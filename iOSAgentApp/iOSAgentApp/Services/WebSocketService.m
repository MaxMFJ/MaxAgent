#import "WebSocketService.h"
#import "ServerConfig.h"

// 安全从 JSON 字典取值，避免 NSNull 导致崩溃
static inline BOOL _BoolFromJSON(id obj) {
    if (!obj || obj == [NSNull null]) return NO;
    return [obj isKindOfClass:[NSNumber class]] ? [obj boolValue] : NO;
}
static inline NSInteger _IntegerFromJSON(id obj) {
    if (!obj || obj == [NSNull null]) return 0;
    return [obj isKindOfClass:[NSNumber class]] ? [obj integerValue] : 0;
}
static inline NSString * _Nullable _StringFromJSON(id obj) {
    if (!obj || obj == [NSNull null]) return nil;
    return [obj isKindOfClass:[NSString class]] ? obj : nil;
}

@interface WebSocketService () <NSURLSessionWebSocketDelegate>

@property (nonatomic, strong) NSURLSession *session;
@property (nonatomic, strong, nullable) NSURLSessionWebSocketTask *webSocketTask;
@property (nonatomic, assign) WebSocketConnectionState connectionState;
@property (nonatomic, copy, nullable) NSString *clientId;
@property (nonatomic, copy, nullable) NSString *sessionId;
@property (nonatomic, strong) NSTimer *pingTimer;
@property (nonatomic, assign) NSInteger reconnectAttempts;
@property (nonatomic, assign) BOOL shouldReconnect;
@property (nonatomic, assign) BOOL hasRunningTask;  // 新增：服务端是否有运行中的任务
@property (nonatomic, copy, nullable) NSString *runningTaskId;  // 新增：运行中的任务 ID

@end

@implementation WebSocketService

+ (instancetype)sharedService {
    static WebSocketService *sharedInstance = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        sharedInstance = [[WebSocketService alloc] init];
    });
    return sharedInstance;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        NSURLSessionConfiguration *config = [NSURLSessionConfiguration defaultSessionConfiguration];
        config.timeoutIntervalForRequest = 30;
        config.timeoutIntervalForResource = 300;
        _session = [NSURLSession sessionWithConfiguration:config delegate:self delegateQueue:[NSOperationQueue mainQueue]];
        _connectionState = WebSocketConnectionStateDisconnected;
        _reconnectAttempts = 0;
        _shouldReconnect = YES;
    }
    return self;
}

#pragma mark - Public Methods

- (void)connect {
    if (self.connectionState == WebSocketConnectionStateConnecting || 
        self.connectionState == WebSocketConnectionStateConnected) {
        return;
    }
    
    NSURL *url = [[ServerConfig sharedConfig] webSocketURL];
    if (!url) {
        NSLog(@"[WebSocket] No server URL configured");
        return;
    }
    
    self.shouldReconnect = YES;
    [self updateConnectionState:WebSocketConnectionStateConnecting];
    
    NSLog(@"[WebSocket] Connecting to: %@", url);
    
    self.webSocketTask = [self.session webSocketTaskWithURL:url];
    [self.webSocketTask resume];
    
    [self receiveMessage];
}

- (void)disconnect {
    self.shouldReconnect = NO;
    [self stopPingTimer];
    
    if (self.webSocketTask) {
        [self.webSocketTask cancelWithCloseCode:NSURLSessionWebSocketCloseCodeNormalClosure reason:nil];
        self.webSocketTask = nil;
    }
    
    [self updateConnectionState:WebSocketConnectionStateDisconnected];
}

- (void)sendChatMessage:(NSString *)content sessionId:(NSString *)sessionId {
    if (self.connectionState != WebSocketConnectionStateConnected) {
        NSLog(@"[WebSocket] Not connected, cannot send message");
        return;
    }
    
    NSDictionary *message = @{
        @"type": @"chat",
        @"content": content,
        @"session_id": sessionId
    };
    
    [self sendJSONMessage:message];
}

- (void)sendChatToDuck:(NSString *)content duckId:(NSString *)duckId sessionId:(NSString *)sessionId {
    if (self.connectionState != WebSocketConnectionStateConnected) {
        NSLog(@"[WebSocket] Not connected, cannot send chat_to_duck");
        return;
    }
    
    if (!duckId || duckId.length == 0) {
        NSLog(@"[WebSocket] chat_to_duck requires duck_id");
        return;
    }
    
    NSDictionary *message = @{
        @"type": @"chat_to_duck",
        @"content": content,
        @"duck_id": duckId,
        @"session_id": sessionId
    };
    
    [self sendJSONMessage:message];
    NSLog(@"[WebSocket] Sent chat_to_duck to duck_id=%@", duckId);
}

- (void)createNewSession:(NSString *)sessionId {
    if (!sessionId) {
        NSLog(@"[WebSocket] createNewSession called with nil sessionId");
        return;
    }
    
    if (self.connectionState == WebSocketConnectionStateConnected) {
        NSDictionary *message = @{
            @"type": @"new_session",
            @"session_id": sessionId
        };
        [self sendJSONMessage:message];
        NSLog(@"[WebSocket] Created new session: %@", sessionId);
    }
}

- (void)clearSession:(NSString *)sessionId {
    if (self.connectionState != WebSocketConnectionStateConnected) {
        return;
    }
    
    NSDictionary *message = @{
        @"type": @"clear_session",
        @"session_id": sessionId
    };
    [self sendJSONMessage:message];
}

- (void)sendStopStream:(NSString *)sessionId {
    if (self.connectionState != WebSocketConnectionStateConnected) {
        return;
    }
    
    NSDictionary *message = @{
        @"type": @"stop",
        @"session_id": sessionId
    };
    [self sendJSONMessage:message];
}

- (void)resumeTask:(NSString *)sessionId {
    if (self.connectionState != WebSocketConnectionStateConnected) {
        NSLog(@"[WebSocket] Not connected, cannot resume task");
        return;
    }
    
    if (!sessionId) {
        NSLog(@"[WebSocket] resumeTask called with nil sessionId");
        return;
    }
    
    NSDictionary *message = @{
        @"type": @"resume_task",
        @"session_id": sessionId
    };
    
    NSLog(@"[WebSocket] Sending resume_task for session: %@", sessionId);
    [self sendJSONMessage:message];
}

- (void)resumeChat:(NSString *)sessionId {
    if (self.connectionState != WebSocketConnectionStateConnected) {
        NSLog(@"[WebSocket] Not connected, cannot resume chat");
        return;
    }
    
    if (!sessionId) {
        NSLog(@"[WebSocket] resumeChat called with nil sessionId");
        return;
    }
    
    NSDictionary *message = @{
        @"type": @"resume_chat",
        @"session_id": sessionId
    };
    
    NSLog(@"[WebSocket] Sending resume_chat for session: %@", sessionId);
    [self sendJSONMessage:message];
}

- (void)checkServerHealth:(void (^)(BOOL, NSString * _Nullable))completion {
    NSURL *url = [[ServerConfig sharedConfig] healthCheckURL];
    if (!url) {
        completion(NO, nil);
        return;
    }
    
    NSURLSessionDataTask *task = [self.session dataTaskWithURL:url completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            if (error) {
                completion(NO, nil);
                return;
            }
            
            NSHTTPURLResponse *httpResponse = (NSHTTPURLResponse *)response;
            if (httpResponse.statusCode != 200) {
                completion(NO, nil);
                return;
            }
            
            NSError *jsonError;
            NSDictionary *json = [NSJSONSerialization JSONObjectWithData:data options:0 error:&jsonError];
            if (jsonError || ![json isKindOfClass:[NSDictionary class]]) {
                completion(NO, nil);
                return;
            }
            
            NSString *model = _StringFromJSON(json[@"model"]);
            completion(YES, model);
        });
    }];
    [task resume];
}

#pragma mark - Private Methods

- (void)sendJSONMessage:(NSDictionary *)dict {
    NSError *error;
    NSData *jsonData = [NSJSONSerialization dataWithJSONObject:dict options:0 error:&error];
    if (error) {
        NSLog(@"[WebSocket] JSON serialization error: %@", error);
        return;
    }
    
    NSString *jsonString = [[NSString alloc] initWithData:jsonData encoding:NSUTF8StringEncoding];
    NSURLSessionWebSocketMessage *message = [[NSURLSessionWebSocketMessage alloc] initWithString:jsonString];
    
    [self.webSocketTask sendMessage:message completionHandler:^(NSError *sendError) {
        if (sendError) {
            NSLog(@"[WebSocket] Send error: %@", sendError);
        }
    }];
}

- (void)receiveMessage {
    if (!self.webSocketTask) return;
    
    __weak typeof(self) weakSelf = self;
    [self.webSocketTask receiveMessageWithCompletionHandler:^(NSURLSessionWebSocketMessage *message, NSError *error) {
        __strong typeof(weakSelf) strongSelf = weakSelf;
        if (!strongSelf) return;
        
        if (error) {
            NSLog(@"[WebSocket] Receive error: %@", error);
            [strongSelf handleDisconnection];
            return;
        }
        
        if (message.type == NSURLSessionWebSocketMessageTypeString) {
            [strongSelf handleStringMessage:message.string];
        }
        
        [strongSelf receiveMessage];
    }];
}

- (void)handleStringMessage:(NSString *)string {
    NSError *error;
    NSData *data = [string dataUsingEncoding:NSUTF8StringEncoding];
    NSDictionary *json = [NSJSONSerialization JSONObjectWithData:data options:0 error:&error];
    
    if (error || ![json isKindOfClass:[NSDictionary class]]) {
        NSLog(@"[WebSocket] Failed to parse message: %@", string);
        return;
    }
    
    NSString *type = _StringFromJSON(json[@"type"]);
    
    if ([type isEqualToString:@"connected"]) {
        self.clientId = _StringFromJSON(json[@"client_id"]);
        self.sessionId = _StringFromJSON(json[@"session_id"]);
        self.hasRunningTask = _BoolFromJSON(json[@"has_running_task"]);
        self.runningTaskId = _StringFromJSON(json[@"running_task_id"]);
        BOOL hasRunningChat = _BoolFromJSON(json[@"has_running_chat"]);
        BOOL hasBufferedChat = _BoolFromJSON(json[@"has_buffered_chat"]);
        NSInteger bufferedChatCount = _IntegerFromJSON(json[@"buffered_chat_count"]);
        
        NSLog(@"[WebSocket] Connected with client_id: %@, session_id: %@, has_running_task: %d, has_running_chat: %d, has_buffered_chat: %d, buffered_count: %ld", 
              self.clientId, self.sessionId, self.hasRunningTask, hasRunningChat, hasBufferedChat, (long)bufferedChatCount);
        
        if ([self.delegate respondsToSelector:@selector(webSocketService:didConnectWithClientId:sessionId:hasRunningTask:runningTaskId:hasRunningChat:hasBufferedChat:bufferedChatCount:)]) {
            [self.delegate webSocketService:self 
                        didConnectWithClientId:self.clientId 
                                     sessionId:self.sessionId 
                               hasRunningTask:self.hasRunningTask 
                                runningTaskId:self.runningTaskId 
                              hasRunningChat:hasRunningChat
                             hasBufferedChat:hasBufferedChat
                           bufferedChatCount:bufferedChatCount];
        } else if ([self.delegate respondsToSelector:@selector(webSocketService:didConnectWithClientId:sessionId:hasRunningTask:runningTaskId:hasRunningChat:)]) {
            // 向后兼容旧的 delegate 方法
            [self.delegate webSocketService:self 
                        didConnectWithClientId:self.clientId 
                                     sessionId:self.sessionId 
                               hasRunningTask:self.hasRunningTask 
                                runningTaskId:self.runningTaskId 
                              hasRunningChat:hasRunningChat];
        }
        
        if (self.hasRunningTask && self.runningTaskId) {
            if ([self.delegate respondsToSelector:@selector(webSocketService:didDetectRunningTask:)]) {
                [self.delegate webSocketService:self didDetectRunningTask:self.runningTaskId];
            }
        }
    }
    else if ([type isEqualToString:@"content"]) {
        NSString *content = _StringFromJSON(json[@"content"]);
        if (content && [self.delegate respondsToSelector:@selector(webSocketService:didReceiveContent:)]) {
            [self.delegate webSocketService:self didReceiveContent:content];
        }
    }
    else if ([type isEqualToString:@"tool_call"]) {
        NSString *toolName = _StringFromJSON(json[@"name"]) ?: _StringFromJSON(json[@"tool_name"]);
        NSString *callId = _StringFromJSON(json[@"call_id"]) ?: _StringFromJSON(json[@"id"]);
        id args = json[@"arguments"] ?: json[@"args"];
        NSString *argsString = @"";
        
        if ([args isKindOfClass:[NSString class]]) {
            argsString = args;
        } else if ([args isKindOfClass:[NSDictionary class]]) {
            NSData *argsData = [NSJSONSerialization dataWithJSONObject:args options:NSJSONWritingPrettyPrinted error:nil];
            argsString = [[NSString alloc] initWithData:argsData encoding:NSUTF8StringEncoding];
        }
        
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveToolCall:callId:arguments:)]) {
            [self.delegate webSocketService:self didReceiveToolCall:toolName callId:callId arguments:argsString];
        }
    }
    else if ([type isEqualToString:@"tool_result"]) {
        NSString *callId = _StringFromJSON(json[@"call_id"]) ?: _StringFromJSON(json[@"id"]);
        id result = json[@"result"];
        NSString *resultString = @"";
        
        if ([result isKindOfClass:[NSString class]]) {
            resultString = result;
        } else if (result) {
            NSData *resultData = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil];
            resultString = [[NSString alloc] initWithData:resultData encoding:NSUTF8StringEncoding];
        }
        
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveToolResult:result:)]) {
            [self.delegate webSocketService:self didReceiveToolResult:callId result:resultString];
        }
    }
    else if ([type isEqualToString:@"image"]) {
        NSString *base64 = _StringFromJSON(json[@"base64"]);
        NSString *mimeType = _StringFromJSON(json[@"mime_type"]) ?: @"image/png";
        
        if (base64.length > 0 && [self.delegate respondsToSelector:@selector(webSocketService:didReceiveImage:mimeType:)]) {
            [self.delegate webSocketService:self didReceiveImage:base64 mimeType:mimeType];
        }
    }
    else if ([type isEqualToString:@"user_message"]) {
        NSString *content = _StringFromJSON(json[@"content"]);
        NSString *fromClient = _StringFromJSON(json[@"from_client"]);
        NSString *fromClientType = _StringFromJSON(json[@"from_client_type"]);
        
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveUserMessage:fromClient:clientType:)]) {
            [self.delegate webSocketService:self didReceiveUserMessage:content fromClient:fromClient clientType:fromClientType];
        }
    }
    else if ([type isEqualToString:@"done"]) {
        NSString *modelName = _StringFromJSON(json[@"model"]);
        NSDictionary *tokenUsage = json[@"usage"];
        if ([self.delegate respondsToSelector:@selector(webSocketServiceDidCompleteSend:modelName:tokenUsage:)]) {
            [self.delegate webSocketServiceDidCompleteSend:self modelName:modelName tokenUsage:tokenUsage];
        }
    }
    else if ([type isEqualToString:@"error"]) {
        NSString *errorMessage = _StringFromJSON(json[@"message"]) ?: @"Unknown error";
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveError:)]) {
            [self.delegate webSocketService:self didReceiveError:errorMessage];
        }
    }
    else if ([type isEqualToString:@"chat_to_duck_error"]) {
        NSString *errorMessage = _StringFromJSON(json[@"message"]) ?: @"该 Duck 不可用";
        NSString *duckId = _StringFromJSON(json[@"duck_id"]);
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveChatToDuckError:duckId:)]) {
            [self.delegate webSocketService:self didReceiveChatToDuckError:errorMessage duckId:duckId];
        } else if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveError:)]) {
            [self.delegate webSocketService:self didReceiveError:errorMessage];
        }
    }
    else if ([type isEqualToString:@"chat_to_duck_accepted"]) {
        NSString *duckId = _StringFromJSON(json[@"duck_id"]) ?: @"";
        NSString *taskId = _StringFromJSON(json[@"task_id"]) ?: @"";
        if ([self.delegate respondsToSelector:@selector(webSocketService:didAcceptChatToDuck:taskId:)]) {
            [self.delegate webSocketService:self didAcceptChatToDuck:duckId taskId:taskId];
        }
        NSLog(@"[WebSocket] chat_to_duck_accepted: duck_id=%@ task_id=%@", duckId, taskId);
    }
    else if ([type isEqualToString:@"chat_to_duck_result"]) {
        NSString *duckId = _StringFromJSON(json[@"duck_id"]) ?: @"";
        NSString *taskId = _StringFromJSON(json[@"task_id"]) ?: @"";
        BOOL success = [json[@"success"] isKindOfClass:[NSNumber class]] ? [json[@"success"] boolValue] : NO;
        NSString *output = _StringFromJSON(json[@"output"]);
        NSString *errorMessage = _StringFromJSON(json[@"error"]);
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveChatToDuckResult:duckId:taskId:success:error:)]) {
            [self.delegate webSocketService:self didReceiveChatToDuckResult:output duckId:duckId taskId:taskId success:success error:errorMessage];
        }
        NSLog(@"[WebSocket] chat_to_duck_result: duck_id=%@ task_id=%@ success=%d", duckId, taskId, success);
    }
    else if ([type isEqualToString:@"duck_task_complete"]) {
        NSString *content = _StringFromJSON(json[@"content"]) ?: @"";
        NSString *sessionId = _StringFromJSON(json[@"session_id"]) ?: @"";
        BOOL success = [json[@"success"] isKindOfClass:[NSNumber class]] ? [json[@"success"] boolValue] : NO;
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveDuckTaskComplete:success:sessionId:)]) {
            [self.delegate webSocketService:self didReceiveDuckTaskComplete:content success:success sessionId:sessionId];
        }
        NSLog(@"[WebSocket] duck_task_complete: session_id=%@ success=%d", sessionId, success);
    }
    // MARK: - Group Chat
    else if ([type isEqualToString:@"group_chat_created"]) {
        NSDictionary *groupData = [json[@"group"] isKindOfClass:[NSDictionary class]] ? json[@"group"] : @{};
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveGroupChatCreated:)]) {
            [self.delegate webSocketService:self didReceiveGroupChatCreated:groupData];
        }
        NSLog(@"[WebSocket] group_chat_created: group_id=%@", groupData[@"group_id"]);
    }
    else if ([type isEqualToString:@"group_message"]) {
        NSString *groupId = _StringFromJSON(json[@"group_id"]) ?: @"";
        NSDictionary *msgData = [json[@"message"] isKindOfClass:[NSDictionary class]] ? json[@"message"] : @{};
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveGroupMessage:message:)]) {
            [self.delegate webSocketService:self didReceiveGroupMessage:groupId message:msgData];
        }
    }
    else if ([type isEqualToString:@"group_status_update"]) {
        NSString *groupId = _StringFromJSON(json[@"group_id"]) ?: @"";
        NSString *status = _StringFromJSON(json[@"status"]) ?: @"";
        NSDictionary *taskSummary = [json[@"task_summary"] isKindOfClass:[NSDictionary class]] ? json[@"task_summary"] : @{};
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveGroupStatusUpdate:status:taskSummary:)]) {
            [self.delegate webSocketService:self didReceiveGroupStatusUpdate:groupId status:status taskSummary:taskSummary];
        }
        NSLog(@"[WebSocket] group_status_update: group_id=%@ status=%@", groupId, status);
    }
    else if ([type isEqualToString:@"pong"]) {
        // Heartbeat response
    }
    else if ([type isEqualToString:@"server_ping"]) {
        // 服务端心跳，回复 pong
        NSDictionary *pongMessage = @{@"type": @"pong"};
        [self sendJSONMessage:pongMessage];
    }
    else if ([type isEqualToString:@"resume_result"]) {
        BOOL found = _BoolFromJSON(json[@"found"]);
        if (!found) {
            NSString *message = _StringFromJSON(json[@"message"]) ?: @"未找到任务";
            NSLog(@"[WebSocket] Resume failed: %@", message);
            if ([self.delegate respondsToSelector:@selector(webSocketService:taskResumeDidFail:)]) {
                [self.delegate webSocketService:self taskResumeDidFail:message];
            }
        } else {
            NSString *taskId = _StringFromJSON(json[@"task_id"]);
            NSString *taskDesc = _StringFromJSON(json[@"task_description"]);
            NSLog(@"[WebSocket] Task resume successful: %@", taskId);
            if ([self.delegate respondsToSelector:@selector(webSocketService:didResumeTaskWithId:description:)]) {
                [self.delegate webSocketService:self didResumeTaskWithId:taskId description:taskDesc];
            }
        }
    }
    else if ([type isEqualToString:@"resume_streaming"]) {
        // 历史回放完成，后续是实时流
        NSLog(@"[WebSocket] Resume streaming started");
    }
    else if ([type isEqualToString:@"session_created"]) {
        NSLog(@"[WebSocket] Session created");
    }
    else if ([type isEqualToString:@"session_cleared"]) {
        if ([self.delegate respondsToSelector:@selector(webSocketServiceDidClearSession:)]) {
            [self.delegate webSocketServiceDidClearSession:self];
        }
    }
    else if ([type isEqualToString:@"stopped"]) {
        if ([self.delegate respondsToSelector:@selector(webSocketServiceDidStop:)]) {
            [self.delegate webSocketServiceDidStop:self];
        }
    }
    else if ([type isEqualToString:@"web_augmentation"]) {
        NSString *augType = _StringFromJSON(json[@"augmentation_type"]) ?: @"unknown";
        NSString *query = _StringFromJSON(json[@"query"]) ?: @"";
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveWebAugmentation:query:)]) {
            [self.delegate webSocketService:self didReceiveWebAugmentation:augType query:query];
        }
    }
    else if ([type isEqualToString:@"execution_log"]) {
        NSString *toolName = _StringFromJSON(json[@"tool_name"]) ?: @"";
        NSString *level = _StringFromJSON(json[@"level"]) ?: @"info";
        NSString *logMessage = _StringFromJSON(json[@"message"]) ?: @"";
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveExecutionLog:level:message:)]) {
            [self.delegate webSocketService:self didReceiveExecutionLog:toolName level:level message:logMessage];
        }
    }
    else if ([type isEqualToString:@"system_notification"]) {
        NSDictionary *notification = json[@"notification"];
        NSInteger unreadCount = _IntegerFromJSON(json[@"unread_count"]);
        if (notification && [self.delegate respondsToSelector:@selector(webSocketService:didReceiveSystemNotification:unreadCount:)]) {
            [self.delegate webSocketService:self didReceiveSystemNotification:notification unreadCount:unreadCount];
        }
    }
    else if ([type isEqualToString:@"tools_updated"]) {
        if ([self.delegate respondsToSelector:@selector(webSocketServiceDidReceiveToolsUpdated:)]) {
            [self.delegate webSocketServiceDidReceiveToolsUpdated:self];
        }
    }
    else if ([type isEqualToString:@"resume_chat_result"]) {
        BOOL found = _BoolFromJSON(json[@"found"]);
        if (found) {
            NSString *taskId = _StringFromJSON(json[@"task_id"]);
            NSString *status = _StringFromJSON(json[@"status"]) ?: @"unknown";
            NSInteger bufferedCount = _IntegerFromJSON(json[@"buffered_count"]);
            NSString *messageId = _StringFromJSON(json[@"last_message_id"]);
            NSLog(@"[WebSocket] Chat resume successful: task=%@, status=%@, buffered=%ld, msgId=%@", taskId, status, (long)bufferedCount, messageId);
            // 优先调用带 messageId 的新方法
            if ([self.delegate respondsToSelector:@selector(webSocketService:didResumeChatWithId:status:bufferedCount:messageId:)]) {
                [self.delegate webSocketService:self didResumeChatWithId:taskId status:status bufferedCount:bufferedCount messageId:messageId];
            } else if ([self.delegate respondsToSelector:@selector(webSocketService:didResumeChatWithId:status:bufferedCount:)]) {
                [self.delegate webSocketService:self didResumeChatWithId:taskId status:status bufferedCount:bufferedCount];
            }
        } else {
            NSString *message = _StringFromJSON(json[@"message"]) ?: @"未找到 chat 任务";
            NSLog(@"[WebSocket] Chat resume failed: %@", message);
            if ([self.delegate respondsToSelector:@selector(webSocketService:taskResumeDidFail:)]) {
                [self.delegate webSocketService:self taskResumeDidFail:message];
            }
        }
    }
    else if ([type isEqualToString:@"resume_chat_streaming"]) {
        NSLog(@"[WebSocket] Resume chat streaming started");
    }
    else if ([type isEqualToString:@"speak"]) {
        NSString *text = _StringFromJSON(json[@"text"]) ?: _StringFromJSON(json[@"message"]) ?: @"";
        if (text.length > 0 && [self.delegate respondsToSelector:@selector(webSocketService:didReceiveSpeak:)]) {
            [self.delegate webSocketService:self didReceiveSpeak:text];
        }
    }
    else if ([type isEqualToString:@"llm_request_start"] || [type isEqualToString:@"llm_request_end"]) {
        // LLM 操作状态
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveLLMStatus:)]) {
            [self.delegate webSocketService:self didReceiveLLMStatus:json];
        }
    }
    else if ([type isEqualToString:@"model_selected"] || [type isEqualToString:@"task_start"] ||
             [type isEqualToString:@"task_analysis"] || [type isEqualToString:@"action_plan"] ||
             [type isEqualToString:@"action_executing"] || [type isEqualToString:@"action_result"] ||
             [type isEqualToString:@"reflect_start"] || [type isEqualToString:@"reflect_result"] ||
             [type isEqualToString:@"task_complete"] || [type isEqualToString:@"task_stopped"] ||
             [type isEqualToString:@"progress_update"]) {
        // These chunks now arrive through chat flow — handled by content/done delegates
        NSLog(@"[WebSocket] Execution chunk: %@", type);
    }
    else if ([type isEqualToString:@"monitor_event"]) {
        NSDictionary *event = json[@"event"];
        NSString *sourceSession = _StringFromJSON(json[@"source_session"]);
        NSString *taskId = _StringFromJSON(json[@"task_id"]);
        NSString *taskType = _StringFromJSON(json[@"task_type"]) ?: @"chat";
        if (event && [event isKindOfClass:[NSDictionary class]] &&
            [self.delegate respondsToSelector:@selector(webSocketService:didReceiveMonitorEvent:sessionId:taskId:taskType:)]) {
            [self.delegate webSocketService:self didReceiveMonitorEvent:event sessionId:sourceSession ?: @"" taskId:taskId ?: @"" taskType:taskType];
        }
    }
    else {
        NSLog(@"[WebSocket] Unhandled message type: %@", type);
    }
}

- (void)updateConnectionState:(WebSocketConnectionState)state {
    if (_connectionState != state) {
        _connectionState = state;
        
        if ([self.delegate respondsToSelector:@selector(webSocketService:didChangeState:)]) {
            [self.delegate webSocketService:self didChangeState:state];
        }
    }
}

- (void)handleDisconnection {
    [self stopPingTimer];
    
    if (self.shouldReconnect && self.reconnectAttempts < 5) {
        [self updateConnectionState:WebSocketConnectionStateReconnecting];
        self.reconnectAttempts++;
        
        NSTimeInterval delay = MIN(pow(2, self.reconnectAttempts), 30);
        NSLog(@"[WebSocket] Will reconnect in %.0f seconds (attempt %ld)", delay, (long)self.reconnectAttempts);
        
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(delay * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
            if (self.shouldReconnect) {
                [self connect];
            }
        });
    } else {
        [self updateConnectionState:WebSocketConnectionStateDisconnected];
    }
}

- (void)startPingTimer {
    [self stopPingTimer];
    
    self.pingTimer = [NSTimer scheduledTimerWithTimeInterval:10.0 repeats:YES block:^(NSTimer *timer) {
        if (self.connectionState == WebSocketConnectionStateConnected) {
            [self sendJSONMessage:@{@"type": @"ping"}];
        }
    }];
}

- (void)stopPingTimer {
    [self.pingTimer invalidate];
    self.pingTimer = nil;
}

#pragma mark - NSURLSessionWebSocketDelegate

- (void)URLSession:(NSURLSession *)session webSocketTask:(NSURLSessionWebSocketTask *)webSocketTask didOpenWithProtocol:(NSString *)protocol {
    NSLog(@"[WebSocket] Connection opened");
    self.reconnectAttempts = 0;
    [self updateConnectionState:WebSocketConnectionStateConnected];
    [self startPingTimer];
}

- (void)URLSession:(NSURLSession *)session webSocketTask:(NSURLSessionWebSocketTask *)webSocketTask didCloseWithCode:(NSURLSessionWebSocketCloseCode)closeCode reason:(NSData *)reason {
    NSLog(@"[WebSocket] Connection closed with code: %ld", (long)closeCode);
    [self handleDisconnection];
}

- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task didCompleteWithError:(NSError *)error {
    if (error) {
        NSLog(@"[WebSocket] Task completed with error: %@", error);
        [self handleDisconnection];
    }
}

@end
