#import <UIKit/UIKit.h>
#import "GroupChat.h"

NS_ASSUME_NONNULL_BEGIN

@class GroupChatViewController;

@protocol GroupChatViewControllerDelegate <NSObject>
@optional
- (void)groupChatViewControllerDidRequestBack:(GroupChatViewController *)vc;
@end

@interface GroupChatViewController : UIViewController <UITableViewDataSource, UITableViewDelegate>

@property (nonatomic, weak, nullable) id<GroupChatViewControllerDelegate> delegate;
@property (nonatomic, strong) GroupChat *groupChat;

- (void)appendMessage:(GroupMessage *)message;
- (void)updateStatus:(GroupChatStatusType)status summary:(GroupTaskSummary *)summary;

@end

NS_ASSUME_NONNULL_END
