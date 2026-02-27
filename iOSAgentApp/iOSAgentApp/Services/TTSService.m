#import "TTSService.h"
#import <AVFoundation/AVFoundation.h>

static NSCharacterSet *sentenceEndChars(void) {
    static NSCharacterSet *set;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        set = [NSCharacterSet characterSetWithCharactersInString:@"。！？.!?\n"];
    });
    return set;
}

@interface TTSService () <AVSpeechSynthesizerDelegate>
@property (nonatomic, strong) AVSpeechSynthesizer *synthesizer;
@property (nonatomic, copy) NSString *pendingSentenceBuffer;
@property (nonatomic, assign) NSInteger spokenSentenceCount;
@property (nonatomic, strong) NSMutableArray<NSString *> *sentenceQueue;
@property (nonatomic, assign, readwrite) BOOL isSpeaking;
@end

@implementation TTSService

+ (instancetype)sharedService {
    static TTSService *shared = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        shared = [[TTSService alloc] init];
    });
    return shared;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _synthesizer = [[AVSpeechSynthesizer alloc] init];
        _synthesizer.delegate = self;
        _pendingSentenceBuffer = @"";
        _sentenceQueue = [NSMutableArray array];
    }
    return self;
}

- (void)speak:(NSString *)text {
    NSString *t = [text stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    if (t.length == 0) return;
    [self stop];
    AVSpeechUtterance *utterance = [AVSpeechUtterance speechUtteranceWithString:t];
    utterance.voice = [AVSpeechSynthesisVoice voiceWithLanguage:@"zh-CN"] ?: [AVSpeechSynthesisVoice voiceWithLanguage:@"en-US"];
    [self.synthesizer speakUtterance:utterance];
    _isSpeaking = YES;
}

- (void)appendAndSpeakStreamedContent:(NSString *)fullText {
    NSString *t = [fullText stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    if (t.length == 0) return;

    NSArray<NSString *> *sentences = nil;
    NSString *remainder = nil;
    [self splitIntoSentences:t sentences:&sentences remainder:&remainder];
    self.pendingSentenceBuffer = remainder ?: @"";

    for (NSInteger i = self.spokenSentenceCount; i < (NSInteger)sentences.count; i++) {
        NSString *trimmed = [sentences[i] stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
        if (trimmed.length == 0) continue;
        if (!self.isSpeaking) {
            [self speakUtterance:trimmed];
            _isSpeaking = YES;
        } else {
            [self.sentenceQueue addObject:trimmed];
        }
    }
    _spokenSentenceCount = sentences.count;
}

- (void)speakUtterance:(NSString *)text {
    AVSpeechUtterance *utterance = [AVSpeechUtterance speechUtteranceWithString:text];
    utterance.voice = [AVSpeechSynthesisVoice voiceWithLanguage:@"zh-CN"] ?: [AVSpeechSynthesisVoice voiceWithLanguage:@"en-US"];
    [self.synthesizer speakUtterance:utterance];
}

- (void)speakNextInQueue {
    if (self.sentenceQueue.count == 0 || self.isSpeaking) return;
    NSString *next = self.sentenceQueue.firstObject;
    [self.sentenceQueue removeObjectAtIndex:0];
    [self speakUtterance:next];
    _isSpeaking = YES;
}

- (void)speakRemainingBuffer {
    NSString *t = [self.pendingSentenceBuffer stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    self.pendingSentenceBuffer = @"";
    _spokenSentenceCount = 0;
    if (t.length == 0) return;
    if (!self.isSpeaking) {
        [self speakUtterance:t];
        _isSpeaking = YES;
    } else {
        [self.sentenceQueue addObject:t];
    }
}

- (void)resetStreamState {
    _spokenSentenceCount = 0;
}

- (void)stop {
    [self.synthesizer stopSpeakingAtBoundary:AVSpeechBoundaryImmediate];
    [self.sentenceQueue removeAllObjects];
    self.pendingSentenceBuffer = @"";
    _spokenSentenceCount = 0;
    _isSpeaking = NO;
}

- (void)splitIntoSentences:(NSString *)text sentences:(NSArray<NSString *> * _Nullable * _Nonnull)outSentences remainder:(NSString * _Nullable * _Nonnull)outRemainder {
    NSMutableArray *sentences = [NSMutableArray array];
    NSMutableString *current = [NSMutableString string];
    NSCharacterSet *ends = sentenceEndChars();
    for (NSUInteger i = 0; i < text.length; i++) {
        unichar c = [text characterAtIndex:i];
        NSString *s = [NSString stringWithCharacters:&c length:1];
        if ([ends characterIsMember:c]) {
            [current appendString:s];
            NSString *trimmed = [current stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
            if (trimmed.length > 0) [sentences addObject:trimmed];
            [current setString:@""];
        } else {
            [current appendString:s];
        }
    }
    *outSentences = sentences;
    *outRemainder = [current stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
}

#pragma mark - AVSpeechSynthesizerDelegate

- (void)speechSynthesizer:(AVSpeechSynthesizer *)synthesizer didFinishSpeechUtterance:(AVSpeechUtterance *)utterance {
    dispatch_async(dispatch_get_main_queue(), ^{
        self->_isSpeaking = NO;
        if (self.sentenceQueue.count > 0) {
            [self speakNextInQueue];
        }
    });
}

- (void)speechSynthesizer:(AVSpeechSynthesizer *)synthesizer didCancelSpeechUtterance:(AVSpeechUtterance *)utterance {
    dispatch_async(dispatch_get_main_queue(), ^{
        self->_isSpeaking = NO;
        if (self.sentenceQueue.count > 0) {
            [self speakNextInQueue];
        }
    });
}

@end
