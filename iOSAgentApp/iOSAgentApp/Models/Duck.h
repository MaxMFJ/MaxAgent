#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// 子 Duck 模型，用于用户直聊选择
@interface Duck : NSObject

@property (nonatomic, copy) NSString *duckId;
@property (nonatomic, copy) NSString *name;
@property (nonatomic, copy) NSString *duckType;
@property (nonatomic, copy) NSString *status;  // online | busy | offline
@property (nonatomic, assign) BOOL isLocal;

- (instancetype)initWithDictionary:(NSDictionary *)dict;
- (NSDictionary *)toDictionary;

@end

NS_ASSUME_NONNULL_END
