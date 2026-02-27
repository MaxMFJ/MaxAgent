#import <UIKit/UIKit.h>
#import "Message.h"

NS_ASSUME_NONNULL_BEGIN

@class MessageCell;

@protocol MessageCellDelegate <NSObject>
- (void)messageCell:(MessageCell *)cell didTapImage:(UIImage *)image;
@optional
- (void)messageCellDidToggleThinking:(MessageCell *)cell;  // thinking 块展开/折叠时调用，用于刷新 cell 高度
@end

@interface MessageCell : UITableViewCell

@property (nonatomic, weak, nullable) id<MessageCellDelegate> delegate;
@property (nonatomic, strong, readonly) UILabel *contentLabel;
@property (nonatomic, strong, readonly) UILabel *roleLabel;
@property (nonatomic, strong, readonly) UIView *bubbleView;
@property (nonatomic, strong, readonly) UIActivityIndicatorView *loadingIndicator;

- (void)configureWithMessage:(Message *)message;

@end

NS_ASSUME_NONNULL_END
