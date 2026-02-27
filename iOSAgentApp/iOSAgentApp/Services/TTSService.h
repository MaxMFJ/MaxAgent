#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// iOS TTS：使用 AVSpeechSynthesizer 朗读，支持流式按句朗读与停止。
@interface TTSService : NSObject

@property (nonatomic, assign, readonly) BOOL isSpeaking;

+ (instancetype)sharedService;

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
