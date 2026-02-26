#import <UIKit/UIKit.h>
#import "Conversation.h"

NS_ASSUME_NONNULL_BEGIN

@protocol ConversationListDelegate <NSObject>

- (void)didSelectConversation:(Conversation *)conversation;
- (void)didDeleteConversation:(Conversation *)conversation;

@end

@interface ConversationListViewController : UIViewController

@property (nonatomic, weak) id<ConversationListDelegate> delegate;

@end

NS_ASSUME_NONNULL_END
