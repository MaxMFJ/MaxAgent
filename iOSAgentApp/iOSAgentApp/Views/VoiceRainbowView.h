#import <UIKit/UIKit.h>

/// 语音模式彩虹边缘光效
/// 屏幕四边渐变彩虹色，从边缘 alpha 0.4 向中心渐变到 0，深度 100pt
@interface VoiceRainbowView : UIView

/// 显示彩虹边缘（淡入）
- (void)showAnimated;
/// 隐藏彩虹边缘（淡出）
- (void)hideAnimated;
/// 开始彩虹流动动画（用户说话时）
- (void)startFlowing;
/// 停止流动动画
- (void)stopFlowing;

@end
