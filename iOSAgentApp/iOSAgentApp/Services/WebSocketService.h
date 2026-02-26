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
- (void)webSocketService:(WebSocketService *)service didConnectWithClientId:(NSString *)clientId sessionId:(NSString *)sessionId hasRunningTask:(BOOL)hasRunningTask runningTaskId:(nullable NSString *)runningTaskId hasRunningChat:(BOOL)hasRunningChat;
- (void)webSocketServiceDidClearSession:(WebSocketService *)service;
- (void)webSocketServiceDidStop:(WebSocketService *)service;
- (void)webSocketService:(WebSocketService *)service didReceiveWebAugmentation:(NSString *)augmentationType query:(NSString *)query;
- (void)webSocketService:(WebSocketService *)service didReceiveExecutionLog:(NSString *)toolName level:(NSString *)level message:(NSString *)message;
- (void)webSocketService:(WebSocketService *)service didReceiveSystemNotification:(NSDictionary *)notification unreadCount:(NSInteger)unreadCount;
- (void)webSocketServiceDidReceiveToolsUpdated:(WebSocketService *)service;

- (void)webSocketService:(WebSocketService *)service didDetectRunningTask:(NSString *)taskId;
- (void)webSocketService:(WebSocketService *)service didResumeTaskWithId:(NSString *)taskId description:(NSString *)taskDescription;
- (void)webSocketService:(WebSocketService *)service taskResumeDidFail:(NSString *)message;
- (void)webSocketService:(WebSocketService *)service didResumeChatWithId:(NSString *)taskId bufferedCount:(NSInteger)bufferedCount;

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
- (void)sendAutonomousTask:(NSString *)task sessionId:(NSString *)sessionId;
- (void)createNewSession:(NSString *)sessionId;
- (void)clearSession:(NSString *)sessionId;
- (void)sendStopStream:(NSString *)sessionId;
- (void)resumeTask:(NSString *)sessionId;
- (void)resumeChat:(NSString *)sessionId;

- (void)checkServerHealth:(void(^)(BOOL available, NSString * _Nullable model))completion;

@end

NS_ASSUME_NONNULL_END
