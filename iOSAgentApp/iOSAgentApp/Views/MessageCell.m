#import "MessageCell.h"
#import "ThinkingContentParser.h"
#import "ThinkingBlockView.h"
#import "TechTheme.h"

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

@property (nonatomic, strong) UILabel *contentLabel;
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

@end

@implementation MessageCell

- (instancetype)initWithStyle:(UITableViewCellStyle)style reuseIdentifier:(NSString *)reuseIdentifier {
    self = [super initWithStyle:style reuseIdentifier:reuseIdentifier];
    if (self) {
        _isFirstConfigure = YES;
        [self setupUI];
    }
    return self;
}

- (void)setupUI {
    self.selectionStyle = UITableViewCellSelectionStyleNone;
    self.backgroundColor = [UIColor clearColor];
    self.contentView.backgroundColor = [UIColor clearColor];

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
    _roleLabel.font = [UIFont monospacedSystemFontOfSize:10 weight:UIFontWeightMedium];
    _roleLabel.textColor = TechTheme.textSecondary;
    [self.contentView addSubview:_roleLabel];

    // --- 内容标签 ---
    _contentLabel = [[UILabel alloc] init];
    _contentLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _contentLabel.font = [UIFont systemFontOfSize:15.5];
    _contentLabel.numberOfLines = 0;

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
    _bubbleTrailing = [_bubbleView.trailingAnchor constraintEqualToAnchor:self.contentView.trailingAnchor constant:-14];

    [NSLayoutConstraint activateConstraints:@[
        [_roleLabel.topAnchor constraintEqualToAnchor:self.contentView.topAnchor constant:8],
        [_roleLabel.leadingAnchor constraintEqualToAnchor:self.contentView.leadingAnchor constant:20],
        [_roleLabel.trailingAnchor constraintEqualToAnchor:self.contentView.trailingAnchor constant:-20],

        [_bubbleView.topAnchor constraintEqualToAnchor:_roleLabel.bottomAnchor constant:4],
        [_bubbleView.bottomAnchor constraintEqualToAnchor:self.contentView.bottomAnchor constant:-6],
        [_bubbleView.widthAnchor constraintLessThanOrEqualToAnchor:self.contentView.widthAnchor multiplier:0.82],

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
}

// MARK: - Configure

- (void)configureWithMessage:(Message *)message {
    BOOL isFirst = _isFirstConfigure;
    _isFirstConfigure = NO;

    // --- 解析思维块 ---
    NSArray *parts = [ThinkingContentParser parseContent:message.content];
    BOOL hasThinking = NO;
    for (NSDictionary *part in parts) {
        if ([part[@"type"] isEqualToString:@"thinking"]) {
            hasThinking = YES;
            break;
        }
    }

    if (!hasThinking) {
        _contentLabel.hidden = NO;
        _contentStackView.hidden = YES;
        _contentLabel.text = message.content.length > 0 ? message.content : @" ";
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
                lbl.font = [UIFont systemFontOfSize:15.5];
                lbl.numberOfLines = 0;
                lbl.text = content;
                [_contentStackView addArrangedSubview:lbl];
            }
        }
    }

    BOOL isUser       = (message.role == MessageRoleUser);
    BOOL isToolCall   = (message.role == MessageRoleToolCall);
    BOOL isToolResult = (message.role == MessageRoleToolResult);

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
        // ------ 用户消息：纯色 + 右侧对齐 + 青色发光（与AI气泡风格一致）------
        _bubbleTrailing.active = YES;
        _bubbleInner.backgroundColor = TechTheme.aiBubbleBackground;

        _contentLabel.textColor    = TechTheme.textPrimary;
        _roleLabel.text            = NSLocalizedString(@"you", nil);
        _roleLabel.textAlignment   = NSTextAlignmentRight;
        _roleLabel.textColor       = [TechTheme.neonCyan colorWithAlphaComponent:0.7];

        [TechTheme applyNeonGlow:_bubbleView color:TechTheme.neonCyan radius:8];

    } else if (isToolCall) {
        // ------ 工具调用：深橙 ------
        _bubbleLeading.active = YES;
        _bubbleInner.backgroundColor = TechTheme.toolCallBubble;

        _contentLabel.textColor    = TechTheme.textPrimary;
        _roleLabel.text            = [NSString stringWithFormat:@"⚙ %@", message.toolName ?: NSLocalizedString(@"tool", nil)];
        _roleLabel.textAlignment   = NSTextAlignmentLeft;
        _roleLabel.textColor       = [TechTheme.neonOrange colorWithAlphaComponent:0.85];

        [TechTheme applyNeonGlow:_bubbleView color:TechTheme.neonOrange radius:6];

    } else if (isToolResult) {
        // ------ 工具结果：深绿 ------
        _bubbleLeading.active = YES;
        _bubbleInner.backgroundColor = TechTheme.toolResultBubble;

        _contentLabel.textColor    = TechTheme.textPrimary;
        _roleLabel.text            = [NSString stringWithFormat:@"✓ %@", NSLocalizedString(@"result", nil)];
        _roleLabel.textAlignment   = NSTextAlignmentLeft;
        _roleLabel.textColor       = [TechTheme.neonGreen colorWithAlphaComponent:0.85];

        [TechTheme applyNeonGlow:_bubbleView color:TechTheme.neonGreen radius:6];

    } else {
        // ------ AI 回复：深色玻璃感 ------
        _bubbleLeading.active = YES;
        _bubbleInner.backgroundColor = TechTheme.aiBubbleBackground;

        _contentLabel.textColor    = TechTheme.textPrimary;
        _roleLabel.text            = message.modelName ?: NSLocalizedString(@"assistant", nil);
        _roleLabel.textAlignment   = NSTextAlignmentLeft;
        _roleLabel.textColor       = [TechTheme.neonPurple colorWithAlphaComponent:0.85];

        [TechTheme applyNeonGlow:_bubbleView color:[TechTheme.neonCyan colorWithAlphaComponent:0.4] radius:10];
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

    // --- 图片 ---
    if (message.imageBase64.length > 0) {
        NSData *imageData = [[NSData alloc] initWithBase64EncodedString:message.imageBase64 options:NSDataBase64DecodingIgnoreUnknownCharacters];
        UIImage *image = [UIImage imageWithData:imageData];
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
}

- (void)prepareForReuse {
    [super prepareForReuse];
    // 不重置 _isFirstConfigure，避免复用 cell 重播入场动画导致变形
    // 重置 transform 和 alpha，防止动画残留
    _bubbleView.transform = CGAffineTransformIdentity;
    _bubbleView.alpha = 1.0;
    [_bubbleView.layer removeAllAnimations];
    // 清理 shadow
    _bubbleView.layer.shadowOpacity = 0;
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
