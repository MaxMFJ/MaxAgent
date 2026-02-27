#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// 语音输入服务：实时识别、静音超时自动提交、无说话超时强制提交。
@interface VoiceInputService : NSObject

/// 静音多久后自动提交（秒）
@property (nonatomic, assign) NSTimeInterval silenceDuration;
/// 一直未说话多久后强制提交（秒）
@property (nonatomic, assign) NSTimeInterval noSpeechTimeout;

/// 实时中间结果（显示在输入框）
@property (nonatomic, copy) NSString *interimText;
/// 当前会话已确认的最终文本
@property (nonatomic, copy) NSString *finalText;

/// 静音检测到后触发提交：参数为当前最终文本，调用方需过滤空字符串
@property (nonatomic, copy, nullable) void (^onShouldSubmit)(NSString *text);
/// 识别中间/最终结果更新时回调，用于更新输入框显示
@property (nonatomic, copy, nullable) void (^onTextUpdate)(NSString *interim, NSString *final);

+ (instancetype)sharedService;

- (void)requestAuthorization:(void (^)(BOOL granted))completion;
- (void)startRecording;
- (void)stopRecording;
/// 手动提交：返回当前 finalText 或 interimText，并停止录音
- (NSString *)commitCurrentText;
- (BOOL)isRecording;

@end

NS_ASSUME_NONNULL_END
