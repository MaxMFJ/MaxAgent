#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

typedef NS_ENUM(NSInteger, WebSocketConnectionState) {
    WebSocketConnectionStateDisconnected,
    WebSocketConnectionStateConnecting,
    WebSocketConnectionStateConnected,
    WebSocketConnectionStateReconnecting
};

@class WebSocketService;

@protocol WebSocketServiceDelegate <NSObject>

@optional
- (void)webSocketService:(WebSocketService *)service didChangeState:(WebSocketConnectionState)state;
- (void)webSocketService:(WebSocketService *)service didReceiveContent:(NSString *)content;
- (void)webSocketService:(WebSocketService *)service didReceiveToolCall:(NSString *)toolName callId:(NSString *)callId arguments:(NSString *)arguments;
- (void)webSocketService:(WebSocketService *)service didReceiveToolResult:(NSString *)callId result:(NSString *)result;
- (void)webSocketService:(WebSocketService *)service didReceiveImage:(NSString *)base64 mimeType:(NSString *)mimeType;
- (void)webSocketService:(WebSocketService *)service didReceiveUserMessage:(NSString *)content fromClient:(NSString *)clientId clientType:(NSString *)clientType;
- (void)webSocketServiceDidCompleteSend:(WebSocketService *)service modelName:(nullable NSString *)modelName tokenUsage:(nullable NSDictionary<NSString *, NSNumber *> *)tokenUsage;
- (void)webSocketService:(WebSocketService *)service didReceiveError:(NSString *)errorMessage;
/// chat_to_duck 失败（Duck 离线/忙碌等）
- (void)webSocketService:(WebSocketService *)service didReceiveChatToDuckError:(NSString *)errorMessage duckId:(nullable NSString *)duckId;
/// chat_to_duck 已被接受（Duck 开始处理）
- (void)webSocketService:(WebSocketService *)service didAcceptChatToDuck:(NSString *)duckId taskId:(NSString *)taskId;
/// chat_to_duck 结果返回
- (void)webSocketService:(WebSocketService *)service didReceiveChatToDuckResult:(nullable NSString *)output duckId:(NSString *)duckId taskId:(NSString *)taskId success:(BOOL)success error:(nullable NSString *)errorMessage;
- (void)webSocketService:(WebSocketService *)service didConnectWithClientId:(NSString *)clientId sessionId:(NSString *)sessionId hasRunningTask:(BOOL)hasRunningTask runningTaskId:(nullable NSString *)runningTaskId hasRunningChat:(BOOL)hasRunningChat;
- (void)webSocketService:(WebSocketService *)service didConnectWithClientId:(NSString *)clientId sessionId:(NSString *)sessionId hasRunningTask:(BOOL)hasRunningTask runningTaskId:(nullable NSString *)runningTaskId hasRunningChat:(BOOL)hasRunningChat hasBufferedChat:(BOOL)hasBufferedChat bufferedChatCount:(NSInteger)bufferedChatCount;
- (void)webSocketServiceDidClearSession:(WebSocketService *)service;
- (void)webSocketServiceDidStop:(WebSocketService *)service;
- (void)webSocketService:(WebSocketService *)service didReceiveWebAugmentation:(NSString *)augmentationType query:(NSString *)query;
- (void)webSocketService:(WebSocketService *)service didReceiveExecutionLog:(NSString *)toolName level:(NSString *)level message:(NSString *)message;
- (void)webSocketService:(WebSocketService *)service didReceiveSystemNotification:(NSDictionary *)notification unreadCount:(NSInteger)unreadCount;
- (void)webSocketServiceDidReceiveToolsUpdated:(WebSocketService *)service;

- (void)webSocketService:(WebSocketService *)service didDetectRunningTask:(NSString *)taskId;
- (void)webSocketService:(WebSocketService *)service didResumeTaskWithId:(NSString *)taskId description:(NSString *)taskDescription;
- (void)webSocketService:(WebSocketService *)service taskResumeDidFail:(NSString *)message;
- (void)webSocketService:(WebSocketService *)service didResumeChatWithId:(NSString *)taskId status:(NSString *)status bufferedCount:(NSInteger)bufferedCount;
- (void)webSocketService:(WebSocketService *)service didResumeChatWithId:(NSString *)taskId status:(NSString *)status bufferedCount:(NSInteger)bufferedCount messageId:(nullable NSString *)messageId;

/// 服务端下发朗读指令（如 notification(speak)）
- (void)webSocketService:(WebSocketService *)service didReceiveSpeak:(NSString *)text;
/// 自主任务流式 chunk（model_selected, task_start, action_plan, action_result, task_complete 等）
- (void)webSocketService:(WebSocketService *)service didReceiveAutonomousChunk:(NSDictionary *)chunk;
/// LLM 操作状态（llm_request_start, llm_request_end）- 用于显示 chat 进度
- (void)webSocketService:(WebSocketService *)service didReceiveLLMStatus:(NSDictionary *)status;
/// 监控事件（chat/自主任务均会广播，含 task_start、llm_request_start、tool_call 等）
- (void)webSocketService:(WebSocketService *)service didReceiveMonitorEvent:(NSDictionary *)event sessionId:(NSString *)sessionId taskId:(NSString *)taskId taskType:(NSString *)taskType;

@end

@interface WebSocketService : NSObject

@property (nonatomic, weak, nullable) id<WebSocketServiceDelegate> delegate;
@property (nonatomic, readonly) WebSocketConnectionState connectionState;
@property (nonatomic, readonly, nullable) NSString *clientId;
@property (nonatomic, readonly, nullable) NSString *sessionId;

+ (instancetype)sharedService;

- (void)connect;
- (void)disconnect;

- (void)sendChatMessage:(NSString *)content sessionId:(NSString *)sessionId;
/// 发送给子 Duck 的直聊消息（主 Backend 转发）
- (void)sendChatToDuck:(NSString *)content duckId:(NSString *)duckId sessionId:(NSString *)sessionId;
- (void)sendAutonomousTask:(NSString *)task sessionId:(NSString *)sessionId;
- (void)createNewSession:(NSString *)sessionId;
- (void)clearSession:(NSString *)sessionId;
- (void)sendStopStream:(NSString *)sessionId;
- (void)resumeTask:(NSString *)sessionId;
- (void)resumeChat:(NSString *)sessionId;

- (void)checkServerHealth:(void(^)(BOOL available, NSString * _Nullable model))completion;

@end

NS_ASSUME_NONNULL_END
