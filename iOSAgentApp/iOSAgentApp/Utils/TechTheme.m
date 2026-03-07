//
//  TechTheme.m
//  iOSAgentApp
//
//  科技感主题 - 霓虹/赛博朋克 UI 样式实现
//

#import "TechTheme.h"

// MARK: - Hex Color Helper
static UIColor *UIColorFromHex(UInt32 hex) {
    return [UIColor colorWithRed:((hex >> 16) & 0xFF) / 255.0
                           green:((hex >> 8) & 0xFF) / 255.0
                            blue:(hex & 0xFF) / 255.0
                           alpha:1.0];
}

static UIColor *UIColorFromHexA(UInt32 hex, CGFloat alpha) {
    return [UIColor colorWithRed:((hex >> 16) & 0xFF) / 255.0
                           green:((hex >> 8) & 0xFF) / 255.0
                            blue:(hex & 0xFF) / 255.0
                           alpha:alpha];
}

@implementation TechTheme

// MARK: - Core Colors（与官网 website 对齐：--bg #0a0a0f, --bg-card #12121f）

+ (UIColor *)backgroundPrimary {
    return UIColorFromHex(0x0a0a0f);   // --bg 极深背景
}

+ (UIColor *)backgroundSecondary {
    return UIColorFromHex(0x0f0f18);   // --bg-elevated
}

+ (UIColor *)backgroundCard {
    return UIColorFromHex(0x12121f);  // --bg-card
}

// MARK: - Neon Accent Colors（与官网 --accent #00f5ff, --neon-purple #bf00ff）

+ (UIColor *)neonCyan {
    return UIColorFromHex(0x00f5ff);  // --accent
}

+ (UIColor *)neonPurple {
    return UIColorFromHex(0xbf00ff);  // --neon-purple
}

+ (UIColor *)neonGreen {
    return UIColorFromHex(0x00FF88);
}

+ (UIColor *)neonOrange {
    return UIColorFromHex(0xFF6B00);
}

+ (UIColor *)neonRed {
    return UIColorFromHex(0xFF2D55);
}

+ (UIColor *)neonBlue {
    return UIColorFromHex(0x3D85FF);
}

// MARK: - Text Colors（与官网 --text #e8e8f0, --text-muted #8b8ba3）

+ (UIColor *)textPrimary {
    return UIColorFromHex(0xe8e8f0);   // --text
}

+ (UIColor *)textSecondary {
    return UIColorFromHex(0x8b8ba3);   // --text-muted
}

+ (UIColor *)textDim {
    return UIColorFromHexA(0x8b8ba3, 0.7);
}

// MARK: - Bubble Colors

+ (UIColor *)userBubbleStart {
    return UIColorFromHex(0x1A2F7A);
}

+ (UIColor *)userBubbleEnd {
    return UIColorFromHex(0x0E1D52);
}

+ (UIColor *)aiBubbleBackground {
    return UIColorFromHexA(0x0F1E33, 0.42);
}

+ (UIColor *)toolCallBubble {
    return UIColorFromHexA(0x2A1600, 0.92);
}

+ (UIColor *)toolResultBubble {
    return UIColorFromHexA(0x001A0E, 0.92);
}

// MARK: - Helpers

+ (void)applyNeonGlow:(UIView *)view color:(UIColor *)color radius:(CGFloat)radius {
    view.layer.shadowColor = color.CGColor;
    view.layer.shadowOffset = CGSizeZero;
    view.layer.shadowRadius = radius;
    view.layer.shadowOpacity = 0.72;
    // 设置 shadowPath 避免 GPU 每帧重新计算阴影轮廓（核心性能优化）
    CGFloat cornerRadius = view.layer.cornerRadius;
    if (cornerRadius > 0) {
        view.layer.shadowPath = [UIBezierPath bezierPathWithRoundedRect:view.bounds cornerRadius:cornerRadius].CGPath;
    } else {
        view.layer.shadowPath = [UIBezierPath bezierPathWithRect:view.bounds].CGPath;
    }
    // 光栅化阴影层，避免滚动时反复渲染
    view.layer.shouldRasterize = YES;
    view.layer.rasterizationScale = [UIScreen mainScreen].scale;
}

+ (void)applyNeonBorder:(UIView *)view color:(UIColor *)color width:(CGFloat)width cornerRadius:(CGFloat)cornerRadius {
    // 移除旧的霓虹边框层
    for (CALayer *l in [view.layer.sublayers copy]) {
        if ([l.name isEqualToString:@"NeonBorderLayer"]) {
            [l removeFromSuperlayer];
        }
    }

    CAGradientLayer *borderLayer = [CAGradientLayer layer];
    borderLayer.name = @"NeonBorderLayer";
    borderLayer.frame = view.bounds;
    borderLayer.colors = @[
        (id)[color colorWithAlphaComponent:0.9].CGColor,
        (id)[color colorWithAlphaComponent:0.2].CGColor,
        (id)[color colorWithAlphaComponent:0.6].CGColor
    ];
    borderLayer.locations = @[@0.0, @0.5, @1.0];
    borderLayer.startPoint = CGPointMake(0, 0);
    borderLayer.endPoint = CGPointMake(1, 1);
    borderLayer.cornerRadius = cornerRadius;

    CAShapeLayer *mask = [CAShapeLayer layer];
    UIBezierPath *outerPath = [UIBezierPath bezierPathWithRoundedRect:view.bounds cornerRadius:cornerRadius];
    UIBezierPath *innerPath = [UIBezierPath bezierPathWithRoundedRect:CGRectInset(view.bounds, width, width) cornerRadius:MAX(0, cornerRadius - width)];
    [outerPath appendPath:innerPath];
    mask.path = outerPath.CGPath;
    mask.fillRule = kCAFillRuleEvenOdd;
    borderLayer.mask = mask;

    [view.layer addSublayer:borderLayer];
}

+ (UIVisualEffectView *)applyGlassBackground:(UIView *)view alpha:(CGFloat)alpha cornerRadius:(CGFloat)cornerRadius {
    UIBlurEffect *blur = [UIBlurEffect effectWithStyle:UIBlurEffectStyleSystemUltraThinMaterialDark];
    UIVisualEffectView *glassView = [[UIVisualEffectView alloc] initWithEffect:blur];
    glassView.translatesAutoresizingMaskIntoConstraints = NO;
    glassView.layer.cornerRadius = cornerRadius;
    glassView.clipsToBounds = YES;
    glassView.alpha = alpha;
    [view insertSubview:glassView atIndex:0];
    [NSLayoutConstraint activateConstraints:@[
        [glassView.topAnchor constraintEqualToAnchor:view.topAnchor],
        [glassView.leadingAnchor constraintEqualToAnchor:view.leadingAnchor],
        [glassView.trailingAnchor constraintEqualToAnchor:view.trailingAnchor],
        [glassView.bottomAnchor constraintEqualToAnchor:view.bottomAnchor]
    ]];
    return glassView;
}

+ (CAGradientLayer *)createUserBubbleGradient:(CGRect)frame {
    CAGradientLayer *gradient = [CAGradientLayer layer];
    gradient.frame = frame;
    gradient.colors = @[
        (id)UIColorFromHex(0x1a1a2e).CGColor,  // --bg-card-hover
        (id)UIColorFromHex(0x12121f).CGColor,
        (id)UIColorFromHex(0x0f0f18).CGColor
    ];
    gradient.locations = @[@0.0, @0.6, @1.0];
    gradient.startPoint = CGPointMake(0, 0);
    gradient.endPoint = CGPointMake(1, 1);
    return gradient;
}

+ (CAGradientLayer *)createAIBorderGradient:(CGRect)frame cornerRadius:(CGFloat)radius {
    CAGradientLayer *borderGradient = [CAGradientLayer layer];
    borderGradient.name = @"AIBorderGradient";
    borderGradient.frame = frame;
    borderGradient.colors = @[
        (id)UIColorFromHexA(0x00f5ff, 0.6).CGColor,
        (id)UIColorFromHexA(0xbf00ff, 0.3).CGColor,
        (id)UIColorFromHexA(0x00f5ff, 0.1).CGColor
    ];
    borderGradient.startPoint = CGPointMake(0, 0);
    borderGradient.endPoint = CGPointMake(1, 1);

    CAShapeLayer *borderMask = [CAShapeLayer layer];
    UIBezierPath *outerPath = [UIBezierPath bezierPathWithRoundedRect:frame cornerRadius:radius];
    UIBezierPath *innerPath = [UIBezierPath bezierPathWithRoundedRect:CGRectInset(frame, 0.8, 0.8) cornerRadius:MAX(0, radius - 0.8)];
    [outerPath appendPath:innerPath];
    borderMask.path = outerPath.CGPath;
    borderMask.fillRule = kCAFillRuleEvenOdd;
    borderGradient.mask = borderMask;

    return borderGradient;
}

+ (void)addPulseAnimation:(UIView *)view color:(UIColor *)color {
    [self removePulseAnimation:view];

    CALayer *pulseLayer = [CALayer layer];
    pulseLayer.name = @"PulseLayer";
    pulseLayer.frame = view.bounds;
    pulseLayer.cornerRadius = view.layer.cornerRadius;
    pulseLayer.backgroundColor = color.CGColor;
    [view.layer insertSublayer:pulseLayer atIndex:0];

    CABasicAnimation *scale = [CABasicAnimation animationWithKeyPath:@"transform.scale"];
    scale.fromValue = @1.0;
    scale.toValue = @1.5;
    scale.duration = 0.9;
    scale.repeatCount = HUGE_VALF;
    scale.autoreverses = NO;
    scale.timingFunction = [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionEaseOut];

    CABasicAnimation *fade = [CABasicAnimation animationWithKeyPath:@"opacity"];
    fade.fromValue = @0.5;
    fade.toValue = @0.0;
    fade.duration = 0.9;
    fade.repeatCount = HUGE_VALF;
    fade.autoreverses = NO;
    fade.timingFunction = [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionEaseOut];

    CAAnimationGroup *group = [CAAnimationGroup animation];
    group.animations = @[scale, fade];
    group.duration = 0.9;
    group.repeatCount = HUGE_VALF;
    group.autoreverses = NO;
    [pulseLayer addAnimation:group forKey:@"pulse"];
}

+ (void)removePulseAnimation:(UIView *)view {
    for (CALayer *l in [view.layer.sublayers copy]) {
        if ([l.name isEqualToString:@"PulseLayer"]) {
            [l removeFromSuperlayer];
        }
    }
}

+ (void)animateMessageBubbleEntrance:(UIView *)bubble fromUser:(BOOL)fromUser {
    bubble.alpha = 0;
    CGFloat dx = fromUser ? 30.0 : -30.0;
    bubble.transform = CGAffineTransformTranslate(CGAffineTransformMakeScale(0.92, 0.92), dx, 8);

    [UIView animateWithDuration:0.38
                          delay:0
         usingSpringWithDamping:0.72
          initialSpringVelocity:0.5
                        options:UIViewAnimationOptionCurveEaseOut
                     animations:^{
        bubble.alpha = 1;
        bubble.transform = CGAffineTransformIdentity;
    } completion:nil];
}

// MARK: - Cyber Fonts（与官网 font-display Orbitron、body Rajdhani 一致）

+ (UIFont *)fontDisplaySize:(CGFloat)size weight:(UIFontWeight)weight {
    // Orbitron 变量字体：尝试多种名称（不同系统可能注册不同）
    NSArray *names = @[@"Orbitron-Bold", @"Orbitron-SemiBold", @"Orbitron-Medium", @"Orbitron", @"OrbitronVariable"];
    for (NSString *name in names) {
        UIFont *f = [UIFont fontWithName:name size:size];
        if (f) return f;
    }
    return [UIFont systemFontOfSize:size weight:weight];
}

+ (UIFont *)fontBodySize:(CGFloat)size weight:(UIFontWeight)weight {
    NSString *name = @"Rajdhani-Regular";
    if (weight >= UIFontWeightBold) name = @"Rajdhani-Bold";
    else if (weight >= UIFontWeightSemibold) name = @"Rajdhani-SemiBold";
    else if (weight >= UIFontWeightMedium) name = @"Rajdhani-Medium";
    UIFont *f = [UIFont fontWithName:name size:size];
    return f ?: [UIFont systemFontOfSize:size weight:weight];
}

+ (UIFont *)fontMonoSize:(CGFloat)size weight:(UIFontWeight)weight {
    return [self fontDisplaySize:size weight:weight >= UIFontWeightMedium ? weight : UIFontWeightMedium];
}

+ (void)addScanAnimation:(UIView *)view {
    for (CALayer *l in [view.layer.sublayers copy]) {
        if ([l.name isEqualToString:@"ScanLine"]) {
            [l removeFromSuperlayer];
        }
    }

    CAGradientLayer *scanLine = [CAGradientLayer layer];
    scanLine.name = @"ScanLine";
    scanLine.frame = CGRectMake(0, 0, view.bounds.size.width, 2);
    scanLine.colors = @[
        (id)[UIColor clearColor].CGColor,
        (id)UIColorFromHexA(0x00f5ff, 0.8).CGColor,
        (id)[UIColor clearColor].CGColor
    ];
    scanLine.startPoint = CGPointMake(0, 0.5);
    scanLine.endPoint = CGPointMake(1, 0.5);
    [view.layer addSublayer:scanLine];

    CABasicAnimation *anim = [CABasicAnimation animationWithKeyPath:@"position.y"];
    anim.fromValue = @0;
    anim.toValue = @(view.bounds.size.height);
    anim.duration = 1.5;
    anim.repeatCount = HUGE_VALF;
    anim.timingFunction = [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionLinear];
    [scanLine addAnimation:anim forKey:@"scan"];
}

@end
