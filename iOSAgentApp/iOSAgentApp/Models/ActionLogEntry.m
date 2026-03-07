#import "ActionLogEntry.h"

@implementation ActionLogEntry

+ (instancetype)entryFromActionPlan:(NSDictionary *)planData iteration:(NSInteger)iteration {
    ActionLogEntry *entry = [[ActionLogEntry alloc] init];
    
    NSDictionary *action = planData[@"action"];
    if (action) {
        entry.actionType = action[@"action_type"] ?: @"unknown";
        entry.reasoning = action[@"reasoning"];
        entry.actionId = action[@"action_id"] ?: [[NSUUID UUID] UUIDString];
        
        // 解析 params 中的信息
        NSDictionary *params = action[@"params"];
        if (params && [params isKindOfClass:[NSDictionary class]]) {
            // 可以在此提取特定参数
        }
    } else {
        entry.actionType = planData[@"action_type"] ?: @"unknown";
        entry.actionId = planData[@"action_id"] ?: [[NSUUID UUID] UUIDString];
    }
    
    entry.iteration = iteration;
    entry.status = ActionLogStatusPending;
    entry.timestamp = [NSDate date];
    
    return entry;
}

- (void)updateWithActionResult:(NSDictionary *)resultData {
    BOOL success = [resultData[@"success"] boolValue];
    self.status = success ? ActionLogStatusSuccess : ActionLogStatusFailed;
    
    if (resultData[@"output"]) {
        id output = resultData[@"output"];
        if ([output isKindOfClass:[NSString class]]) {
            self.output = output;
        } else if ([output isKindOfClass:[NSDictionary class]] || [output isKindOfClass:[NSArray class]]) {
            NSData *jsonData = [NSJSONSerialization dataWithJSONObject:output options:0 error:nil];
            if (jsonData) {
                self.output = [[NSString alloc] initWithData:jsonData encoding:NSUTF8StringEncoding];
            }
        }
    }
    
    self.error = resultData[@"error"];
    
    NSNumber *execTime = resultData[@"execution_time_ms"];
    if (execTime) {
        self.executionTimeMs = [execTime integerValue];
    }
    
    // 处理截图
    if (resultData[@"screenshot_path"]) {
        self.screenshotPath = resultData[@"screenshot_path"];
    }
    if (resultData[@"image_base64"]) {
        self.screenshotBase64 = resultData[@"image_base64"];
    }
}

- (NSString *)statusIcon {
    switch (self.status) {
        case ActionLogStatusPending:
            return @"⏳";
        case ActionLogStatusExecuting:
            return @"🔄";
        case ActionLogStatusSuccess:
            return @"✅";
        case ActionLogStatusFailed:
            return @"❌";
    }
}

- (NSString *)shortDescription {
    NSString *typeDisplay = self.actionType;
    
    // 友好显示 action type
    NSDictionary *typeMap = @{
        @"run_shell": @"执行命令",
        @"read_file": @"读取文件",
        @"write_file": @"写入文件",
        @"take_screenshot": @"截图",
        @"call_tool": @"调用工具",
        @"think": @"思考",
        @"finish": @"完成",
        @"search_web": @"搜索",
        @"browser_action": @"浏览器"
    };
    
    if (typeMap[self.actionType]) {
        typeDisplay = typeMap[self.actionType];
    }
    
    if (self.reasoning && self.reasoning.length > 0) {
        NSString *truncated = self.reasoning;
        if (truncated.length > 50) {
            truncated = [[truncated substringToIndex:47] stringByAppendingString:@"..."];
        }
        return [NSString stringWithFormat:@"%@ → %@", typeDisplay, truncated];
    }
    
    return typeDisplay;
}

@end

#pragma mark - TaskProgress

@implementation TaskProgress

+ (instancetype)progressWithTaskId:(NSString *)taskId description:(NSString *)description {
    TaskProgress *progress = [[TaskProgress alloc] init];
    progress.taskId = taskId;
    progress.taskDescription = description;
    progress.actionLogs = [NSMutableArray array];
    progress.currentIteration = 0;
    progress.maxIterations = 50;
    progress.totalActions = 0;
    progress.successfulActions = 0;
    progress.failedActions = 0;
    progress.isRunning = NO;
    progress.isCompleted = NO;
    progress.isLLMRequesting = NO;
    return progress;
}

- (void)handleTaskStart:(NSDictionary *)data {
    self.taskId = data[@"task_id"] ?: self.taskId;
    if (data[@"task"]) {
        self.taskDescription = data[@"task"];
    }
    if (data[@"max_iterations"]) {
        self.maxIterations = [data[@"max_iterations"] integerValue];
    }
    self.isRunning = YES;
    self.startTime = [NSDate date];
}

- (void)handleModelSelected:(NSDictionary *)data {
    self.modelType = data[@"model_type"];
    self.modelReason = data[@"reason"];
}

- (ActionLogEntry *)handleActionPlan:(NSDictionary *)data {
    NSInteger iteration = [data[@"iteration"] integerValue];
    self.currentIteration = iteration;
    
    if (data[@"max_iterations"]) {
        self.maxIterations = [data[@"max_iterations"] integerValue];
    }
    
    ActionLogEntry *entry = [ActionLogEntry entryFromActionPlan:data iteration:iteration];
    [self.actionLogs addObject:entry];
    self.totalActions++;
    
    return entry;
}

- (void)handleActionExecuting:(NSDictionary *)data {
    NSString *actionId = data[@"action_id"];
    if (actionId) {
        ActionLogEntry *entry = [self findEntryByActionId:actionId];
        if (entry) {
            entry.status = ActionLogStatusExecuting;
        }
    }
}

- (void)handleActionResult:(NSDictionary *)data {
    NSString *actionId = data[@"action_id"];
    
    // 查找对应的 entry
    ActionLogEntry *entry = nil;
    if (actionId) {
        entry = [self findEntryByActionId:actionId];
    }
    
    // 如果找不到，使用最后一个 pending/executing 的 entry
    if (!entry && self.actionLogs.count > 0) {
        for (NSInteger i = self.actionLogs.count - 1; i >= 0; i--) {
            ActionLogEntry *e = self.actionLogs[i];
            if (e.status == ActionLogStatusPending || e.status == ActionLogStatusExecuting) {
                entry = e;
                break;
            }
        }
    }
    
    if (entry) {
        [entry updateWithActionResult:data];
        
        if (entry.status == ActionLogStatusSuccess) {
            self.successfulActions++;
        } else if (entry.status == ActionLogStatusFailed) {
            self.failedActions++;
        }
    }
}

- (void)handleProgressUpdate:(NSDictionary *)data {
    if (data[@"iteration"]) {
        self.currentIteration = [data[@"iteration"] integerValue];
    }
    if (data[@"max_iterations"]) {
        self.maxIterations = [data[@"max_iterations"] integerValue];
    }
}

- (void)handleTaskComplete:(NSDictionary *)data {
    self.isRunning = NO;
    self.isCompleted = YES;
    self.endTime = [NSDate date];
    self.finalSuccess = [data[@"success"] boolValue];
    self.finalSummary = data[@"summary"];
    
    if (data[@"iterations"]) {
        self.currentIteration = [data[@"iterations"] integerValue];
    }
}

- (void)handleTaskStopped:(NSDictionary *)data {
    self.isRunning = NO;
    self.isCompleted = YES;
    self.endTime = [NSDate date];
    self.finalSuccess = NO;
    self.finalSummary = data[@"message"];
    
    if (data[@"iterations"]) {
        self.currentIteration = [data[@"iterations"] integerValue];
    }
}

- (void)handleLLMRequestStart:(NSDictionary *)data {
    self.isLLMRequesting = YES;
    self.llmRequestStartTime = (NSInteger)([[NSDate date] timeIntervalSince1970] * 1000);
}

- (void)handleLLMRequestEnd:(NSDictionary *)data {
    self.isLLMRequesting = NO;
}

- (void)recordToolCallForDisplay:(NSString *)toolName {
    if (!toolName || toolName.length == 0) return;
    ActionLogEntry *entry = [[ActionLogEntry alloc] init];
    entry.actionType = toolName;
    entry.actionId = [[NSUUID UUID] UUIDString];
    entry.iteration = 1;
    entry.status = ActionLogStatusExecuting;
    entry.timestamp = [NSDate date];
    [self.actionLogs addObject:entry];
}

- (CGFloat)progressPercentage {
    if (self.maxIterations <= 0) return 0.0;
    return MIN(1.0, (CGFloat)self.currentIteration / (CGFloat)self.maxIterations);
}

- (CGFloat)successRate {
    if (self.totalActions <= 0) return 1.0;
    return (CGFloat)self.successfulActions / (CGFloat)self.totalActions;
}

- (nullable ActionLogEntry *)findEntryByActionId:(NSString *)actionId {
    for (ActionLogEntry *entry in self.actionLogs) {
        if ([entry.actionId isEqualToString:actionId]) {
            return entry;
        }
    }
    return nil;
}

@end
