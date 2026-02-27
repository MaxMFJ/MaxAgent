#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@class InputView;

@protocol InputViewDelegate <NSObject>

- (void)inputView:(InputView *)inputView didSendMessage:(NSString *)message;
- (void)inputViewDidRequestStop:(InputView *)inputView;

@optional
- (void)inputViewDidRequestVoiceInput:(InputView *)inputView;
- (void)inputView:(InputView *)inputView didRequestSendAsAutonomousTask:(NSString *)text;

@end

@interface InputView : UIView

@property (nonatomic, weak, nullable) id<InputViewDelegate> delegate;
@property (nonatomic, assign, getter=isEnabled) BOOL enabled;
@property (nonatomic, assign, getter=isLoading) BOOL loading;
@property (nonatomic, assign, getter=isVoiceInputActive) BOOL voiceInputActive;

- (void)clearText;
- (void)setText:(NSString *)text;

@end

NS_ASSUME_NONNULL_END
