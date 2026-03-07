#import <UIKit/UIKit.h>

@class Duck;

NS_ASSUME_NONNULL_BEGIN

@protocol DuckTargetSelectorDelegate <NSObject>
/// 选择主 Agent（duck 为 nil）
- (void)duckTargetSelectorDidSelectMain;
/// 选择子 Duck
- (void)duckTargetSelectorDidSelectDuck:(Duck *)duck;
@end

@interface DuckTargetSelectorViewController : UITableViewController

@property (nonatomic, weak, nullable) id<DuckTargetSelectorDelegate> delegate;

@end

NS_ASSUME_NONNULL_END
