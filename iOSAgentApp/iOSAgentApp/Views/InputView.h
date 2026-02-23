#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@class InputView;

@protocol InputViewDelegate <NSObject>

- (void)inputView:(InputView *)inputView didSendMessage:(NSString *)message;

@end

@interface InputView : UIView

@property (nonatomic, weak, nullable) id<InputViewDelegate> delegate;
@property (nonatomic, assign, getter=isEnabled) BOOL enabled;

- (void)clearText;
- (void)setText:(NSString *)text;

@end

NS_ASSUME_NONNULL_END
