#import "SceneDelegate.h"
#import "ViewControllers/ChatViewController.h"
#import "Services/WebSocketService.h"

@interface SceneDelegate ()
@property (nonatomic, assign) UIBackgroundTaskIdentifier bgTask;
@end

@implementation SceneDelegate

- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)connectionOptions {
    if (![scene isKindOfClass:[UIWindowScene class]]) {
        return;
    }
    
    UIWindowScene *windowScene = (UIWindowScene *)scene;
    self.window = [[UIWindow alloc] initWithWindowScene:windowScene];
    
    ChatViewController *chatVC = [[ChatViewController alloc] init];
    UINavigationController *navController = [[UINavigationController alloc] initWithRootViewController:chatVC];
    
    self.window.rootViewController = navController;
    [self.window makeKeyAndVisible];
}

- (void)sceneDidDisconnect:(UIScene *)scene {
}

- (void)sceneDidBecomeActive:(UIScene *)scene {
    // 回到前台：取消后台任务，确保 WebSocket 重连
    if (self.bgTask != UIBackgroundTaskInvalid) {
        [[UIApplication sharedApplication] endBackgroundTask:self.bgTask];
        self.bgTask = UIBackgroundTaskInvalid;
    }
    // 确保连接
    WebSocketService *ws = [WebSocketService sharedService];
    if (ws.connectionState != WebSocketConnectionStateConnected) {
        [ws connect];
    }
}

- (void)sceneWillResignActive:(UIScene *)scene {
}

- (void)sceneWillEnterForeground:(UIScene *)scene {
}

- (void)sceneDidEnterBackground:(UIScene *)scene {
    // 进入后台：申请后台执行时间保持 WebSocket 连接
    self.bgTask = [[UIApplication sharedApplication] beginBackgroundTaskWithName:@"KeepWebSocket" expirationHandler:^{
        NSLog(@"[Background] Task expired, ending background task");
        [[UIApplication sharedApplication] endBackgroundTask:self.bgTask];
        self.bgTask = UIBackgroundTaskInvalid;
    }];
    NSLog(@"[Background] Started background task, remaining time: %.0f seconds",
          [UIApplication sharedApplication].backgroundTimeRemaining);
}

@end
