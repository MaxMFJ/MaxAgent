#import <UIKit/UIKit.h>
#import "Message.h"

NS_ASSUME_NONNULL_BEGIN

@class MessageCell;

@protocol MessageCellDelegate <NSObject>
- (void)messageCell:(MessageCell *)cell didTapImage:(UIImage *)image;
@optional
- (void)messageCellDidToggleThinking:(MessageCell *)cell;
@end

@interface MessageCell : UITableViewCell

/// 预计算 cell 高度（供 heightForRowAtIndexPath 使用，避免 self-sizing 开销）
+ (CGFloat)heightForMessage:(Message *)message tableViewWidth:(CGFloat)width;

@property (nonatomic, weak, nullable) id<MessageCellDelegate> delegate;
@property (nonatomic, strong, readonly) UIView *contentLabel;  // YYLabel，对外暴露为 UIView
@property (nonatomic, strong, readonly) UILabel *roleLabel;
@property (nonatomic, strong, readonly) UIView *bubbleView;
@property (nonatomic, strong, readonly) UIActivityIndicatorView *loadingIndicator;

- (void)configureWithMessage:(Message *)message;

@end

NS_ASSUME_NONNULL_END
