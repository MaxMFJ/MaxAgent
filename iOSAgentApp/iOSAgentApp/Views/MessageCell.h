#import <UIKit/UIKit.h>
#import "Message.h"

NS_ASSUME_NONNULL_BEGIN

@interface MessageCell : UITableViewCell

@property (nonatomic, strong, readonly) UILabel *contentLabel;
@property (nonatomic, strong, readonly) UILabel *roleLabel;
@property (nonatomic, strong, readonly) UIView *bubbleView;
@property (nonatomic, strong, readonly) UIActivityIndicatorView *loadingIndicator;

- (void)configureWithMessage:(Message *)message;

@end

NS_ASSUME_NONNULL_END
