#import "Message.h"

@implementation Message

- (instancetype)init {
    self = [super init];
    if (self) {
        _messageId = [[NSUUID UUID] UUIDString];
        _timestamp = [NSDate date];
        _status = MessageStatusPending;
        _content = @"";
    }
    return self;
}

+ (instancetype)userMessageWithContent:(NSString *)content {
    Message *message = [[Message alloc] init];
    message.role = MessageRoleUser;
    message.content = content;
    message.status = MessageStatusComplete;
    return message;
}

+ (instancetype)assistantMessage {
    Message *message = [[Message alloc] init];
    message.role = MessageRoleAssistant;
    message.status = MessageStatusStreaming;
    return message;
}

+ (instancetype)toolCallWithName:(NSString *)toolName callId:(NSString *)callId arguments:(NSString *)arguments {
    Message *message = [[Message alloc] init];
    message.role = MessageRoleToolCall;
    message.toolName = toolName;
    message.toolCallId = callId;
    message.content = arguments;
    message.status = MessageStatusComplete;
    return message;
}

+ (instancetype)toolResultWithCallId:(NSString *)callId result:(NSString *)result {
    Message *message = [[Message alloc] init];
    message.role = MessageRoleToolResult;
    message.toolCallId = callId;
    message.content = result;
    message.status = MessageStatusComplete;
    return message;
}

- (void)appendContent:(NSString *)content {
    if (content) {
        _content = [_content stringByAppendingString:content];
    }
}

@end
