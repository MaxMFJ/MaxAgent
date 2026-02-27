#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@class ThinkingBlockView;

@protocol ThinkingBlockViewDelegate <NSObject>
- (void)thinkingBlockViewDidToggle:(ThinkingBlockView *)view;
@end

/// 可折叠的 Thinking 块视图，类似 Cursor 的 thinking 展示
/// 输出完成后默认折叠，点击可展开
@interface ThinkingBlockView : UIView

@property (nonatomic, weak, nullable) id<ThinkingBlockViewDelegate> delegate;
@property (nonatomic, copy) NSString *thinkingContent;
/// 是否正在流式输出；NO 时输出完成，默认折叠
@property (nonatomic, assign) BOOL isStreaming;

- (instancetype)initWithThinkingContent:(NSString *)content isStreaming:(BOOL)streaming;

@end

NS_ASSUME_NONNULL_END
