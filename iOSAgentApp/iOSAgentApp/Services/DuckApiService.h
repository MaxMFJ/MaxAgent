#import <Foundation/Foundation.h>
#import "Duck.h"

NS_ASSUME_NONNULL_BEGIN

@interface DuckApiService : NSObject

+ (instancetype)sharedService;

/// 获取 Duck 列表，GET /duck/list
- (void)fetchDuckListWithCompletion:(void(^)(NSArray<Duck *> * _Nullable ducks, NSError * _Nullable error))completion;

@end

NS_ASSUME_NONNULL_END
