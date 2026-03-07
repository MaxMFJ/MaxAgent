#import "MessageTextDisplay.h"
#import <YYText/YYText.h>

@implementation MessageTextDisplay

+ (NSAttributedString *)_attributedStringForText:(NSString *)text font:(UIFont *)font textColor:(UIColor *)textColor {
    if (!text || text.length == 0) {
        text = @" ";
    }
    return [[NSAttributedString alloc] initWithString:text attributes:@{
        NSFontAttributeName: font ?: [UIFont systemFontOfSize:15],
        NSForegroundColorAttributeName: textColor ?: [UIColor blackColor]
    }];
}

+ (YYTextLayout *)_layoutForText:(NSString *)text font:(UIFont *)font textColor:(UIColor *)textColor maxWidth:(CGFloat)maxWidth {
    NSAttributedString *attr = [self _attributedStringForText:text font:font textColor:textColor];
    YYTextContainer *container = [YYTextContainer containerWithSize:CGSizeMake(maxWidth, CGFLOAT_MAX)];
    container.maximumNumberOfRows = 0;
    return [YYTextLayout layoutWithContainer:container text:attr];
}

+ (CGFloat)heightForText:(NSString *)text font:(UIFont *)font textColor:(UIColor *)textColor maxWidth:(CGFloat)maxWidth {
    if (maxWidth <= 0) return 20;
    YYTextLayout *layout = [self _layoutForText:text font:font textColor:textColor maxWidth:maxWidth];
    if (!layout) return 20;
    return ceil(layout.textBoundingSize.height);
}

+ (void)configureLabel:(YYLabel *)label withText:(NSString *)text font:(UIFont *)font textColor:(UIColor *)textColor maxWidth:(CGFloat)maxWidth {
    if (!label || maxWidth <= 0) return;
    YYTextLayout *layout = [self _layoutForText:text font:font textColor:textColor maxWidth:maxWidth];
    if (!layout) {
        label.textLayout = nil;
        label.text = text ?: @" ";
        label.font = font;
        label.textColor = textColor;
        return;
    }
    label.ignoreCommonProperties = YES;
    label.displaysAsynchronously = YES;
    label.textLayout = layout;
}

@end
