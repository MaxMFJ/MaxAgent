#import "DuckApiService.h"
#import "ServerConfig.h"

@implementation DuckApiService

+ (instancetype)sharedService {
    static DuckApiService *shared = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        shared = [[DuckApiService alloc] init];
    });
    return shared;
}

- (NSURL *)duckListURL {
    NSURL *healthURL = [[ServerConfig sharedConfig] healthCheckURL];
    if (!healthURL) return nil;
    
    NSURLComponents *components = [NSURLComponents componentsWithURL:healthURL resolvingAgainstBaseURL:NO];
    if (!components) return nil;
    components.path = @"/duck/list";
    components.query = nil;
    components.fragment = nil;
    return components.URL;
}

- (void)fetchDuckListWithCompletion:(void (^)(NSArray<Duck *> * _Nullable, NSError * _Nullable))completion {
    NSURL *url = [self duckListURL];
    if (!url) {
        dispatch_async(dispatch_get_main_queue(), ^{
            completion(nil, [NSError errorWithDomain:@"DuckApiService" code:-1 userInfo:@{NSLocalizedDescriptionKey: @"Server URL not configured"}]);
        });
        return;
    }
    
    NSURLSession *session = [NSURLSession sharedSession];
    NSURLSessionDataTask *task = [session dataTaskWithURL:url completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            if (error) {
                completion(nil, error);
                return;
            }
            
            NSHTTPURLResponse *http = (NSHTTPURLResponse *)response;
            if (http.statusCode != 200) {
                completion(nil, [NSError errorWithDomain:@"DuckApiService" code:http.statusCode userInfo:@{NSLocalizedDescriptionKey: [NSString stringWithFormat:@"HTTP %ld", (long)http.statusCode]}]);
                return;
            }
            
            NSError *jsonError;
            id json = [NSJSONSerialization JSONObjectWithData:data options:0 error:&jsonError];
            if (jsonError || ![json isKindOfClass:[NSDictionary class]]) {
                completion(nil, jsonError ?: [NSError errorWithDomain:@"DuckApiService" code:-2 userInfo:@{NSLocalizedDescriptionKey: @"Invalid JSON"}]);
                return;
            }
            
            NSArray *raw = [(NSDictionary *)json objectForKey:@"ducks"];
            if (![raw isKindOfClass:[NSArray class]]) {
                completion(@[], nil);
                return;
            }
            
            NSMutableArray<Duck *> *ducks = [NSMutableArray array];
            for (id item in raw) {
                if ([item isKindOfClass:[NSDictionary class]]) {
                    [ducks addObject:[[Duck alloc] initWithDictionary:item]];
                }
            }
            completion(ducks, nil);
        });
    }];
    [task resume];
}

@end
