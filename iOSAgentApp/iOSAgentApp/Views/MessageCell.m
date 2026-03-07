#import "MessageCell.h"
#import "ThinkingContentParser.h"
#import "ThinkingBlockView.h"
#import "FileDownloadView.h"
#import "ServerConfig.h"
#import "TechTheme.h"
#import "MessageTextDisplay.h"
#import <YYText/YYText.h>
#import <QuartzCore/QuartzCore.h>

// 气泡：左 14pt，右 8pt，内容区左右各 14pt padding
static CGFloat _MessageCellContentMaxWidth(CGFloat tableViewWidth) {
    CGFloat w = tableViewWidth > 0 ? tableViewWidth : UIScreen.mainScreen.bounds.size.width;
    return w - 14 - 8 - 28;  // 屏幕宽 - 左边距 - 右边距 - 气泡内边距
}

// MARK: - 三点打字动画视图

@interface TypingDotsView : UIView
- (void)startAnimating;
- (void)stopAnimating;
@end

@implementation TypingDotsView {
    NSArray<UIView *> *_dots;
    BOOL _animating;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        self.translatesAutoresizingMaskIntoConstraints = NO;
        NSMutableArray *dots = [NSMutableArray array];
        for (int i = 0; i < 3; i++) {
            UIView *dot = [[UIView alloc] init];
            dot.translatesAutoresizingMaskIntoConstraints = NO;
            dot.backgroundColor = TechTheme.neonCyan;
            dot.layer.cornerRadius = 4;
            dot.alpha = 0.3;
            [self addSubview:dot];
            [NSLayoutConstraint activateConstraints:@[
                [dot.widthAnchor constraintEqualToConstant:8],
                [dot.heightAnchor constraintEqualToConstant:8],
                [dot.centerYAnchor constraintEqualToAnchor:self.centerYAnchor],
                [dot.leadingAnchor constraintEqualToAnchor:self.leadingAnchor constant:i * 14.0]
            ]];
            [dots addObject:dot];
        }
        _dots = dots;
        [NSLayoutConstraint activateConstraints:@[
            [self.widthAnchor constraintEqualToConstant:36],
            [self.heightAnchor constraintEqualToConstant:20]
        ]];
    }
    return self;
}

- (void)startAnimating {
    if (_animating) return;
    _animating = YES;
    self.hidden = NO;
    [self animateDotAtIndex:0 delay:0];
    [self animateDotAtIndex:1 delay:0.2];
    [self animateDotAtIndex:2 delay:0.4];
}

- (void)animateDotAtIndex:(NSInteger)index delay:(NSTimeInterval)delay {
    if (!_animating) return;
    UIView *dot = _dots[index];
    [UIView animateWithDuration:0.5
                          delay:delay
                        options:UIViewAnimationOptionRepeat | UIViewAnimationOptionAutoreverse
                     animations:^{
        dot.alpha = 1.0;
        dot.transform = CGAffineTransformMakeTranslation(0, -5);
    } completion:nil];
}

- (void)stopAnimating {
    _animating = NO;
    self.hidden = YES;
    for (UIView *dot in _dots) {
        [dot.layer removeAllAnimations];
        dot.alpha = 0.3;
        dot.transform = CGAffineTransformIdentity;
    }
}

@end


// MARK: - MessageCell

@interface MessageCell () <ThinkingBlockViewDelegate>

@property (nonatomic, strong) YYLabel *contentLabel;
@property (nonatomic, strong) UIStackView *contentStackView;
@property (nonatomic, strong) UIView *contentContainerView;
@property (nonatomic, strong) UILabel *roleLabel;
@property (nonatomic, strong) UIView *bubbleView;
@property (nonatomic, strong) UIView *bubbleInner;
@property (nonatomic, strong) UIActivityIndicatorView *loadingIndicator;
@property (nonatomic, strong) TypingDotsView *typingDots;
@property (nonatomic, strong) UIImageView *messageImageView;
@property (nonatomic, strong) UIStackView *bubbleStackView;
@property (nonatomic, strong) NSLayoutConstraint *bubbleLeading;
@property (nonatomic, strong) NSLayoutConstraint *bubbleTrailing;
@property (nonatomic, strong) NSLayoutConstraint *bubbleMinWidth;

// 渐变层（按消息类型切换）
@property (nonatomic, strong) CAGradientLayer *bubbleGradientLayer;
@property (nonatomic, assign) BOOL isFirstConfigure;

// 缓存：避免流式更新时重复执行昂贵操作
@property (nonatomic, copy, nullable) NSString *cachedContent;
@property (nonatomic, assign) MessageRole cachedRole;
@property (nonatomic, assign) BOOL cachedHasThinking;

// UILabel 高度约束：用 boundingRectWithSize 快速计算代替 intrinsicContentSize 慢计算
@property (nonatomic, strong) NSLayoutConstraint *contentLabelHeightConstraint;

@end

@implementation MessageCell

- (instancetype)initWithStyle:(UITableViewCellStyle)style reuseIdentifier:(NSString *)reuseIdentifier {
    self = [super initWithStyle:style reuseIdentifier:reuseIdentifier];
    if (self) {
        _isFirstConfigure = YES;
        _cachedRole = (MessageRole)NSIntegerMax; // sentinel
        [self setupUI];
    }
    return self;
}

- (void)setupUI {
    self.selectionStyle = UITableViewCellSelectionStyleNone;
    self.backgroundColor = [UIColor clearColor];
    self.contentView.backgroundColor = [UIColor clearColor];
    self.contentView.layoutMargins = UIEdgeInsetsZero;  // 消除默认边距，让气泡贴边

    // --- 气泡容器 ---
    _bubbleView = [[UIView alloc] init];
    _bubbleView.translatesAutoresizingMaskIntoConstraints = NO;
    _bubbleView.layer.cornerRadius = 18;
    _bubbleView.clipsToBounds = NO;   // 不裁剪，允许 glow 溢出
    [self.contentView addSubview:_bubbleView];

    // 用于裁剪内容的内层视图
    _bubbleInner = [[UIView alloc] init];
    _bubbleInner.translatesAutoresizingMaskIntoConstraints = NO;
    _bubbleInner.layer.cornerRadius = 18;
    _bubbleInner.clipsToBounds = YES;
    _bubbleInner.backgroundColor = [UIColor clearColor];
    [_bubbleView addSubview:_bubbleInner];
    [NSLayoutConstraint activateConstraints:@[
        [_bubbleInner.topAnchor constraintEqualToAnchor:_bubbleView.topAnchor],
        [_bubbleInner.leadingAnchor constraintEqualToAnchor:_bubbleView.leadingAnchor],
        [_bubbleInner.trailingAnchor constraintEqualToAnchor:_bubbleView.trailingAnchor],
        [_bubbleInner.bottomAnchor constraintEqualToAnchor:_bubbleView.bottomAnchor]
    ]];

    // --- 角色标签 ---
    _roleLabel = [[UILabel alloc] init];
    _roleLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _roleLabel.font = [TechTheme fontMonoSize:10 weight:UIFontWeightMedium];
    _roleLabel.textColor = TechTheme.textSecondary;
    [self.contentView addSubview:_roleLabel];

    // --- 内容标签（YYLabel 高性能渲染，配合 MessageTextDisplay 中间层保证高度一致）---
    _contentLabel = [[YYLabel alloc] init];
    _contentLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _contentLabel.numberOfLines = 0;
    _contentLabel.lineBreakMode = NSLineBreakByWordWrapping;

    // --- 思考块 StackView ---
    _contentStackView = [[UIStackView alloc] init];
    _contentStackView.axis = UILayoutConstraintAxisVertical;
    _contentStackView.spacing = 8;
    _contentStackView.translatesAutoresizingMaskIntoConstraints = NO;
    _contentStackView.hidden = YES;

    _contentContainerView = [[UIView alloc] init];
    _contentContainerView.translatesAutoresizingMaskIntoConstraints = NO;
    [_contentContainerView addSubview:_contentLabel];
    [_contentContainerView addSubview:_contentStackView];
    [NSLayoutConstraint activateConstraints:@[
        [_contentLabel.topAnchor constraintEqualToAnchor:_contentContainerView.topAnchor],
        [_contentLabel.leadingAnchor constraintEqualToAnchor:_contentContainerView.leadingAnchor],
        [_contentLabel.trailingAnchor constraintEqualToAnchor:_contentContainerView.trailingAnchor],
        [_contentLabel.bottomAnchor constraintEqualToAnchor:_contentContainerView.bottomAnchor],
        [_contentStackView.topAnchor constraintEqualToAnchor:_contentContainerView.topAnchor],
        [_contentStackView.leadingAnchor constraintEqualToAnchor:_contentContainerView.leadingAnchor],
        [_contentStackView.trailingAnchor constraintEqualToAnchor:_contentContainerView.trailingAnchor],
        [_contentStackView.bottomAnchor constraintEqualToAnchor:_contentContainerView.bottomAnchor]
    ]];

    // 高度约束：用 boundingRectWithSize 快速计算高度
    _contentLabelHeightConstraint = [_contentLabel.heightAnchor constraintGreaterThanOrEqualToConstant:0];
    _contentLabelHeightConstraint.priority = UILayoutPriorityDefaultHigh;
    _contentLabelHeightConstraint.active = YES;
    [_contentLabel setContentHuggingPriority:UILayoutPriorityDefaultLow - 1 forAxis:UILayoutConstraintAxisVertical];


    // --- 图片 ---
    _messageImageView = [[UIImageView alloc] init];
    _messageImageView.translatesAutoresizingMaskIntoConstraints = NO;
    _messageImageView.contentMode = UIViewContentModeScaleAspectFit;
    _messageImageView.layer.cornerRadius = 10;
    _messageImageView.clipsToBounds = YES;
    _messageImageView.hidden = YES;
    _messageImageView.userInteractionEnabled = YES;
    UITapGestureRecognizer *imageTap = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(imageTapped)];
    [_messageImageView addGestureRecognizer:imageTap];

    // --- 气泡内容 StackView ---
    _bubbleStackView = [[UIStackView alloc] initWithArrangedSubviews:@[_contentContainerView, _messageImageView]];
    _bubbleStackView.axis = UILayoutConstraintAxisVertical;
    _bubbleStackView.spacing = 8;
    _bubbleStackView.translatesAutoresizingMaskIntoConstraints = NO;
    [_bubbleInner addSubview:_bubbleStackView];

    // --- 三点打字动画（取代 spinner）---
    _typingDots = [[TypingDotsView alloc] init];
    _typingDots.hidden = YES;
    [_bubbleInner addSubview:_typingDots];

    // --- 保留 loadingIndicator 供外部 readonly 属性访问（但不可见）---
    _loadingIndicator = [[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleMedium];
    _loadingIndicator.translatesAutoresizingMaskIntoConstraints = NO;
    _loadingIndicator.hidesWhenStopped = YES;
    _loadingIndicator.hidden = YES;
    [_bubbleInner addSubview:_loadingIndicator];

    // --- 气泡最小宽度（保证打字动画可见）---
    _bubbleMinWidth = [_bubbleView.widthAnchor constraintGreaterThanOrEqualToConstant:80];
    _bubbleMinWidth.active = YES;

    _bubbleLeading  = [_bubbleView.leadingAnchor  constraintEqualToAnchor:self.contentView.leadingAnchor  constant:14];
    _bubbleTrailing = [_bubbleView.trailingAnchor constraintEqualToAnchor:self.contentView.trailingAnchor constant:-8];  // 距屏幕右边 8pt

    [NSLayoutConstraint activateConstraints:@[
        [_roleLabel.topAnchor constraintEqualToAnchor:self.contentView.topAnchor constant:8],
        [_roleLabel.leadingAnchor constraintEqualToAnchor:self.contentView.leadingAnchor constant:20],
        [_roleLabel.trailingAnchor constraintEqualToAnchor:self.contentView.trailingAnchor constant:-20],

        [_bubbleView.topAnchor constraintEqualToAnchor:_roleLabel.bottomAnchor constant:4],
        [_bubbleView.bottomAnchor constraintEqualToAnchor:self.contentView.bottomAnchor constant:-6],
        [_bubbleView.widthAnchor constraintLessThanOrEqualToAnchor:self.contentView.widthAnchor multiplier:1 constant:-22],  // 左14+右8，最大宽度铺满

        [_bubbleStackView.topAnchor constraintEqualToAnchor:_bubbleInner.topAnchor constant:12],
        [_bubbleStackView.leadingAnchor constraintEqualToAnchor:_bubbleInner.leadingAnchor constant:14],
        [_bubbleStackView.trailingAnchor constraintEqualToAnchor:_bubbleInner.trailingAnchor constant:-14],
        [_bubbleStackView.bottomAnchor constraintEqualToAnchor:_bubbleInner.bottomAnchor constant:-12],

        [_messageImageView.widthAnchor constraintLessThanOrEqualToConstant:280],
        [_messageImageView.heightAnchor constraintLessThanOrEqualToConstant:300],

        [_typingDots.centerYAnchor constraintEqualToAnchor:_bubbleInner.centerYAnchor],
        [_typingDots.trailingAnchor constraintEqualToAnchor:_bubbleInner.trailingAnchor constant:-14],

        [_loadingIndicator.centerYAnchor constraintEqualToAnchor:_bubbleInner.centerYAnchor],
        [_loadingIndicator.trailingAnchor constraintEqualToAnchor:_bubbleInner.trailingAnchor constant:-14]
    ]];
}

// MARK: - Layout 时更新渐变层 frame

- (void)layoutSubviews {
    [super layoutSubviews];

    // 更新渐变层 frame（渐变在 bubbleInner 上，会被裁剪）
    if (_bubbleGradientLayer) {
        _bubbleGradientLayer.frame = _bubbleInner.bounds;
        _bubbleGradientLayer.cornerRadius = 18;
    }
    
    // 更新 shadowPath（bounds 可能在 configure 后因 Auto Layout 改变）
    if (_bubbleView.layer.shadowOpacity > 0 && !CGRectIsEmpty(_bubbleView.bounds)) {
        CGFloat cornerRadius = _bubbleView.layer.cornerRadius;
        _bubbleView.layer.shadowPath = [UIBezierPath bezierPathWithRoundedRect:_bubbleView.bounds cornerRadius:cornerRadius].CGPath;
    }
}

// MARK: - 高度计算（类方法供 heightForRowAtIndexPath 使用）

+ (CGFloat)heightForMessage:(Message *)message tableViewWidth:(CGFloat)width {
    if (message.cachedCellHeight > 0) {
        return message.cachedCellHeight; // 复用缓存，避免重复 boundingRect 计算
    }
    CGFloat maxWidth = _MessageCellContentMaxWidth(width);
    UIFont *bodyFont = [TechTheme fontBodySize:15.5 weight:UIFontWeightRegular];
    UIFont *thinkingFont = [TechTheme fontBodySize:11.5 weight:UIFontWeightRegular];
    
    CGFloat contentHeight;
    BOOL parseCacheValid = (message.cachedParsedParts != nil && message.cachedContentLength == message.content.length);
    NSArray *parts = parseCacheValid ? message.cachedParsedParts : [ThinkingContentParser parseContent:message.content];
    if (!parseCacheValid) {
        message.cachedParsedParts = parts;
        message.cachedContentLength = message.content.length;
    }
    
    BOOL hasThinking = NO;
    for (NSDictionary *part in parts) {
        if ([part[@"type"] isEqualToString:@"thinking"]) {
            hasThinking = YES;
            break;
        }
    }
    
    if (!hasThinking) {
        NSString *text = message.content.length > 0 ? message.content : @" ";
        contentHeight = [MessageTextDisplay heightForText:text font:bodyFont textColor:TechTheme.textPrimary maxWidth:maxWidth];
    } else {
        contentHeight = 0;
        UIColor *thinkingColor = [TechTheme.neonPurple colorWithAlphaComponent:0.75];
        for (NSDictionary *part in parts) {
            NSString *type = part[@"type"];
            NSString *content = part[@"content"] ?: @"";
            if ([type isEqualToString:@"thinking"]) {
                contentHeight += 30 + 8 + [MessageTextDisplay heightForText:content font:thinkingFont textColor:thinkingColor maxWidth:maxWidth - 24] + 8;
            } else if (content.length > 0) {
                contentHeight += [MessageTextDisplay heightForText:content font:bodyFont textColor:TechTheme.textPrimary maxWidth:maxWidth];
            }
        }
        contentHeight += (parts.count > 1) ? (parts.count - 1) * 8 : 0; // UIStackView spacing
    }
    
    // 图片高度
    if (message.imageBase64.length > 0) {
        contentHeight += 8 + MIN(300, 280 * 0.75); // 最大 300 高，宽 280
    }
    
    // FileDownloadView 每个约 60pt
    NSArray *filePaths = message.cachedFilePaths;
    if (!filePaths) {
        filePaths = [FileDownloadView detectFilePathsInText:message.content];
        message.cachedFilePaths = filePaths;
    }
    if (filePaths.count > 0) {
        contentHeight += 8 + (CGFloat)filePaths.count * 60;
    }
    
    // 固定部分：roleLabel(8+14+4) + bubble(12+12) + bottom(6) = 56
    CGFloat total = 56 + contentHeight;
    message.cachedCellHeight = total; // 缓存供 heightForRow 复用
    return total;
}

// MARK: - Configure

- (void)configureWithMessage:(Message *)message {
    BOOL isFirst = _isFirstConfigure;
    _isFirstConfigure = NO;
    
    // === 快速路径：流式更新时，如果角色未变且无 thinking 块，仅更新文本 ===
    BOOL roleChanged = (_cachedRole != message.role);
    BOOL isStreamingUpdate = !isFirst && !roleChanged && message.status == MessageStatusStreaming;
    
    if (isStreamingUpdate && !_cachedHasThinking) {
        if (![_cachedContent isEqualToString:message.content]) {
            NSString *text = message.content.length > 0 ? message.content : @" ";
            CGFloat maxW = _MessageCellContentMaxWidth(0);
            [MessageTextDisplay configureLabel:_contentLabel withText:text font:[TechTheme fontBodySize:15.5 weight:UIFontWeightRegular] textColor:TechTheme.textPrimary maxWidth:maxW];
            _contentLabelHeightConstraint.constant = [MessageTextDisplay heightForText:text font:[TechTheme fontBodySize:15.5 weight:UIFontWeightRegular] textColor:TechTheme.textPrimary maxWidth:maxW];
            _cachedContent = message.content;
            // 流式更新时也检测文件路径并显示 FileDownloadView（如 AI 回复中已包含完整路径）
            NSArray<NSString *> *filePaths = message.cachedFilePaths;
            if (!filePaths) {
                filePaths = [FileDownloadView detectFilePathsInText:message.content];
                message.cachedFilePaths = filePaths;
            }
            if (filePaths.count > 0) {
                for (UIView *v in [_bubbleStackView.arrangedSubviews copy]) {
                    if ([v isKindOfClass:[FileDownloadView class]]) {
                        [_bubbleStackView removeArrangedSubview:v];
                        [v removeFromSuperview];
                    }
                }
                NSString *baseURL = [ServerConfig sharedConfig].serverURL;
                for (NSString *path in filePaths) {
                    FileDownloadView *fdv = [[FileDownloadView alloc] initWithFilePath:path serverBaseURL:baseURL];
                    [_bubbleStackView addArrangedSubview:fdv];
                    [fdv.leadingAnchor constraintEqualToAnchor:_bubbleStackView.leadingAnchor].active = YES;
                    [fdv.trailingAnchor constraintEqualToAnchor:_bubbleStackView.trailingAnchor].active = YES;
                }
            }
        }
        return;
    }

    // === 完整配置路径 ===
    CFTimeInterval t0 = CACurrentMediaTime();
    _cachedContent = message.content;
    _cachedRole = message.role;

    // 检查 Message 对象上的解析缓存是否有效（content 长度改变则失效）
    BOOL parseCacheValid = (message.cachedParsedParts != nil && message.cachedContentLength == message.content.length);

    CFTimeInterval tParse0 = CACurrentMediaTime();
    // --- 解析思维块（使用 Message 缓存避免重复解析）---
    NSArray *parts;
    if (parseCacheValid) {
        parts = message.cachedParsedParts;
    } else {
        parts = [ThinkingContentParser parseContent:message.content];
        message.cachedParsedParts = parts;
        message.cachedContentLength = message.content.length;
        message.cachedFilePaths = nil; // 内容变化时清除文件路径缓存
    }
    BOOL hasThinking = NO;
    for (NSDictionary *part in parts) {
        if ([part[@"type"] isEqualToString:@"thinking"]) {
            hasThinking = YES;
            break;
        }
    }
    _cachedHasThinking = hasThinking;
    CFTimeInterval tParse1 = CACurrentMediaTime();

    CFTimeInterval tContent0 = CACurrentMediaTime();

    if (!hasThinking) {
        _contentLabel.hidden = NO;
        _contentStackView.hidden = YES;
        // 关键：复用 cell 时若之前是 thinking 模式，必须清空 contentStackView，否则隐藏的 subviews 仍参与 layout 导致卡顿
        for (UIView *v in [_contentStackView.arrangedSubviews copy]) {
            [_contentStackView removeArrangedSubview:v];
            [v removeFromSuperview];
        }
        NSString *text = message.content.length > 0 ? message.content : @" ";
        UIFont *bodyFont = [TechTheme fontBodySize:15.5 weight:UIFontWeightRegular];
        UIColor *textColor = TechTheme.textPrimary;
        CGFloat maxW = _MessageCellContentMaxWidth(0);
        [UIView performWithoutAnimation:^{
            [MessageTextDisplay configureLabel:_contentLabel withText:text font:bodyFont textColor:textColor maxWidth:maxW];
            _contentLabelHeightConstraint.constant = [MessageTextDisplay heightForText:text font:bodyFont textColor:textColor maxWidth:maxW];
        }];
    } else {
        _contentLabel.hidden = YES;
        _contentStackView.hidden = NO;
        for (UIView *v in [_contentStackView.arrangedSubviews copy]) {
            [_contentStackView removeArrangedSubview:v];
            [v removeFromSuperview];
        }
        BOOL isStreaming = (message.status == MessageStatusStreaming);
        for (NSDictionary *part in parts) {
            NSString *type = part[@"type"];
            NSString *content = part[@"content"] ?: @"";
            if ([type isEqualToString:@"thinking"]) {
                ThinkingBlockView *tb = [[ThinkingBlockView alloc] initWithThinkingContent:content isStreaming:isStreaming];
                tb.delegate = (id<ThinkingBlockViewDelegate>)self;
                [_contentStackView addArrangedSubview:tb];
            } else if (content.length > 0) {
                UILabel *lbl = [[UILabel alloc] init];
                lbl.font = [TechTheme fontBodySize:15.5 weight:UIFontWeightRegular];
                lbl.numberOfLines = 0;
                lbl.text = content;
                [_contentStackView addArrangedSubview:lbl];
            }
        }
    }
    CFTimeInterval tContent1 = CACurrentMediaTime();

    BOOL isUser       = (message.role == MessageRoleUser);
    BOOL isToolCall   = (message.role == MessageRoleToolCall);
    BOOL isToolResult = (message.role == MessageRoleToolResult);

    // 仅在角色变化或首次配置时执行昂贵的样式/glow 操作
    if (roleChanged || isFirst) {
        _bubbleLeading.active  = NO;
        _bubbleTrailing.active = NO;

        // 移除旧渐变层
        if (_bubbleGradientLayer) {
            [_bubbleGradientLayer removeFromSuperlayer];
            _bubbleGradientLayer = nil;
        }

        // 重置背景
        _bubbleView.backgroundColor = [UIColor clearColor];
        _bubbleInner.backgroundColor = [UIColor clearColor];

        if (isUser) {
            _bubbleLeading.active = NO;
            _bubbleTrailing.active = YES;  // 用户消息：气泡靠右
            _bubbleInner.backgroundColor = TechTheme.aiBubbleBackground;
            _contentLabel.textColor    = TechTheme.textPrimary;
            _roleLabel.text            = NSLocalizedString(@"you", nil);
            _roleLabel.textAlignment   = NSTextAlignmentRight;
            _roleLabel.textColor       = [TechTheme.neonCyan colorWithAlphaComponent:0.7];
//            [TechTheme applyNeonGlow:_bubbleView color:TechTheme.neonCyan radius:8];
        } else if (isToolCall) {
            _bubbleLeading.active = YES;
            _bubbleTrailing.active = YES;  // AI/工具消息：气泡左右都固定，延伸到右边距 8pt
            _bubbleInner.backgroundColor = TechTheme.toolCallBubble;
            _contentLabel.textColor    = TechTheme.textPrimary;
            _roleLabel.text            = [NSString stringWithFormat:@"⚙ %@", message.toolName ?: NSLocalizedString(@"tool", nil)];
            _roleLabel.textAlignment   = NSTextAlignmentLeft;
            _roleLabel.textColor       = [TechTheme.neonOrange colorWithAlphaComponent:0.85];
//            [TechTheme applyNeonGlow:_bubbleView color:TechTheme.neonOrange radius:6];
        } else if (isToolResult) {
            _bubbleLeading.active = YES;
            _bubbleTrailing.active = YES;
            _bubbleInner.backgroundColor = TechTheme.toolResultBubble;
            _contentLabel.textColor    = TechTheme.textPrimary;
            _roleLabel.text            = [NSString stringWithFormat:@"✓ %@", NSLocalizedString(@"result", nil)];
            _roleLabel.textAlignment   = NSTextAlignmentLeft;
            _roleLabel.textColor       = [TechTheme.neonGreen colorWithAlphaComponent:0.85];
//            [TechTheme applyNeonGlow:_bubbleView color:TechTheme.neonGreen radius:6];
        } else {
            _bubbleLeading.active = YES;
            _bubbleTrailing.active = YES;  // 助手消息：气泡延伸到右边距 8pt
            _bubbleInner.backgroundColor = TechTheme.aiBubbleBackground;
            _contentLabel.textColor    = TechTheme.textPrimary;
            _roleLabel.text            = message.modelName ?: NSLocalizedString(@"assistant", nil);
            _roleLabel.textAlignment   = NSTextAlignmentLeft;
            _roleLabel.textColor       = [TechTheme.neonPurple colorWithAlphaComponent:0.85];
//            [TechTheme applyNeonGlow:_bubbleView color:[TechTheme.neonCyan colorWithAlphaComponent:0.4] radius:10];
        }
    }

    // 同步 contentStackView 内文本颜色
    for (UIView *v in _contentStackView.arrangedSubviews) {
        if ([v isKindOfClass:[UILabel class]]) {
            ((UILabel *)v).textColor = _contentLabel.textColor;
        }
    }

    // --- 打字动画 ---
    if (message.status == MessageStatusStreaming) {
        [_typingDots startAnimating];
    } else {
        [_typingDots stopAnimating];
    }

    // --- 文件下载卡片（使用 Message 缓存避免重复正则匹配）---
    // 先移除旧的 FileDownloadView
    for (UIView *v in [_bubbleStackView.arrangedSubviews copy]) {
        if ([v isKindOfClass:[FileDownloadView class]]) {
            [_bubbleStackView removeArrangedSubview:v];
            [v removeFromSuperview];
        }
    }
    // 检测文件路径并添加
    NSArray<NSString *> *filePaths = message.cachedFilePaths;
    if (!filePaths) {
        filePaths = [FileDownloadView detectFilePathsInText:message.content];
        message.cachedFilePaths = filePaths;
    }
    if (filePaths.count > 0) {
        NSString *baseURL = [ServerConfig sharedConfig].serverURL;
        for (NSString *path in filePaths) {
            FileDownloadView *fdv = [[FileDownloadView alloc] initWithFilePath:path serverBaseURL:baseURL];
            [_bubbleStackView addArrangedSubview:fdv];
            // 宽度填充气泡
            [fdv.leadingAnchor constraintEqualToAnchor:_bubbleStackView.leadingAnchor].active = YES;
            [fdv.trailingAnchor constraintEqualToAnchor:_bubbleStackView.trailingAnchor].active = YES;
        }
    }

    // --- 图片（使用 Message 缓存避免重复 base64 解码）---
    if (message.imageBase64.length > 0) {
        UIImage *image = message.cachedDecodedImage;
        if (!image) {
            NSData *imageData = [[NSData alloc] initWithBase64EncodedString:message.imageBase64 options:NSDataBase64DecodingIgnoreUnknownCharacters];
            image = [UIImage imageWithData:imageData];
            message.cachedDecodedImage = image;
        }
        if (image) {
            _messageImageView.image = image;
            _messageImageView.hidden = NO;
            // 图片加霓虹边框
            [TechTheme applyNeonGlow:_messageImageView color:TechTheme.neonCyan radius:6];
        } else {
            _messageImageView.image = nil;
            _messageImageView.hidden = YES;
        }
    } else {
        _messageImageView.image = nil;
        _messageImageView.hidden = YES;
    }

    // --- 入场动画（仅首次配置时播放）---
    if (isFirst) {
        [TechTheme animateMessageBubbleEntrance:_bubbleView fromUser:isUser];
    }

    CFTimeInterval t1 = CACurrentMediaTime();
    if ((t1 - t0) > 0.005) { // 仅记录超过 5ms 的配置
        NSLog(@"[Cell perf] total=%.1fms parse=%.1fms content=%.1fms rest=%.1fms role=%ld changed=%d len=%luB cache=%d thinking=%d",
              (t1 - t0) * 1000, (tParse1 - tParse0) * 1000, (tContent1 - tContent0) * 1000,
              (t1 - tContent1) * 1000, (long)message.role, roleChanged,
              (unsigned long)message.content.length, parseCacheValid, hasThinking);
    }
}

- (void)prepareForReuse {
    [super prepareForReuse];
    // 不重置 _isFirstConfigure，避免复用 cell 重播入场动画导致变形
    // 重置 transform 和 alpha，防止动画残留
    _bubbleView.transform = CGAffineTransformIdentity;
    _bubbleView.alpha = 1.0;
    [_bubbleView.layer removeAllAnimations];
    // 保留 shadow 和 _cachedRole：configureWithMessage 的 roleChanged 检查
    // 会在角色真正变化时重新应用样式和 glow，避免每次复用都走昂贵的样式路径。
    // layoutSubviews 会自动更新 shadowPath 适配新 bounds。
    // 清理 contentStackView：从长 cell（含 thinking 块）复用为短 cell 时，避免隐藏的 subviews 参与 layout 导致卡顿
    for (UIView *v in [_contentStackView.arrangedSubviews copy]) {
        [_contentStackView removeArrangedSubview:v];
        [v removeFromSuperview];
    }
    // 清理 FileDownloadView，避免复用时残留上一条消息的文件下载按钮
    for (UIView *v in [_bubbleStackView.arrangedSubviews copy]) {
        if ([v isKindOfClass:[FileDownloadView class]]) {
            [_bubbleStackView removeArrangedSubview:v];
            [v removeFromSuperview];
        }
    }
    _cachedContent = nil;
    _cachedHasThinking = NO;
}

- (void)imageTapped {
    if (_messageImageView.image && [self.delegate respondsToSelector:@selector(messageCell:didTapImage:)]) {
        [self.delegate messageCell:self didTapImage:_messageImageView.image];
    }
}

#pragma mark - ThinkingBlockViewDelegate

- (void)thinkingBlockViewDidToggle:(ThinkingBlockView *)view {
    if ([self.delegate respondsToSelector:@selector(messageCellDidToggleThinking:)]) {
        [self.delegate messageCellDidToggleThinking:self];
    }
}

@end
