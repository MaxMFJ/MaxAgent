#import <UIKit/UIKit.h>
#import "ActionLogEntry.h"

NS_ASSUME_NONNULL_BEGIN

@class AgentLiveView;

@protocol AgentLiveViewDelegate <NSObject>
@optional
/// 用户点击展开/折叠
- (void)agentLiveViewDidToggle:(AgentLiveView *)view;
/// 用户点击停止任务按钮
- (void)agentLiveViewDidRequestStop:(AgentLiveView *)view;
/// 用户点击某个 action log 条目
- (void)agentLiveView:(AgentLiveView *)view didSelectActionLog:(ActionLogEntry *)entry;
@end

/// Agent Live — 赛博朋克 2077 风格神经接口终端
/// 在 Chat 页面内嵌展示，调用 AI 时显示 LLM 思考、工具执行等状态
@interface AgentLiveView : UIView

@property (nonatomic, weak, nullable) id<AgentLiveViewDelegate> delegate;

/// 当前任务进度对象
@property (nonatomic, strong, nullable) TaskProgress *taskProgress;

/// 是否展开显示详细步骤 (默认 YES)
@property (nonatomic, assign) BOOL isExpanded;

/// 是否正在执行
@property (nonatomic, assign, readonly) BOOL isRunning;

- (void)updateWithTaskProgress:(TaskProgress *)progress;
- (void)handleActionPlan:(NSDictionary *)data;
- (void)handleActionExecuting:(NSDictionary *)data;
- (void)handleActionResult:(NSDictionary *)data;
- (void)handleTaskComplete:(NSDictionary *)data;
- (void)handleTaskStopped:(NSDictionary *)data;
- (void)handleLLMRequestStart:(NSDictionary *)data;
- (void)handleLLMRequestEnd:(NSDictionary *)data;
- (void)reset;
- (CGFloat)requiredHeight;

@end

NS_ASSUME_NONNULL_END
