#import <Foundation/Foundation.h>

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

@interface Message : NSObject

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

+ (instancetype)userMessageWithContent:(NSString *)content;
+ (instancetype)assistantMessage;
+ (instancetype)toolCallWithName:(NSString *)toolName callId:(NSString *)callId arguments:(NSString *)arguments;
+ (instancetype)toolResultWithCallId:(NSString *)callId result:(NSString *)result;

- (void)appendContent:(NSString *)content;

@end

NS_ASSUME_NONNULL_END
