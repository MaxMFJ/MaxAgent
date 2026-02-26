#import <Foundation/Foundation.h>
#import "Conversation.h"

NS_ASSUME_NONNULL_BEGIN

@interface ConversationManager : NSObject

@property (nonatomic, strong, readonly) NSMutableArray<Conversation *> *conversations;
@property (nonatomic, strong, nullable) Conversation *currentConversation;

+ (instancetype)sharedManager;

- (Conversation *)createNewConversation;
- (void)selectConversation:(Conversation *)conversation;
- (void)deleteConversation:(Conversation *)conversation;
- (void)saveConversations;
- (void)loadConversations;

@end

NS_ASSUME_NONNULL_END
