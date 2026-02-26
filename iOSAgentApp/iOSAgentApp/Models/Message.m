#import "Message.h"

@implementation Message

+ (BOOL)supportsSecureCoding {
    return YES;
}

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

#pragma mark - NSCoding

- (instancetype)initWithCoder:(NSCoder *)coder {
    self = [super init];
    if (self) {
        _messageId = [coder decodeObjectOfClass:[NSString class] forKey:@"messageId"];
        _role = [coder decodeIntegerForKey:@"role"];
        _content = [coder decodeObjectOfClass:[NSString class] forKey:@"content"];
        _timestamp = [coder decodeObjectOfClass:[NSDate class] forKey:@"timestamp"];
        _status = [coder decodeIntegerForKey:@"status"];
        _fromClient = [coder decodeObjectOfClass:[NSString class] forKey:@"fromClient"];
        _fromClientType = [coder decodeObjectOfClass:[NSString class] forKey:@"fromClientType"];
        _toolName = [coder decodeObjectOfClass:[NSString class] forKey:@"toolName"];
        _toolCallId = [coder decodeObjectOfClass:[NSString class] forKey:@"toolCallId"];
        _modelName = [coder decodeObjectOfClass:[NSString class] forKey:@"modelName"];
        _imageBase64 = [coder decodeObjectOfClass:[NSString class] forKey:@"imageBase64"];
        
        if (!_messageId) {
            _messageId = [[NSUUID UUID] UUIDString];
        }
        if (!_timestamp) {
            _timestamp = [NSDate date];
        }
        if (!_content) {
            _content = @"";
        }
    }
    return self;
}

- (void)encodeWithCoder:(NSCoder *)coder {
    [coder encodeObject:_messageId forKey:@"messageId"];
    [coder encodeInteger:_role forKey:@"role"];
    [coder encodeObject:_content forKey:@"content"];
    [coder encodeObject:_timestamp forKey:@"timestamp"];
    [coder encodeInteger:_status forKey:@"status"];
    [coder encodeObject:_fromClient forKey:@"fromClient"];
    [coder encodeObject:_fromClientType forKey:@"fromClientType"];
    [coder encodeObject:_toolName forKey:@"toolName"];
    [coder encodeObject:_toolCallId forKey:@"toolCallId"];
    [coder encodeObject:_modelName forKey:@"modelName"];
    [coder encodeObject:_imageBase64 forKey:@"imageBase64"];
}

@end
