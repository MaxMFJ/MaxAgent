#import "Duck.h"

@implementation Duck

- (instancetype)initWithDictionary:(NSDictionary *)dict {
    self = [super init];
    if (self) {
        _duckId = [dict[@"duck_id"] isKindOfClass:[NSString class]] ? dict[@"duck_id"] : @"";
        _name = [dict[@"name"] isKindOfClass:[NSString class]] ? dict[@"name"] : _duckId;
        _duckType = [dict[@"duck_type"] isKindOfClass:[NSString class]] ? dict[@"duck_type"] : @"general";
        _status = [dict[@"status"] isKindOfClass:[NSString class]] ? dict[@"status"] : @"offline";
        _isLocal = [dict[@"is_local"] isKindOfClass:[NSNumber class]] ? [dict[@"is_local"] boolValue] : NO;
    }
    return self;
}

- (NSDictionary *)toDictionary {
    return @{
        @"duck_id": _duckId ?: @"",
        @"name": _name ?: @"",
        @"duck_type": _duckType ?: @"general",
        @"status": _status ?: @"offline",
        @"is_local": @(_isLocal)
    };
}

@end
