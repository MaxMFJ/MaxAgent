#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// 解析 content 中的 <thinking>...</thinking> 块
/// 返回 @[@{@"type":@"text",@"content":@"..."}, @{@"type":@"thinking",@"content":@"..."}]
@interface ThinkingContentParser : NSObject

+ (NSArray<NSDictionary<NSString *, NSString *> *> *)parseContent:(NSString *)content;

@end

NS_ASSUME_NONNULL_END
