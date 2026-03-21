#import <UIKit/UIKit.h>
#import "Conversation.h"
#import "GroupChat.h"

NS_ASSUME_NONNULL_BEGIN

@protocol ConversationListDelegate <NSObject>

- (void)didSelectConversation:(Conversation *)conversation;
- (void)didDeleteConversation:(Conversation *)conversation;

@optional
- (void)didSelectGroupChat:(GroupChat *)groupChat;
- (void)didDeleteGroupChat:(GroupChat *)groupChat;

@end

@interface ConversationListViewController : UIViewController

@property (nonatomic, weak) id<ConversationListDelegate> delegate;
/// 由外部注入（通常来自 ChatViewController 的本地恢复结果）
@property (nonatomic, strong) NSArray<GroupChat *> *groupChats;

@end

NS_ASSUME_NONNULL_END
