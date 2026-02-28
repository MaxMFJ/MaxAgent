#import "VoiceRainbowView.h"

@interface VoiceRainbowView ()
@property (nonatomic, strong) CAGradientLayer *topEdge;
@property (nonatomic, strong) CAGradientLayer *bottomEdge;
@property (nonatomic, strong) CAGradientLayer *leftEdge;
@property (nonatomic, strong) CAGradientLayer *rightEdge;
@end

static const CGFloat kEdgeDepth = 150;
static const CGFloat kEdgeAlpha = 0.2;

@implementation VoiceRainbowView

- (instancetype)initWithFrame:(CGRect)frame {
    self = [super initWithFrame:frame];
    if (self) {
        self.userInteractionEnabled = NO;
        self.backgroundColor = [UIColor clearColor];
        self.alpha = 0;
        [self setupEdges];
    }
    return self;
}

#pragma mark - Rainbow Colors

- (NSArray *)rainbowColors {
    CGFloat a = kEdgeAlpha;
    return @[
        (id)[UIColor colorWithRed:1.0 green:0.0  blue:0.0 alpha:a].CGColor,  // 红
        (id)[UIColor colorWithRed:1.0 green:0.45 blue:0.0 alpha:a].CGColor,  // 橙
        (id)[UIColor colorWithRed:1.0 green:0.9  blue:0.0 alpha:a].CGColor,  // 黄
        (id)[UIColor colorWithRed:0.0 green:0.9  blue:0.3 alpha:a].CGColor,  // 绿
        (id)[UIColor colorWithRed:0.0 green:0.85 blue:1.0 alpha:a].CGColor,  // 青
        (id)[UIColor colorWithRed:0.2 green:0.3  blue:1.0 alpha:a].CGColor,  // 蓝
        (id)[UIColor colorWithRed:0.6 green:0.1  blue:1.0 alpha:a].CGColor,  // 紫
        (id)[UIColor colorWithRed:1.0 green:0.0  blue:0.4 alpha:a].CGColor   // 回红
    ];
}

/// 按偏移量旋转颜色数组（用于流动动画关键帧）
- (NSArray *)rainbowColorsShiftedBy:(NSInteger)offset {
    NSArray *base = [self rainbowColors];
    NSInteger count = base.count;
    NSMutableArray *shifted = [NSMutableArray arrayWithCapacity:count];
    for (NSInteger i = 0; i < count; i++) {
        [shifted addObject:base[(i + offset) % count]];
    }
    return shifted;
}

#pragma mark - Setup

- (void)setupEdges {
    NSArray *colors = [self rainbowColors];

    // ---- 顶部 ----
    _topEdge = [CAGradientLayer layer];
    _topEdge.colors = colors;
    _topEdge.startPoint = CGPointMake(0, 0.5);
    _topEdge.endPoint   = CGPointMake(1, 0.5);
    CAGradientLayer *topMask = [CAGradientLayer layer];
    topMask.colors = @[(id)[UIColor whiteColor].CGColor, (id)[UIColor clearColor].CGColor];
    topMask.startPoint = CGPointMake(0.5, 0);
    topMask.endPoint   = CGPointMake(0.5, 1);
    _topEdge.mask = topMask;
    [self.layer addSublayer:_topEdge];

    // ---- 底部 ----
    _bottomEdge = [CAGradientLayer layer];
    _bottomEdge.colors = colors;
    _bottomEdge.startPoint = CGPointMake(1, 0.5);
    _bottomEdge.endPoint   = CGPointMake(0, 0.5);
    CAGradientLayer *bottomMask = [CAGradientLayer layer];
    bottomMask.colors = @[(id)[UIColor whiteColor].CGColor, (id)[UIColor clearColor].CGColor];
    bottomMask.startPoint = CGPointMake(0.5, 1);
    bottomMask.endPoint   = CGPointMake(0.5, 0);
    _bottomEdge.mask = bottomMask;
    [self.layer addSublayer:_bottomEdge];

    // ---- 左侧 ----
    _leftEdge = [CAGradientLayer layer];
    _leftEdge.colors = colors;
    _leftEdge.startPoint = CGPointMake(0.5, 1);
    _leftEdge.endPoint   = CGPointMake(0.5, 0);
    CAGradientLayer *leftMask = [CAGradientLayer layer];
    leftMask.colors = @[(id)[UIColor whiteColor].CGColor, (id)[UIColor clearColor].CGColor];
    leftMask.startPoint = CGPointMake(0, 0.5);
    leftMask.endPoint   = CGPointMake(1, 0.5);
    _leftEdge.mask = leftMask;
    [self.layer addSublayer:_leftEdge];

    // ---- 右侧 ----
    _rightEdge = [CAGradientLayer layer];
    _rightEdge.colors = colors;
    _rightEdge.startPoint = CGPointMake(0.5, 0);
    _rightEdge.endPoint   = CGPointMake(0.5, 1);
    CAGradientLayer *rightMask = [CAGradientLayer layer];
    rightMask.colors = @[(id)[UIColor whiteColor].CGColor, (id)[UIColor clearColor].CGColor];
    rightMask.startPoint = CGPointMake(1, 0.5);
    rightMask.endPoint   = CGPointMake(0, 0.5);
    _rightEdge.mask = rightMask;
    [self.layer addSublayer:_rightEdge];
}

#pragma mark - Layout

- (void)layoutSubviews {
    [super layoutSubviews];
    CGFloat w = self.bounds.size.width;
    CGFloat h = self.bounds.size.height;

    _topEdge.frame    = CGRectMake(0, 0, w, kEdgeDepth);
    _bottomEdge.frame = CGRectMake(0, h - kEdgeDepth, w, kEdgeDepth);
    _leftEdge.frame   = CGRectMake(0, 0, kEdgeDepth, h);
    _rightEdge.frame  = CGRectMake(w - kEdgeDepth, 0, kEdgeDepth, h);

    ((CAGradientLayer *)_topEdge.mask).frame    = _topEdge.bounds;
    ((CAGradientLayer *)_bottomEdge.mask).frame = _bottomEdge.bounds;
    ((CAGradientLayer *)_leftEdge.mask).frame   = _leftEdge.bounds;
    ((CAGradientLayer *)_rightEdge.mask).frame  = _rightEdge.bounds;
}

#pragma mark - Show / Hide

- (void)showAnimated {
    [UIView animateWithDuration:0.35 animations:^{
        self.alpha = 1.0;
    }];
}

- (void)hideAnimated {
    [self stopFlowing];
    [UIView animateWithDuration:0.35 animations:^{
        self.alpha = 0;
    }];
}

#pragma mark - Flow Animation

- (void)startFlowing {
    // 创建关键帧：颜色数组逐步偏移，产生彩虹流动效果
    NSInteger colorCount = [self rainbowColors].count;
    NSMutableArray *keyframes = [NSMutableArray array];
    for (NSInteger i = 0; i < colorCount; i++) {
        [keyframes addObject:[self rainbowColorsShiftedBy:i]];
    }
    // 闭合回路：末尾加回初始帧，避免循环时跳变卡顿
    [keyframes addObject:[self rainbowColorsShiftedBy:0]];

    for (CAGradientLayer *edge in @[_topEdge, _bottomEdge, _leftEdge, _rightEdge]) {
        // 颜色流动
        CAKeyframeAnimation *colorAnim = [CAKeyframeAnimation animationWithKeyPath:@"colors"];
        colorAnim.values = keyframes;
        colorAnim.duration = 4.0;
        colorAnim.repeatCount = HUGE_VALF;
        colorAnim.calculationMode = kCAAnimationLinear;
        [edge addAnimation:colorAnim forKey:@"rainbowFlow"];

        // 轻微闪烁
        CABasicAnimation *flickerAnim = [CABasicAnimation animationWithKeyPath:@"opacity"];
        flickerAnim.fromValue = @1.0;
        flickerAnim.toValue   = @0.75;
        flickerAnim.duration  = 1.0;
        flickerAnim.repeatCount = HUGE_VALF;
        flickerAnim.autoreverses = YES;
        flickerAnim.timingFunction = [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionEaseInEaseOut];
        [edge addAnimation:flickerAnim forKey:@"flicker"];
    }
}

- (void)stopFlowing {
    for (CAGradientLayer *edge in @[_topEdge, _bottomEdge, _leftEdge, _rightEdge]) {
        [edge removeAnimationForKey:@"rainbowFlow"];
        [edge removeAnimationForKey:@"flicker"];
    }
}

@end
