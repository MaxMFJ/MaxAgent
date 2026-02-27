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

    _recognitionRequest = [[SFSpeechAudioBufferRecognitionRequest alloc] init];
    _recognitionRequest.shouldReportPartialResults = YES;
    _recognitionRequest.requiresOnDeviceRecognition = NO;

    AVAudioInputNode *inputNode = self.audioEngine.inputNode;
    AVAudioFormat *format = [inputNode outputFormatForBus:0];

    __weak typeof(self) wself = self;
    [inputNode installTapOnBus:0 bufferSize:1024 format:format block:^(AVAudioPCMBuffer *buffer, AVAudioTime *time) {
        [wself.recognitionRequest appendAudioPCMBuffer:buffer];
    }];

    [self.audioEngine prepare];
    NSError *error = nil;
    if (![self.audioEngine startAndReturnError:&error]) {
        _isRunning = NO;
        return;
    }

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
    [self.audioEngine stop];
    [self.audioEngine.inputNode removeTapOnBus:0];
    _isRunning = NO;
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
