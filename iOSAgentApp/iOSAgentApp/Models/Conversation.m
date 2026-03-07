#import "Conversation.h"

@implementation Conversation

+ (BOOL)supportsSecureCoding {
    return YES;
}

- (instancetype)init {
    return [self initWithId:[[NSUUID UUID] UUIDString]];
}

- (instancetype)initWithId:(NSString *)conversationId {
    self = [super init];
    if (self) {
        _conversationId = [conversationId copy];
        _title = NSLocalizedString(@"new_conversation", @"New Conversation");
        _messages = [NSMutableArray array];
        _createdAt = [NSDate date];
        _updatedAt = [NSDate date];
        _targetType = ConversationTargetTypeMain;
        _targetDuckId = nil;
    }
    return self;
}

#pragma mark - NSCoding

- (instancetype)initWithCoder:(NSCoder *)coder {
    self = [super init];
    if (self) {
        _conversationId = [coder decodeObjectOfClass:[NSString class] forKey:@"conversationId"];
        _title = [coder decodeObjectOfClass:[NSString class] forKey:@"title"];
        
        NSSet *messageClasses = [NSSet setWithObjects:[NSMutableArray class], [Message class], nil];
        _messages = [coder decodeObjectOfClasses:messageClasses forKey:@"messages"];
        if (!_messages) {
            _messages = [NSMutableArray array];
        }
        
        _createdAt = [coder decodeObjectOfClass:[NSDate class] forKey:@"createdAt"];
        _updatedAt = [coder decodeObjectOfClass:[NSDate class] forKey:@"updatedAt"];
        _targetType = (ConversationTargetType)[coder decodeIntegerForKey:@"targetType"];
        _targetDuckId = [coder decodeObjectOfClass:[NSString class] forKey:@"targetDuckId"];
        
        if (!_conversationId) {
            _conversationId = [[NSUUID UUID] UUIDString];
        }
        if (!_createdAt) {
            _createdAt = [NSDate date];
        }
        if (!_updatedAt) {
            _updatedAt = [NSDate date];
        }
    }
    return self;
}

- (void)encodeWithCoder:(NSCoder *)coder {
    [coder encodeObject:_conversationId forKey:@"conversationId"];
    [coder encodeObject:_title forKey:@"title"];
    [coder encodeObject:_messages forKey:@"messages"];
    [coder encodeObject:_createdAt forKey:@"createdAt"];
    [coder encodeObject:_updatedAt forKey:@"updatedAt"];
    [coder encodeInteger:(NSInteger)_targetType forKey:@"targetType"];
    [coder encodeObject:_targetDuckId forKey:@"targetDuckId"];
}

@end
