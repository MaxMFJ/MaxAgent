#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface ServerConfig : NSObject

@property (nonatomic, copy) NSString *serverURL;
@property (nonatomic, copy, nullable) NSString *authToken;
@property (nonatomic, copy) NSString *sessionId;

+ (instancetype)sharedConfig;

- (void)save;
- (void)load;

- (NSURL *)webSocketURL;
- (NSURL *)healthCheckURL;

@end

NS_ASSUME_NONNULL_END
