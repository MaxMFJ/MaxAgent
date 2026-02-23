#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@class InputView;

@protocol InputViewDelegate <NSObject>

- (void)inputView:(InputView *)inputView didSendMessage:(NSString *)message;
- (void)inputViewDidRequestStop:(InputView *)inputView;

@end

@interface InputView : UIView

@property (nonatomic, weak, nullable) id<InputViewDelegate> delegate;
@property (nonatomic, assign, getter=isEnabled) BOOL enabled;
@property (nonatomic, assign, getter=isLoading) BOOL loading;

- (void)clearText;
- (void)setText:(NSString *)text;

@end

NS_ASSUME_NONNULL_END
