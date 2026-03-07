#import <UIKit/UIKit.h>

#if __has_include(<YYText/YYText.h>)
#import <YYText/YYText.h>
#else
@class YYLabel;
#endif

NS_ASSUME_NONNULL_BEGIN

/// 消息文本展示中间层：基于 YYText 统一高度计算与渲染，确保 cell 高度与内容完全匹配
/// 解决 YYLabel 单独使用时 heightForRow 与显示高度不一致导致的截断/显示不全问题
@interface MessageTextDisplay : NSObject

/// 使用 YYTextLayout 计算文本高度（与 YYLabel 渲染结果一致）
/// @param text 纯文本
/// @param font 字体
/// @param textColor 文字颜色
/// @param maxWidth 最大宽度
+ (CGFloat)heightForText:(NSString *)text
                   font:(UIFont *)font
              textColor:(UIColor *)textColor
               maxWidth:(CGFloat)maxWidth;

/// 配置 YYLabel 显示文本（使用与高度计算相同的 layout 逻辑，保证一致）
/// @param label YYLabel 实例
/// @param text 纯文本
/// @param font 字体
/// @param textColor 文字颜色
/// @param maxWidth 最大宽度
+ (void)configureLabel:(YYLabel *)label
             withText:(NSString *)text
                font:(UIFont *)font
           textColor:(UIColor *)textColor
            maxWidth:(CGFloat)maxWidth;

@end

NS_ASSUME_NONNULL_END
