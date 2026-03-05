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
@property (nonatomic, strong) AVSpeechSynthesisVoice *bestChineseVoice;
@end

@implementation TTSService

#pragma mark - TTS Text Preprocessing

/// 预处理文本：清理Markdown，百分比→中文读法，保留小数点，缩略词音译，过滤表情
+ (NSString *)preprocessForSpeech:(NSString *)text {
    if (text.length == 0) return text;
    NSMutableString *result = [text mutableCopy];

    // 0. 清理 Markdown 语法、URL、HTML/XML标签和 thinking 块
    {
        // 移除 <thinking>...</thinking> 块（含内容）
        NSRegularExpression *thinkBlock = [NSRegularExpression regularExpressionWithPattern:@"<thinking>[\\s\\S]*?</thinking>" options:NSRegularExpressionCaseInsensitive error:nil];
        [thinkBlock replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@""];

        // 移除未闭合的 <thinking>（流式中可能没闭合）
        NSRegularExpression *thinkOpen = [NSRegularExpression regularExpressionWithPattern:@"<thinking>[\\s\\S]*$" options:NSRegularExpressionCaseInsensitive error:nil];
        [thinkOpen replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@""];

        // 移除所有 HTML/XML 标签 <...>
        NSRegularExpression *htmlTags = [NSRegularExpression regularExpressionWithPattern:@"<[^>]+>" options:0 error:nil];
        [htmlTags replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@""];

        // 移除代码块 ```...```
        NSRegularExpression *codeBlock = [NSRegularExpression regularExpressionWithPattern:@"```[\\s\\S]*?```" options:0 error:nil];
        [codeBlock replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@""];

        // 移除行内代码 `...`
        NSRegularExpression *inlineCode = [NSRegularExpression regularExpressionWithPattern:@"`[^`]+`" options:0 error:nil];
        [inlineCode replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@""];

        // Markdown 链接 [text](url) → text
        NSRegularExpression *mdLink = [NSRegularExpression regularExpressionWithPattern:@"\\[([^\\]]+)\\]\\([^)]+\\)" options:0 error:nil];
        [mdLink replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@"$1"];

        // 移除 URL
        NSRegularExpression *url = [NSRegularExpression regularExpressionWithPattern:@"https?://[^\\s)）]+" options:0 error:nil];
        [url replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@""];

        // 移除 Markdown 加粗/斜体: **text** → text, *text* → text, __text__ → text
        NSRegularExpression *bold = [NSRegularExpression regularExpressionWithPattern:@"\\*{1,3}([^*]+)\\*{1,3}" options:0 error:nil];
        [bold replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@"$1"];

        NSRegularExpression *underscoreBold = [NSRegularExpression regularExpressionWithPattern:@"_{1,3}([^_]+)_{1,3}" options:0 error:nil];
        [underscoreBold replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@"$1"];

        // 移除标题符号 # ## ###
        NSRegularExpression *heading = [NSRegularExpression regularExpressionWithPattern:@"^#{1,6}\\s*" options:NSRegularExpressionAnchorsMatchLines error:nil];
        [heading replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@""];

        // 移除列表符号 - * 1. 2.
        NSRegularExpression *listItem = [NSRegularExpression regularExpressionWithPattern:@"^\\s*[-*]\\s+" options:NSRegularExpressionAnchorsMatchLines error:nil];
        [listItem replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@""];

        NSRegularExpression *numList = [NSRegularExpression regularExpressionWithPattern:@"^\\s*\\d+\\.\\s+" options:NSRegularExpressionAnchorsMatchLines error:nil];
        [numList replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@""];

        // 移除 ~~删除线~~
        NSRegularExpression *strikethrough = [NSRegularExpression regularExpressionWithPattern:@"~~([^~]+)~~" options:0 error:nil];
        [strikethrough replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@"$1"];
    }

    // 1. 百分比：50% → 百分之50，3.14% → 百分之3点14
    {
        NSRegularExpression *regex = [NSRegularExpression regularExpressionWithPattern:@"(\\d+(?:\\.\\d+)?)\\s*%" options:0 error:nil];
        NSArray<NSTextCheckingResult *> *matches = [regex matchesInString:result options:0 range:NSMakeRange(0, result.length)];
        // 从后向前替换避免 range 偏移
        for (NSTextCheckingResult *m in [matches reverseObjectEnumerator]) {
            NSString *num = [result substringWithRange:[m rangeAtIndex:1]];
            NSString *replacement = [NSString stringWithFormat:@"百分之%@", num];
            [result replaceCharactersInRange:m.range withString:replacement];
        }
    }

    // 2. 小数点：3.14 → 3点14（仅数字间的点）
    {
        NSRegularExpression *regex = [NSRegularExpression regularExpressionWithPattern:@"(\\d)\\.(\\d)" options:0 error:nil];
        NSArray<NSTextCheckingResult *> *matches = [regex matchesInString:result options:0 range:NSMakeRange(0, result.length)];
        for (NSTextCheckingResult *m in [matches reverseObjectEnumerator]) {
            NSString *before = [result substringWithRange:[m rangeAtIndex:1]];
            NSString *after  = [result substringWithRange:[m rangeAtIndex:2]];
            NSString *replacement = [NSString stringWithFormat:@"%@点%@", before, after];
            [result replaceCharactersInRange:m.range withString:replacement];
        }
    }

    // 3. 缩略词：连续大写字母→中文字母音译 (AI→诶爱, CPU→西皮优)
    {
        // 英文字母中文读音映射
        static NSDictionary<NSString *, NSString *> *letterMap;
        static dispatch_once_t onceToken;
        dispatch_once(&onceToken, ^{
            letterMap = @{
                @"A": @"诶", @"B": @"比", @"C": @"西", @"D": @"迪",
                @"E": @"伊", @"F": @"艾弗", @"G": @"吉", @"H": @"艾奇",
                @"I": @"爱", @"J": @"杰", @"K": @"开", @"L": @"艾尔",
                @"M": @"艾姆", @"N": @"恩", @"O": @"欧", @"P": @"皮",
                @"Q": @"寇", @"R": @"啊", @"S": @"艾斯", @"T": @"踢",
                @"U": @"优", @"V": @"维", @"W": @"达不留", @"X": @"艾克斯",
                @"Y": @"歪", @"Z": @"泽"
            };
        });
        NSRegularExpression *regex = [NSRegularExpression regularExpressionWithPattern:@"[A-Z]{2,}" options:0 error:nil];
        NSArray<NSTextCheckingResult *> *matches = [regex matchesInString:result options:0 range:NSMakeRange(0, result.length)];
        for (NSTextCheckingResult *m in [matches reverseObjectEnumerator]) {
            NSString *abbr = [result substringWithRange:m.range];
            NSMutableString *phonetic = [NSMutableString string];
            for (NSUInteger i = 0; i < abbr.length; i++) {
                NSString *ch = [abbr substringWithRange:NSMakeRange(i, 1)];
                NSString *mapped = letterMap[ch];
                if (mapped) [phonetic appendString:mapped];
                else [phonetic appendString:ch];
            }
            [result replaceCharactersInRange:m.range withString:phonetic];
        }
    }

    // 4. 过滤所有不可朗读字符（只保留中日韩文字、ASCII字母数字、常用标点）
    //    使用正则白名单：不在以下范围内的字符一律删除
    {
        static NSRegularExpression *nonReadable;
        static dispatch_once_t emojiOnce;
        dispatch_once(&emojiOnce, ^{
            nonReadable = [NSRegularExpression regularExpressionWithPattern:
                @"[^"
                @"\\u0020-\\u007E"  // ASCII printable (space ~ tilde)
                @"\\u00A0-\\u024F"  // Latin Extended (accented chars)
                @"\\u2010-\\u2027"  // Dashes, quotes, leaders, ellipsis
                @"\\u2030-\\u205E"  // Per mille, prime, brackets (skip 2028-202F bidi/separators)
                @"\\u3000-\\u303F"  // CJK Symbols & Punctuation (、。「」等)
                @"\\u3040-\\u30FF"  // Hiragana & Katakana
                @"\\u3400-\\u4DBF"  // CJK Extension A
                @"\\u4E00-\\u9FFF"  // CJK Unified Ideographs
                @"\\uAC00-\\uD7AF"  // Hangul Syllables
                @"\\uF900-\\uFAFF"  // CJK Compatibility Ideographs
                @"\\uFE30-\\uFE4F"  // CJK Compatibility Forms (︰︱等)
                @"\\uFF00-\\uFFEF"  // Fullwidth Forms (！？等)
                @"]+"
                options:0 error:nil];
        });
        [nonReadable replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@""];
    }

    // 5. 清理多余空白：连续空格合并为一个，去掉首尾空白
    {
        static NSRegularExpression *multiSpace;
        static dispatch_once_t spaceOnce;
        dispatch_once(&spaceOnce, ^{
            multiSpace = [NSRegularExpression regularExpressionWithPattern:@"\\s{2,}" options:0 error:nil];
        });
        [multiSpace replaceMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@" "];
        NSString *trimmed = [result stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
        [result setString:trimmed];
    }

    NSString *finalResult = [result copy];
    NSLog(@"[TTS preprocess] in=%@ out=%@", [text substringToIndex:MIN(text.length, 50u)], [finalResult substringToIndex:MIN(finalResult.length, 50u)]);
    return finalResult;
}

/// 查找设备上最高质量的中文语音（Premium > Enhanced > Default）
+ (AVSpeechSynthesisVoice *)findBestChineseVoice {
    NSArray<AVSpeechSynthesisVoice *> *allVoices = [AVSpeechSynthesisVoice speechVoices];
    AVSpeechSynthesisVoice *best = nil;
    NSInteger bestQuality = -1;

    for (AVSpeechSynthesisVoice *voice in allVoices) {
        // 匹配中文语音 (zh-CN, zh-TW, zh-HK)
        if (![voice.language hasPrefix:@"zh"]) continue;

        NSInteger q = (NSInteger)voice.quality; // Default=1, Enhanced=2, Premium=3
        if (q > bestQuality) {
            bestQuality = q;
            best = voice;
        }
    }
    // 如果没找到中文语音，fallback
    if (!best) {
        best = [AVSpeechSynthesisVoice voiceWithLanguage:@"zh-CN"];
    }
    return best;
}

/// 列出所有可用的中文语音（调试用）
+ (void)logAvailableChineseVoices {
    for (AVSpeechSynthesisVoice *voice in [AVSpeechSynthesisVoice speechVoices]) {
        if ([voice.language hasPrefix:@"zh"]) {
            NSLog(@"[TTS Voice] %@ | lang=%@ | quality=%ld | id=%@",
                  voice.name, voice.language, (long)voice.quality, voice.identifier);
        }
    }
}

+ (NSArray<AVSpeechSynthesisVoice *> *)availableChineseVoices {
    NSMutableArray<AVSpeechSynthesisVoice *> *voices = [NSMutableArray array];
    for (AVSpeechSynthesisVoice *voice in [AVSpeechSynthesisVoice speechVoices]) {
        if ([voice.language hasPrefix:@"zh"]) {
            [voices addObject:voice];
        }
    }
    // 按质量降序排列
    [voices sortUsingComparator:^NSComparisonResult(AVSpeechSynthesisVoice *a, AVSpeechSynthesisVoice *b) {
        if (a.quality != b.quality) return b.quality > a.quality ? NSOrderedDescending : NSOrderedAscending;
        return [a.name compare:b.name];
    }];
    return [voices copy];
}

static NSString * const kTTSVoiceIdentifierKey = @"tts_preferred_voice_identifier";

- (void)setPreferredVoiceWithIdentifier:(NSString *)identifier {
    if (identifier) {
        AVSpeechSynthesisVoice *voice = [AVSpeechSynthesisVoice voiceWithIdentifier:identifier];
        if (voice) {
            _bestChineseVoice = voice;
            [[NSUserDefaults standardUserDefaults] setObject:identifier forKey:kTTSVoiceIdentifierKey];
            NSLog(@"[TTS] Voice changed to: %@ (quality=%ld)", voice.name, (long)voice.quality);
            return;
        }
    }
    // nil 或找不到 → 自动选最佳
    _bestChineseVoice = [TTSService findBestChineseVoice];
    [[NSUserDefaults standardUserDefaults] removeObjectForKey:kTTSVoiceIdentifierKey];
    NSLog(@"[TTS] Voice reset to auto: %@", _bestChineseVoice.name);
}

- (AVSpeechSynthesisVoice *)currentVoice {
    return _bestChineseVoice;
}


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

        // 加载用户偏好语音或自动选最佳
        NSString *savedId = [[NSUserDefaults standardUserDefaults] stringForKey:kTTSVoiceIdentifierKey];
        if (savedId) {
            AVSpeechSynthesisVoice *saved = [AVSpeechSynthesisVoice voiceWithIdentifier:savedId];
            _bestChineseVoice = saved ?: [TTSService findBestChineseVoice];
        } else {
            _bestChineseVoice = [TTSService findBestChineseVoice];
        }

        // 配置 AVAudioSession 支持后台播放
        NSError *error = nil;
        [[AVAudioSession sharedInstance] setCategory:AVAudioSessionCategoryPlayback
                                         withOptions:AVAudioSessionCategoryOptionDuckOthers
                                               error:&error];
        if (error) {
            NSLog(@"[TTS] AudioSession setCategory error: %@", error);
        }
        [[AVAudioSession sharedInstance] setActive:YES error:&error];
        if (error) {
            NSLog(@"[TTS] AudioSession setActive error: %@", error);
        }

        NSLog(@"[TTS] Selected voice: %@ (quality=%ld)", _bestChineseVoice.name, (long)_bestChineseVoice.quality);
    }
    return self;
}

- (void)speak:(NSString *)text {
    NSString *t = [text stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    t = [TTSService preprocessForSpeech:t];
    if (t.length == 0) return;
    [self stop];
    AVSpeechUtterance *utterance = [AVSpeechUtterance speechUtteranceWithString:t];
    utterance.voice = self.bestChineseVoice;
    [self.synthesizer speakUtterance:utterance];
    _isSpeaking = YES;
}

- (void)appendAndSpeakStreamedContent:(NSString *)fullText {
    NSString *t = [fullText stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    if (t.length == 0) return;

    // ⚡ 关键：在句子分割前就移除 <thinking> 块
    // 否则 thinking 内容会被 splitIntoSentences 按 "." 分成多个句子，
    // 每个句子不包含 <thinking> 标签，preprocessForSpeech 就无法移除它们
    {
        NSMutableString *cleaned = [t mutableCopy];
        // 移除完整的 <thinking>...</thinking> 块
        static NSRegularExpression *thinkComplete;
        static NSRegularExpression *thinkOpen;
        static dispatch_once_t thinkOnce;
        dispatch_once(&thinkOnce, ^{
            thinkComplete = [NSRegularExpression regularExpressionWithPattern:@"<thinking>[\\s\\S]*?</thinking>" options:NSRegularExpressionCaseInsensitive error:nil];
            thinkOpen = [NSRegularExpression regularExpressionWithPattern:@"<thinking>[\\s\\S]*$" options:NSRegularExpressionCaseInsensitive error:nil];
        });
        [thinkComplete replaceMatchesInString:cleaned options:0 range:NSMakeRange(0, cleaned.length) withTemplate:@""];
        // 移除未闭合的 <thinking>（流式中可能尚未收到 </thinking>）
        [thinkOpen replaceMatchesInString:cleaned options:0 range:NSMakeRange(0, cleaned.length) withTemplate:@""];
        t = [cleaned stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
        if (t.length == 0) return;
    }

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
    NSString *processed = [TTSService preprocessForSpeech:text];
    if (processed.length == 0) {
        NSLog(@"[TTS] Empty after preprocess, skipping. raw=%@", [text substringToIndex:MIN(text.length, 80u)]);
        return;
    }
    NSLog(@"[TTS speak] \"%@\"", [processed substringToIndex:MIN(processed.length, 100u)]);
    AVSpeechUtterance *utterance = [AVSpeechUtterance speechUtteranceWithString:processed];
    utterance.voice = self.bestChineseVoice;
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
