#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Action 执行状态
typedef NS_ENUM(NSInteger, ActionLogStatus) {
    ActionLogStatusPending,     // 等待执行
    ActionLogStatusExecuting,   // 执行中
    ActionLogStatusSuccess,     // 成功
    ActionLogStatusFailed       // 失败
};

/// 单个 Action 的执行日志条目
@interface ActionLogEntry : NSObject

@property (nonatomic, copy) NSString *actionId;
@property (nonatomic, copy) NSString *actionType;
@property (nonatomic, copy, nullable) NSString *reasoning;
@property (nonatomic, assign) NSInteger iteration;
@property (nonatomic, assign) ActionLogStatus status;
@property (nonatomic, copy, nullable) NSString *output;
@property (nonatomic, copy, nullable) NSString *error;
@property (nonatomic, assign) NSInteger executionTimeMs;
@property (nonatomic, strong) NSDate *timestamp;
@property (nonatomic, copy, nullable) NSString *screenshotPath;
@property (nonatomic, copy, nullable) NSString *screenshotBase64;

/// 从 action_plan 消息创建
+ (instancetype)entryFromActionPlan:(NSDictionary *)planData iteration:(NSInteger)iteration;

/// 从 action_result 消息更新
- (void)updateWithActionResult:(NSDictionary *)resultData;

/// 获取状态图标
- (NSString *)statusIcon;

/// 获取简短描述
- (NSString *)shortDescription;

@end

/// 任务整体进度
@interface TaskProgress : NSObject

@property (nonatomic, copy) NSString *taskId;
@property (nonatomic, copy) NSString *taskDescription;
@property (nonatomic, assign) NSInteger currentIteration;
@property (nonatomic, assign) NSInteger maxIterations;
@property (nonatomic, assign) NSInteger totalActions;
@property (nonatomic, assign) NSInteger successfulActions;
@property (nonatomic, assign) NSInteger failedActions;
@property (nonatomic, assign) BOOL isRunning;
@property (nonatomic, assign) BOOL isCompleted;
@property (nonatomic, copy, nullable) NSString *modelType;
@property (nonatomic, copy, nullable) NSString *modelReason;
@property (nonatomic, strong) NSMutableArray<ActionLogEntry *> *actionLogs;
@property (nonatomic, strong) NSDate *startTime;
@property (nonatomic, strong, nullable) NSDate *endTime;
@property (nonatomic, copy, nullable) NSString *finalSummary;
@property (nonatomic, assign) BOOL finalSuccess;

/// 是否正在执行 LLM 请求
@property (nonatomic, assign) BOOL isLLMRequesting;
@property (nonatomic, assign) NSInteger llmRequestStartTime;

+ (instancetype)progressWithTaskId:(NSString *)taskId description:(NSString *)description;

/// 处理 task_start 消息
- (void)handleTaskStart:(NSDictionary *)data;

/// 处理 model_selected 消息
- (void)handleModelSelected:(NSDictionary *)data;

/// 处理 action_plan 消息，返回新创建的 ActionLogEntry
- (ActionLogEntry *)handleActionPlan:(NSDictionary *)data;

/// 处理 action_executing 消息
- (void)handleActionExecuting:(NSDictionary *)data;

/// 处理 action_result 消息
- (void)handleActionResult:(NSDictionary *)data;

/// 处理 progress_update 消息
- (void)handleProgressUpdate:(NSDictionary *)data;

/// 处理 task_complete 消息
- (void)handleTaskComplete:(NSDictionary *)data;

/// 处理 task_stopped 消息
- (void)handleTaskStopped:(NSDictionary *)data;

/// 处理 llm_request_start 消息
- (void)handleLLMRequestStart:(NSDictionary *)data;

/// 处理 llm_request_end 消息
- (void)handleLLMRequestEnd:(NSDictionary *)data;

/// 记录 chat 工具调用（用于 monitor_event 中的 tool_call，供 Agent Live 展示）
- (void)recordToolCallForDisplay:(NSString *)toolName;

/// 获取进度百分比 (0.0 - 1.0)
- (CGFloat)progressPercentage;

/// 获取成功率
- (CGFloat)successRate;

/// 查找特定 actionId 的 ActionLogEntry
- (nullable ActionLogEntry *)findEntryByActionId:(NSString *)actionId;

@end

NS_ASSUME_NONNULL_END
