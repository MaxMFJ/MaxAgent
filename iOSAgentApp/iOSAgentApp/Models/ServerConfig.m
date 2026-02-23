#import "ServerConfig.h"

static NSString * const kServerURLKey = @"ServerURL";
static NSString * const kAuthTokenKey = @"AuthToken";
static NSString * const kSessionIdKey = @"SessionId";

@implementation ServerConfig

+ (instancetype)sharedConfig {
    static ServerConfig *sharedInstance = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        sharedInstance = [[ServerConfig alloc] init];
        [sharedInstance load];
    });
    return sharedInstance;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _serverURL = @"";
        _authToken = nil;
        _sessionId = [[NSUUID UUID] UUIDString];
    }
    return self;
}

- (void)save {
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    [defaults setObject:self.serverURL forKey:kServerURLKey];
    if (self.authToken) {
        [defaults setObject:self.authToken forKey:kAuthTokenKey];
    } else {
        [defaults removeObjectForKey:kAuthTokenKey];
    }
    [defaults setObject:self.sessionId forKey:kSessionIdKey];
    [defaults synchronize];
}

- (void)load {
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    NSString *savedURL = [defaults stringForKey:kServerURLKey];
    if (savedURL) {
        self.serverURL = savedURL;
    }
    self.authToken = [defaults stringForKey:kAuthTokenKey];
    NSString *savedSessionId = [defaults stringForKey:kSessionIdKey];
    if (savedSessionId) {
        self.sessionId = savedSessionId;
    }
}

- (NSURL *)webSocketURL {
    if (self.serverURL.length == 0) {
        return nil;
    }
    
    NSString *wsURL = self.serverURL;
    
    if ([wsURL hasPrefix:@"https://"]) {
        wsURL = [wsURL stringByReplacingOccurrencesOfString:@"https://" withString:@"wss://"];
    } else if ([wsURL hasPrefix:@"http://"]) {
        wsURL = [wsURL stringByReplacingOccurrencesOfString:@"http://" withString:@"ws://"];
    } else if (![wsURL hasPrefix:@"ws://"] && ![wsURL hasPrefix:@"wss://"]) {
        wsURL = [@"wss://" stringByAppendingString:wsURL];
    }
    
    if (![wsURL hasSuffix:@"/ws"]) {
        if ([wsURL hasSuffix:@"/"]) {
            wsURL = [wsURL stringByAppendingString:@"ws"];
        } else {
            wsURL = [wsURL stringByAppendingString:@"/ws"];
        }
    }
    
    NSMutableString *urlWithParams = [NSMutableString stringWithString:wsURL];
    [urlWithParams appendString:@"?client_type=ios"];
    
    if (self.authToken.length > 0) {
        [urlWithParams appendFormat:@"&token=%@", self.authToken];
    }
    
    return [NSURL URLWithString:urlWithParams];
}

- (NSURL *)healthCheckURL {
    if (self.serverURL.length == 0) {
        return nil;
    }
    
    NSString *httpURL = self.serverURL;
    
    if ([httpURL hasPrefix:@"ws://"]) {
        httpURL = [httpURL stringByReplacingOccurrencesOfString:@"ws://" withString:@"http://"];
    } else if ([httpURL hasPrefix:@"wss://"]) {
        httpURL = [httpURL stringByReplacingOccurrencesOfString:@"wss://" withString:@"https://"];
    } else if (![httpURL hasPrefix:@"http://"] && ![httpURL hasPrefix:@"https://"]) {
        httpURL = [@"https://" stringByAppendingString:httpURL];
    }
    
    NSURL *baseURL = [NSURL URLWithString:httpURL];
    if (!baseURL) {
        return nil;
    }
    
    NSURLComponents *components = [NSURLComponents componentsWithURL:baseURL resolvingAgainstBaseURL:NO];
    if (!components) {
        return nil;
    }
    components.path = @"/health";
    components.query = nil;
    components.fragment = nil;
    
    return components.URL;
}

@end
