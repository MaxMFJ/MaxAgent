#import <Foundation/Foundation.h>
#import <AVFoundation/AVFoundation.h>

NS_ASSUME_NONNULL_BEGIN

/// iOS TTS：使用 AVSpeechSynthesizer 朗读，支持流式按句朗读与停止。
@interface TTSService : NSObject

@property (nonatomic, assign, readonly) BOOL isSpeaking;

/// 当前使用的语音
@property (nonatomic, strong, readonly) AVSpeechSynthesisVoice *currentVoice;

+ (instancetype)sharedService;

/// 获取设备上所有可用的中文语音
+ (NSArray<AVSpeechSynthesisVoice *> *)availableChineseVoices;

/// 设置用户选择的语音（传 nil 则自动选最佳）
- (void)setPreferredVoiceWithIdentifier:(nullable NSString *)identifier;

/// 朗读完整一段文字（会先停止当前朗读）
- (void)speak:(NSString *)text;

/// 流式追加内容：只朗读新完整的句子（句号、问号、感叹号、换行结尾）
- (void)appendAndSpeakStreamedContent:(NSString *)fullText;

/// 会话结束：朗读剩余缓冲中的内容
- (void)speakRemainingBuffer;

/// 重置流式状态（新一条助手消息开始时调用）
- (void)resetStreamState;

/// 停止当前朗读
- (void)stop;

@end

NS_ASSUME_NONNULL_END
