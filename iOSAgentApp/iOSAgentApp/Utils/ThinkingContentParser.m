#import "ThinkingContentParser.h"

@implementation ThinkingContentParser

+ (NSArray<NSDictionary<NSString *, NSString *> *> *)parseContent:(NSString *)content {
    if (!content || content.length == 0) {
        return @[@{@"type": @"text", @"content": @""}];
    }
    
    NSMutableArray<NSDictionary<NSString *, NSString *> *> *parts = [NSMutableArray array];
    NSString *openTag = @"<thinking>";
    NSString *closeTag = @"</thinking>";
    NSRange searchRange = NSMakeRange(0, content.length);
    
    while (searchRange.location < content.length) {
        NSRange openRange = [content rangeOfString:openTag options:NSCaseInsensitiveSearch range:searchRange];
        
        if (openRange.location == NSNotFound) {
            NSString *remaining = [content substringFromIndex:searchRange.location];
            if (remaining.length > 0) {
                [parts addObject:@{@"type": @"text", @"content": remaining}];
            }
            break;
        }
        
        // 开标签之前的文本
        if (openRange.location > searchRange.location) {
            NSString *before = [content substringWithRange:NSMakeRange(searchRange.location, openRange.location - searchRange.location)];
            if (before.length > 0) {
                [parts addObject:@{@"type": @"text", @"content": before}];
            }
        }
        
        NSRange afterOpen = NSMakeRange(openRange.location + openTag.length, content.length - (openRange.location + openTag.length));
        NSRange closeRange = [content rangeOfString:closeTag options:NSCaseInsensitiveSearch range:afterOpen];
        
        if (closeRange.location == NSNotFound) {
            // 未闭合（流式输出中）
            NSString *thinkingContent = [content substringFromIndex:afterOpen.location];
            thinkingContent = [thinkingContent stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
            if (thinkingContent.length > 0) {
                [parts addObject:@{@"type": @"thinking", @"content": thinkingContent}];
            }
            break;
        }
        
        NSString *thinkingContent = [content substringWithRange:NSMakeRange(afterOpen.location, closeRange.location - afterOpen.location)];
        thinkingContent = [thinkingContent stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
        if (thinkingContent.length > 0) {
            [parts addObject:@{@"type": @"thinking", @"content": thinkingContent}];
        }
        
        searchRange.location = closeRange.location + closeTag.length;
        searchRange.length = content.length - searchRange.location;
    }
    
    if (parts.count == 0) {
        return @[@{@"type": @"text", @"content": content}];
    }
    return [parts copy];
}

@end
