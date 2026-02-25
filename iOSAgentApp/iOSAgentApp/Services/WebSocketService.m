#import "WebSocketService.h"
#import "ServerConfig.h"

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

- (void)sendChatMessage:(NSString *)content {
    if (self.connectionState != WebSocketConnectionStateConnected) {
        NSLog(@"[WebSocket] Not connected, cannot send message");
        return;
    }
    
    NSDictionary *message = @{
        @"type": @"chat",
        @"content": content,
        @"session_id": [ServerConfig sharedConfig].sessionId
    };
    
    [self sendJSONMessage:message];
}

- (void)sendAutonomousTask:(NSString *)task {
    if (self.connectionState != WebSocketConnectionStateConnected) {
        NSLog(@"[WebSocket] Not connected, cannot send task");
        return;
    }
    
    NSDictionary *message = @{
        @"type": @"autonomous_task",
        @"task": task,
        @"session_id": [ServerConfig sharedConfig].sessionId
    };
    
    [self sendJSONMessage:message];
}

- (void)createNewSession:(NSString *)sessionId {
    NSString *newSessionId = sessionId ?: [[NSUUID UUID] UUIDString];
    [ServerConfig sharedConfig].sessionId = newSessionId;
    [[ServerConfig sharedConfig] save];
    
    if (self.connectionState == WebSocketConnectionStateConnected) {
        NSDictionary *message = @{
            @"type": @"new_session",
            @"session_id": newSessionId
        };
        [self sendJSONMessage:message];
    }
}

- (void)clearSession {
    if (self.connectionState != WebSocketConnectionStateConnected) {
        return;
    }
    
    NSDictionary *message = @{
        @"type": @"clear_session",
        @"session_id": [ServerConfig sharedConfig].sessionId
    };
    [self sendJSONMessage:message];
}

- (void)sendStopStream {
    if (self.connectionState != WebSocketConnectionStateConnected) {
        return;
    }
    
    NSDictionary *message = @{
        @"type": @"stop",
        @"session_id": [ServerConfig sharedConfig].sessionId
    };
    [self sendJSONMessage:message];
}

// 新增：恢复运行中的任务
- (void)resumeTask:(NSString *)sessionId {
    if (self.connectionState != WebSocketConnectionStateConnected) {
        NSLog(@"[WebSocket] Not connected, cannot resume task");
        return;
    }
    
    NSDictionary *message = @{
        @"type": @"resume_task",
        @"session_id": sessionId ?: [ServerConfig sharedConfig].sessionId
    };
    
    NSLog(@"[WebSocket] Sending resume_task for session: %@", sessionId);
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
            
            NSString *model = json[@"model"];
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
    
    NSString *type = json[@"type"];
    
    if ([type isEqualToString:@"connected"]) {
        self.clientId = json[@"client_id"];
        self.sessionId = json[@"session_id"];
        self.hasRunningTask = [json[@"has_running_task"] boolValue];
        self.runningTaskId = json[@"running_task_id"];
        
        NSLog(@"[WebSocket] Connected with client_id: %@, has_running_task: %d", self.clientId, self.hasRunningTask);
        
        if ([self.delegate respondsToSelector:@selector(webSocketService:didConnectWithClientId:)]) {
            [self.delegate webSocketService:self didConnectWithClientId:self.clientId];
        }
        
        // 如果检测到有运行中的任务，通知代理
        if (self.hasRunningTask && self.runningTaskId) {
            if ([self.delegate respondsToSelector:@selector(webSocketService:didDetectRunningTask:)]) {
                [self.delegate webSocketService:self didDetectRunningTask:self.runningTaskId];
            }
        }
    }
    else if ([type isEqualToString:@"content"]) {
        NSString *content = json[@"content"];
        if (content && [self.delegate respondsToSelector:@selector(webSocketService:didReceiveContent:)]) {
            [self.delegate webSocketService:self didReceiveContent:content];
        }
    }
    else if ([type isEqualToString:@"tool_call"]) {
        NSString *toolName = json[@"name"] ?: json[@"tool_name"];
        NSString *callId = json[@"call_id"] ?: json[@"id"];
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
        NSString *callId = json[@"call_id"] ?: json[@"id"];
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
        NSString *base64 = json[@"base64"];
        NSString *mimeType = json[@"mime_type"] ?: @"image/png";
        
        if (base64.length > 0 && [self.delegate respondsToSelector:@selector(webSocketService:didReceiveImage:mimeType:)]) {
            [self.delegate webSocketService:self didReceiveImage:base64 mimeType:mimeType];
        }
    }
    else if ([type isEqualToString:@"user_message"]) {
        NSString *content = json[@"content"];
        NSString *fromClient = json[@"from_client"];
        NSString *fromClientType = json[@"from_client_type"];
        
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveUserMessage:fromClient:clientType:)]) {
            [self.delegate webSocketService:self didReceiveUserMessage:content fromClient:fromClient clientType:fromClientType];
        }
    }
    else if ([type isEqualToString:@"done"]) {
        NSString *modelName = json[@"model"];
        if ([self.delegate respondsToSelector:@selector(webSocketServiceDidCompleteSend:modelName:)]) {
            [self.delegate webSocketServiceDidCompleteSend:self modelName:modelName];
        }
    }
    else if ([type isEqualToString:@"error"]) {
        NSString *errorMessage = json[@"message"] ?: @"Unknown error";
        if ([self.delegate respondsToSelector:@selector(webSocketService:didReceiveError:)]) {
            [self.delegate webSocketService:self didReceiveError:errorMessage];
        }
    }
    else if ([type isEqualToString:@"pong"]) {
        // Heartbeat response
    }
    else if ([type isEqualToString:@"server_ping"]) {
        // 服务端心跳，回复 pong
        NSDictionary *pongMessage = @{@"type": @"pong"};
        [self sendJSONMessage:pongMessage];
    }
    else if ([type isEqualToString:@"autonomous_task_accepted"]) {
        // 服务端确认接受任务
        NSLog(@"[WebSocket] Autonomous task accepted");
    }
    else if ([type isEqualToString:@"resume_result"]) {
        BOOL found = [json[@"found"] boolValue];
        if (!found) {
            NSString *message = json[@"message"] ?: @"未找到任务";
            NSLog(@"[WebSocket] Resume failed: %@", message);
            if ([self.delegate respondsToSelector:@selector(webSocketService:taskResumeDidFail:)]) {
                [self.delegate webSocketService:self taskResumeDidFail:message];
            }
        } else {
            NSString *taskId = json[@"task_id"];
            NSString *taskDesc = json[@"task_description"];
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
