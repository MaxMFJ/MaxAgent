#import <Foundation/Foundation.h>
#import "Conversation.h"

NS_ASSUME_NONNULL_BEGIN

@interface ConversationManager : NSObject

@property (nonatomic, strong, readonly) NSMutableArray<Conversation *> *conversations;
@property (nonatomic, strong, nullable) Conversation *currentConversation;

+ (instancetype)sharedManager;

- (Conversation *)createNewConversation;
/// 创建以子 Duck 为目标的会话
- (Conversation *)createNewConversationWithDuckId:(NSString *)duckId;
- (void)selectConversation:(Conversation *)conversation;
- (void)deleteConversation:(Conversation *)conversation;
- (void)saveConversations;
- (void)loadConversations;

@end

NS_ASSUME_NONNULL_END
