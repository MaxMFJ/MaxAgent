//
//  TechTheme.h
//  iOSAgentApp
//
//  科技感主题 - 霓虹/赛博朋克 UI 样式中心
//

#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@interface TechTheme : NSObject

// MARK: - Core Colors

/// 主背景色：深空黑
@property (class, nonatomic, readonly) UIColor *backgroundPrimary;
/// 次背景色：深灰蓝
@property (class, nonatomic, readonly) UIColor *backgroundSecondary;
/// 卡片背景（半透明模糊）
@property (class, nonatomic, readonly) UIColor *backgroundCard;

// MARK: - Neon Accent Colors

/// 主霓虹青色 #00D4FF
@property (class, nonatomic, readonly) UIColor *neonCyan;
/// 霓虹紫色 #7B2FFF
@property (class, nonatomic, readonly) UIColor *neonPurple;
/// 霓虹绿色 #00FF88
@property (class, nonatomic, readonly) UIColor *neonGreen;
/// 霓虹橙色 #FF6B00
@property (class, nonatomic, readonly) UIColor *neonOrange;
/// 霓虹红色 #FF2D55
@property (class, nonatomic, readonly) UIColor *neonRed;
/// 霓虹蓝色 #3D85FF
@property (class, nonatomic, readonly) UIColor *neonBlue;

// MARK: - Text Colors

/// 主文字（冷白）
@property (class, nonatomic, readonly) UIColor *textPrimary;
/// 次文字（dim blue-white）
@property (class, nonatomic, readonly) UIColor *textSecondary;
/// 暗淡文字
@property (class, nonatomic, readonly) UIColor *textDim;

// MARK: - Message Bubble Colors

/// 用户消息气泡渐变起始颜色
@property (class, nonatomic, readonly) UIColor *userBubbleStart;
/// 用户消息气泡渐变结束颜色
@property (class, nonatomic, readonly) UIColor *userBubbleEnd;
/// AI 回复气泡背景
@property (class, nonatomic, readonly) UIColor *aiBubbleBackground;
/// 工具调用气泡背景
@property (class, nonatomic, readonly) UIColor *toolCallBubble;
/// 工具结果气泡背景
@property (class, nonatomic, readonly) UIColor *toolResultBubble;

// MARK: - Helpers

/// 为 view 添加霓虹发光阴影效果
+ (void)applyNeonGlow:(UIView *)view color:(UIColor *)color radius:(CGFloat)radius;

/// 为 view 添加霓虹边框（CAGradientLayer）
+ (void)applyNeonBorder:(UIView *)view color:(UIColor *)color width:(CGFloat)width cornerRadius:(CGFloat)cornerRadius;

/// 为 view 应用玻璃拟态背景（需要父视图支持）
+ (UIVisualEffectView *)applyGlassBackground:(UIView *)view alpha:(CGFloat)alpha cornerRadius:(CGFloat)cornerRadius;

/// 创建用户消息气泡渐变层
+ (CAGradientLayer *)createUserBubbleGradient:(CGRect)frame;

/// 创建 AI 气泡边框光晕层
+ (CAGradientLayer *)createAIBorderGradient:(CGRect)frame cornerRadius:(CGFloat)radius;

/// 动态脉冲动画（用于连接指示灯等）
+ (void)addPulseAnimation:(UIView *)view color:(UIColor *)color;

/// 移除脉冲动画
+ (void)removePulseAnimation:(UIView *)view;

/// 消息气泡入场动画
+ (void)animateMessageBubbleEntrance:(UIView *)bubble fromUser:(BOOL)fromUser;

/// 扫描线动画（用于思维块 header）
+ (void)addScanAnimation:(UIView *)view;

@end

NS_ASSUME_NONNULL_END
