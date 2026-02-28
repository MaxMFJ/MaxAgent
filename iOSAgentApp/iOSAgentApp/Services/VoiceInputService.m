#import "VoiceInputService.h"
#import <Speech/Speech.h>
#import <AVFoundation/AVFoundation.h>

@interface VoiceInputService ()
@property (nonatomic, strong, nullable) SFSpeechRecognizer *speechRecognizer;
@property (nonatomic, strong, nullable) SFSpeechAudioBufferRecognitionRequest *recognitionRequest;
@property (nonatomic, strong, nullable) SFSpeechRecognitionTask *recognitionTask;
@property (nonatomic, strong) AVAudioEngine *audioEngine;
@property (nonatomic, assign) BOOL isRunning;
@property (nonatomic, assign) BOOL authorized;
@property (nonatomic, strong) dispatch_queue_t queue;
@property (nonatomic, strong, nullable) dispatch_block_t silenceWorkItem;
@property (nonatomic, strong, nullable) dispatch_block_t noSpeechWorkItem;
@end

@implementation VoiceInputService

+ (instancetype)sharedService {
    static VoiceInputService *shared = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        shared = [[VoiceInputService alloc] init];
    });
    return shared;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _speechRecognizer = [[SFSpeechRecognizer alloc] initWithLocale:[NSLocale localeWithLocaleIdentifier:@"zh-CN"]];
        if (!_speechRecognizer) {
            _speechRecognizer = [[SFSpeechRecognizer alloc] initWithLocale:[NSLocale localeWithLocaleIdentifier:@"en-US"]];
        }
        _audioEngine = [[AVAudioEngine alloc] init];
        _queue = dispatch_queue_create("com.iosagent.voiceinput", DISPATCH_QUEUE_SERIAL);
        _silenceDuration = 2.0;
        _noSpeechTimeout = 12.0;
        _interimText = @"";
        _finalText = @"";
    }
    return self;
}

- (void)requestAuthorization:(void (^)(BOOL))completion {
    [SFSpeechRecognizer requestAuthorization:^(SFSpeechRecognizerAuthorizationStatus status) {
        dispatch_async(dispatch_get_main_queue(), ^{
            BOOL granted = (status == SFSpeechRecognizerAuthorizationStatusAuthorized);
            self.authorized = granted;
            if (completion) completion(granted);
        });
    }];
}

- (BOOL)isRecording {
    return _isRunning;
}

- (void)startRecording {
    if (!self.authorized) {
        [self requestAuthorization:^(BOOL granted) {
            if (granted) [self startRecording];
        }];
        return;
    }
    if (_isRunning) return;
    if (!_speechRecognizer || !_speechRecognizer.isAvailable) return;

    [self stopRecording];

    _interimText = @"";
    _finalText = @"";
    _isRunning = YES;

    // 1. 配置 AVAudioSession（必须在访问 inputNode 之前）
    AVAudioSession *session = [AVAudioSession sharedInstance];
    NSError *sessionError = nil;
    [session setCategory:AVAudioSessionCategoryRecord
                    mode:AVAudioSessionModeMeasurement
                 options:AVAudioSessionCategoryOptionDuckOthers
                   error:&sessionError];
    if (sessionError) {
        NSLog(@"[VoiceInput] Audio session category error: %@", sessionError);
        _isRunning = NO;
        return;
    }
    [session setActive:YES
           withOptions:AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation
                 error:&sessionError];
    if (sessionError) {
        NSLog(@"[VoiceInput] Audio session activate error: %@", sessionError);
        _isRunning = NO;
        return;
    }

    _recognitionRequest = [[SFSpeechAudioBufferRecognitionRequest alloc] init];
    _recognitionRequest.shouldReportPartialResults = YES;
    _recognitionRequest.requiresOnDeviceRecognition = NO;

    // 2. 获取 inputNode（此时 audio session 已正确配置）
    AVAudioInputNode *inputNode = self.audioEngine.inputNode;

    // 3. 获取硬件原生格式并验证
    AVAudioFormat *hwFormat = [inputNode outputFormatForBus:0];
    AVAudioFormat *recordingFormat = hwFormat;

    // 如果硬件格式无效，手动创建 16kHz mono 格式（语音识别常用格式）
    if (!recordingFormat || recordingFormat.channelCount == 0 || recordingFormat.sampleRate == 0) {
        recordingFormat = [[AVAudioFormat alloc] initWithCommonFormat:AVAudioPCMFormatFloat32
                                                          sampleRate:16000
                                                            channels:1
                                                         interleaved:NO];
    }

    // 4. 安装 tap（使用 @try 防止格式不匹配导致的异常崩溃）
    @try {
        [inputNode installTapOnBus:0 bufferSize:1024 format:recordingFormat block:^(AVAudioPCMBuffer *buffer, AVAudioTime *time) {
            [self.recognitionRequest appendAudioPCMBuffer:buffer];
        }];
    } @catch (NSException *exception) {
        NSLog(@"[VoiceInput] Tap install failed with format %@, retrying with nil format: %@", recordingFormat, exception);
        // 回退方案：使用 nil 格式（让系统自动选择匹配的格式）
        @try {
            [inputNode removeTapOnBus:0];
            [inputNode installTapOnBus:0 bufferSize:1024 format:nil block:^(AVAudioPCMBuffer *buffer, AVAudioTime *time) {
                [self.recognitionRequest appendAudioPCMBuffer:buffer];
            }];
        } @catch (NSException *ex2) {
            NSLog(@"[VoiceInput] Tap install failed even with nil format: %@", ex2);
            _isRunning = NO;
            return;
        }
    }

    [self.audioEngine prepare];
    NSError *error = nil;
    if (![self.audioEngine startAndReturnError:&error]) {
        NSLog(@"[VoiceInput] Engine start error: %@", error);
        _isRunning = NO;
        return;
    }

    __weak typeof(self) wself = self;
    _recognitionTask = [self.speechRecognizer recognitionTaskWithRequest:_recognitionRequest resultHandler:^(SFSpeechRecognitionResult * _Nullable result, NSError * _Nullable err) {
        __strong typeof(wself) self = wself;
        if (!self) return;
        if (err) return;
        if (!result) return;

        NSString *best = result.bestTranscription.formattedString;
        BOOL isFinal = result.isFinal;

        dispatch_async(dispatch_get_main_queue(), ^{
            if (isFinal) {
                self.finalText = best;
                self.interimText = @"";
                [self cancelNoSpeechTimeout];
                [self scheduleSilenceSubmit];
                if (self.onTextUpdate) self.onTextUpdate(@"", best);
            } else {
                self.interimText = best;
                if (self.onTextUpdate) self.onTextUpdate(best, self.finalText);
            }
        });
    }];

    [self scheduleNoSpeechTimeout];
}

- (void)cancelNoSpeechTimeout {
    __weak typeof(self) wself = self;
    dispatch_async(_queue, ^{
        if (wself.noSpeechWorkItem) {
            dispatch_block_cancel(wself.noSpeechWorkItem);
            wself.noSpeechWorkItem = nil;
        }
    });
}

- (void)stopRecording {
    __weak typeof(self) wself = self;
    dispatch_async(_queue, ^{
        if (wself.silenceWorkItem) {
            dispatch_block_cancel(wself.silenceWorkItem);
            wself.silenceWorkItem = nil;
        }
        if (wself.noSpeechWorkItem) {
            dispatch_block_cancel(wself.noSpeechWorkItem);
            wself.noSpeechWorkItem = nil;
        }
    });
    [_recognitionTask cancel];
    _recognitionTask = nil;
    [_recognitionRequest endAudio];
    _recognitionRequest = nil;
    if (self.audioEngine.isRunning) {
        [self.audioEngine stop];
    }
    @try {
        [self.audioEngine.inputNode removeTapOnBus:0];
    } @catch (NSException *exception) {
        NSLog(@"[VoiceInput] removeTap exception: %@", exception);
    }
    _isRunning = NO;

    // 反激活 audio session，让其他 app 恢复音频
    NSError *deactivateError = nil;
    [[AVAudioSession sharedInstance] setActive:NO
                                   withOptions:AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation
                                         error:&deactivateError];
}

- (void)scheduleSilenceSubmit {
    NSString *textToSubmit = [self.finalText copy];
    __weak typeof(self) wself = self;
    dispatch_async(_queue, ^{
        if (wself.silenceWorkItem) dispatch_block_cancel(wself.silenceWorkItem);
        dispatch_block_t item = dispatch_block_create(0, ^{
            dispatch_async(dispatch_get_main_queue(), ^{
                if (wself.isRunning) {
                    [wself stopRecording];
                    if (wself.onShouldSubmit && textToSubmit.length > 0) {
                        wself.onShouldSubmit(textToSubmit);
                    }
                }
            });
        });
        wself.silenceWorkItem = item;
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(wself.silenceDuration * NSEC_PER_SEC)), wself.queue, item);
    });
}

- (void)scheduleNoSpeechTimeout {
    __weak typeof(self) wself = self;
    dispatch_async(_queue, ^{
        if (wself.noSpeechWorkItem) dispatch_block_cancel(wself.noSpeechWorkItem);
        dispatch_block_t item = dispatch_block_create(0, ^{
            dispatch_async(dispatch_get_main_queue(), ^{
                if (wself.isRunning) {
                    NSString *text = wself.finalText.length > 0 ? wself.finalText : wself.interimText;
                    [wself stopRecording];
                    if (wself.onShouldSubmit) wself.onShouldSubmit(text ?: @"");
                }
            });
        });
        wself.noSpeechWorkItem = item;
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(wself.noSpeechTimeout * NSEC_PER_SEC)), wself.queue, item);
    });
}

- (NSString *)commitCurrentText {
    NSString *text = _finalText.length > 0 ? _finalText : _interimText;
    [self stopRecording];
    return [text stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]] ?: @"";
}

@end
