#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

typedef NS_ENUM(NSInteger, MessageRole) {
    MessageRoleUser,
    MessageRoleAssistant,
    MessageRoleSystem,
    MessageRoleToolCall,
    MessageRoleToolResult
};

typedef NS_ENUM(NSInteger, MessageStatus) {
    MessageStatusPending,
    MessageStatusStreaming,
    MessageStatusComplete,
    MessageStatusError
};

@interface Message : NSObject <NSCoding, NSSecureCoding>

@property (nonatomic, copy) NSString *messageId;
@property (nonatomic, assign) MessageRole role;
@property (nonatomic, copy) NSString *content;
@property (nonatomic, strong) NSDate *timestamp;
@property (nonatomic, assign) MessageStatus status;
@property (nonatomic, copy, nullable) NSString *fromClient;
@property (nonatomic, copy, nullable) NSString *fromClientType;
@property (nonatomic, copy, nullable) NSString *toolName;
@property (nonatomic, copy, nullable) NSString *toolCallId;
@property (nonatomic, copy, nullable) NSString *modelName;
@property (nonatomic, copy, nullable) NSString *imageBase64;

// 缓存：避免滚动时重复执行昂贵的解析操作
@property (nonatomic, strong, nullable) NSArray<NSDictionary<NSString *, NSString *> *> *cachedParsedParts;
@property (nonatomic, strong, nullable) NSArray<NSString *> *cachedFilePaths;
@property (nonatomic, strong, nullable) UIImage *cachedDecodedImage;
@property (nonatomic, assign) NSUInteger cachedContentLength; // 用于判断缓存是否过期
@property (nonatomic, assign) CGFloat cachedCellHeight; // 预计算的 cell 高度缓存（0 = 未计算）

+ (instancetype)userMessageWithContent:(NSString *)content;
+ (instancetype)assistantMessage;
+ (instancetype)toolCallWithName:(NSString *)toolName callId:(NSString *)callId arguments:(NSString *)arguments;
+ (instancetype)toolResultWithCallId:(NSString *)callId result:(NSString *)result;

- (void)appendContent:(NSString *)content;

@end

NS_ASSUME_NONNULL_END
