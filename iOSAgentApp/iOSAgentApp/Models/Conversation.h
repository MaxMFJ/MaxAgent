#import <Foundation/Foundation.h>
#import "Message.h"

NS_ASSUME_NONNULL_BEGIN

/// 对话目标类型：主 Agent 或子 Duck
typedef NS_ENUM(NSInteger, ConversationTargetType) {
    ConversationTargetTypeMain = 0,  /// 主 Agent
    ConversationTargetTypeDuck = 1    /// 子 Duck
};

@interface Conversation : NSObject <NSCoding, NSSecureCoding>

@property (nonatomic, copy, readonly) NSString *conversationId;
@property (nonatomic, copy) NSString *title;
@property (nonatomic, strong) NSMutableArray<Message *> *messages;
@property (nonatomic, strong) NSDate *createdAt;
@property (nonatomic, strong) NSDate *updatedAt;

/// 对话目标：主 Agent 或子 Duck
@property (nonatomic, assign) ConversationTargetType targetType;
/// 当 targetType == Duck 时，对应的 duck_id
@property (nonatomic, copy, nullable) NSString *targetDuckId;

- (instancetype)init;
- (instancetype)initWithId:(NSString *)conversationId;

@end

NS_ASSUME_NONNULL_END
