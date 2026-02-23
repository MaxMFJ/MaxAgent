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
- (void)webSocketServiceDidCompleteSend:(WebSocketService *)service modelName:(nullable NSString *)modelName;
- (void)webSocketService:(WebSocketService *)service didReceiveError:(NSString *)errorMessage;
- (void)webSocketService:(WebSocketService *)service didConnectWithClientId:(NSString *)clientId;
- (void)webSocketServiceDidClearSession:(WebSocketService *)service;

@end

@interface WebSocketService : NSObject

@property (nonatomic, weak, nullable) id<WebSocketServiceDelegate> delegate;
@property (nonatomic, readonly) WebSocketConnectionState connectionState;
@property (nonatomic, readonly, nullable) NSString *clientId;
@property (nonatomic, readonly, nullable) NSString *sessionId;

+ (instancetype)sharedService;

- (void)connect;
- (void)disconnect;

- (void)sendChatMessage:(NSString *)content;
- (void)sendAutonomousTask:(NSString *)task;
- (void)createNewSession:(nullable NSString *)sessionId;
- (void)clearSession;

- (void)checkServerHealth:(void(^)(BOOL available, NSString * _Nullable model))completion;

@end

NS_ASSUME_NONNULL_END
