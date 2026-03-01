#import <UIKit/UIKit.h>
#import "ActionLogEntry.h"

NS_ASSUME_NONNULL_BEGIN

@class TaskProgressView;

@protocol TaskProgressViewDelegate <NSObject>
@optional
/// 用户点击展开/折叠
- (void)taskProgressViewDidToggle:(TaskProgressView *)view;
/// 用户点击停止任务按钮
- (void)taskProgressViewDidRequestStop:(TaskProgressView *)view;
/// 用户点击某个 action log 条目
- (void)taskProgressView:(TaskProgressView *)view didSelectActionLog:(ActionLogEntry *)entry;
@end

/// 任务进度面板视图，显示自主任务的执行进度和步骤列表
/// 可折叠展示，支持进度条和详细步骤
@interface TaskProgressView : UIView

@property (nonatomic, weak, nullable) id<TaskProgressViewDelegate> delegate;

/// 当前任务进度对象
@property (nonatomic, strong, nullable) TaskProgress *taskProgress;

/// 是否展开显示详细步骤 (默认 YES)
@property (nonatomic, assign) BOOL isExpanded;

/// 是否正在执行 (显示加载动画)
@property (nonatomic, assign, readonly) BOOL isRunning;

/// 更新整体任务进度
- (void)updateWithTaskProgress:(TaskProgress *)progress;

/// 处理 action_plan 消息并添加新的 action log 条目
- (void)handleActionPlan:(NSDictionary *)data;

/// 处理 action_executing 消息
- (void)handleActionExecuting:(NSDictionary *)data;

/// 处理 action_result 消息
- (void)handleActionResult:(NSDictionary *)data;

/// 处理 task_complete 消息
- (void)handleTaskComplete:(NSDictionary *)data;

/// 处理 task_stopped 消息
- (void)handleTaskStopped:(NSDictionary *)data;

/// 处理 llm_request_start 消息 (显示 LLM 请求中状态)
- (void)handleLLMRequestStart:(NSDictionary *)data;

/// 处理 llm_request_end 消息
- (void)handleLLMRequestEnd:(NSDictionary *)data;

/// 重置视图状态
- (void)reset;

/// 计算当前视图所需高度
- (CGFloat)requiredHeight;

@end

NS_ASSUME_NONNULL_END
