#import "InputView.h"
#import "TechTheme.h"

@interface InputView () <UITextViewDelegate>

@property (nonatomic, strong) UITextView *textView;
@property (nonatomic, strong) UIButton *sendButton;
@property (nonatomic, strong) UIButton *voiceButton;
@property (nonatomic, strong) UILabel *placeholderLabel;
@property (nonatomic, strong) UIView *containerView;
@property (nonatomic, strong) NSLayoutConstraint *textViewHeightConstraint;

// 玻璃拟态模糊背景
@property (nonatomic, strong) UIVisualEffectView *blurBackground;
// 发送按钮渐变层
@property (nonatomic, strong) CAGradientLayer *sendGradientLayer;
// 麦克风按钮脉冲环
@property (nonatomic, strong) UIView *voicePulseRing;
// 防止 layoutSubviews 无限循环
@property (nonatomic, assign) CGSize lastContainerSize;

@end

@implementation InputView

- (instancetype)initWithFrame:(CGRect)frame {
    self = [super initWithFrame:frame];
    if (self) {
        [self setupUI];
        _enabled = YES;
        _loading = NO;
        _voiceInputActive = NO;
    }
    return self;
}

- (void)setupUI {
    // 主背景：玻璃拟态深色模糊
    self.backgroundColor = [UIColor clearColor];

    UIBlurEffect *blur = [UIBlurEffect effectWithStyle:UIBlurEffectStyleSystemUltraThinMaterialDark];
    _blurBackground = [[UIVisualEffectView alloc] initWithEffect:blur];
    _blurBackground.translatesAutoresizingMaskIntoConstraints = NO;
    [self addSubview:_blurBackground];

    // 顶部分隔线（发光青色）
    UIView *topGlow = [[UIView alloc] init];
    topGlow.translatesAutoresizingMaskIntoConstraints = NO;
    topGlow.backgroundColor = [TechTheme.neonCyan colorWithAlphaComponent:0.35];
    [self addSubview:topGlow];

    // 麦克风按钮
    _voiceButton = [UIButton buttonWithType:UIButtonTypeCustom];
    _voiceButton.translatesAutoresizingMaskIntoConstraints = NO;
    [_voiceButton setImage:[UIImage systemImageNamed:@"mic.fill"
                                   withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:20 weight:UIFontWeightMedium]]
                 forState:UIControlStateNormal];
    [_voiceButton setImage:[UIImage systemImageNamed:@"mic.fill"
                                   withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:20 weight:UIFontWeightMedium]]
                 forState:UIControlStateSelected];
    _voiceButton.tintColor = TechTheme.textSecondary;
    _voiceButton.backgroundColor = [TechTheme.neonCyan colorWithAlphaComponent:0.08];
    _voiceButton.layer.cornerRadius = 20;
    [_voiceButton addTarget:self action:@selector(voiceButtonTapped) forControlEvents:UIControlEventTouchUpInside];
    [self addSubview:_voiceButton];

    // 脉冲环（语音激活时使用）
    _voicePulseRing = [[UIView alloc] init];
    _voicePulseRing.translatesAutoresizingMaskIntoConstraints = NO;
    _voicePulseRing.layer.cornerRadius = 20;
    _voicePulseRing.layer.borderWidth = 2;
    _voicePulseRing.layer.borderColor = TechTheme.neonRed.CGColor;
    _voicePulseRing.backgroundColor = [UIColor clearColor];
    _voicePulseRing.alpha = 0;
    _voicePulseRing.userInteractionEnabled = NO;
    [self addSubview:_voicePulseRing];

    // 输入框容器（圆角，玻璃带霓虹边框）
    _containerView = [[UIView alloc] init];
    _containerView.translatesAutoresizingMaskIntoConstraints = NO;
    _containerView.backgroundColor = [TechTheme.backgroundCard colorWithAlphaComponent:0.72];
    _containerView.layer.cornerRadius = 22;
    _containerView.clipsToBounds = NO;
    [self addSubview:_containerView];

    // 文字输入
    _textView = [[UITextView alloc] init];
    _textView.translatesAutoresizingMaskIntoConstraints = NO;
    _textView.font = [TechTheme fontBodySize:15.5 weight:UIFontWeightRegular];
    _textView.backgroundColor = [UIColor clearColor];
    _textView.textColor = TechTheme.textPrimary;
    _textView.tintColor = TechTheme.neonCyan;
    _textView.keyboardAppearance = UIKeyboardAppearanceDark;
    _textView.delegate = self;
    _textView.scrollEnabled = NO;
    [_containerView addSubview:_textView];

    // 点击容器区域确保激活输入框
    UITapGestureRecognizer *containerTap = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(containerTapped)];
    [_containerView addGestureRecognizer:containerTap];

    // 占位文字
    _placeholderLabel = [[UILabel alloc] init];
    _placeholderLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _placeholderLabel.text = NSLocalizedString(@"message_placeholder", nil);
    _placeholderLabel.font = [TechTheme fontBodySize:15.5 weight:UIFontWeightRegular];
    _placeholderLabel.textColor = TechTheme.textDim;
    [_containerView addSubview:_placeholderLabel];

    // 发送按钮
    _sendButton = [UIButton buttonWithType:UIButtonTypeCustom];
    _sendButton.translatesAutoresizingMaskIntoConstraints = NO;
    _sendButton.layer.cornerRadius = 18;
    _sendButton.clipsToBounds = YES;
    UIImage *sendImage = [UIImage systemImageNamed:@"arrow.up" withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:18 weight:UIFontWeightBold]];
    [_sendButton setImage:sendImage forState:UIControlStateNormal];
    _sendButton.tintColor = [UIColor whiteColor];
    [_sendButton addTarget:self action:@selector(sendButtonTapped) forControlEvents:UIControlEventTouchUpInside];
    _sendButton.enabled = NO;

    // 发送按钮渐变背景
    _sendGradientLayer = [CAGradientLayer layer];
    _sendGradientLayer.colors = @[
        (id)[TechTheme.neonCyan colorWithAlphaComponent:0.9].CGColor,
        (id)[TechTheme.neonBlue colorWithAlphaComponent:0.9].CGColor
    ];
    _sendGradientLayer.startPoint = CGPointMake(0, 0);
    _sendGradientLayer.endPoint = CGPointMake(1, 1);
    _sendGradientLayer.cornerRadius = 18;
    [_sendButton.layer insertSublayer:_sendGradientLayer atIndex:0];

    [self addSubview:_sendButton];

    _textViewHeightConstraint = [_textView.heightAnchor constraintEqualToConstant:38];

    [NSLayoutConstraint activateConstraints:@[
        // 模糊背景铺满
        [_blurBackground.topAnchor constraintEqualToAnchor:self.topAnchor],
        [_blurBackground.leadingAnchor constraintEqualToAnchor:self.leadingAnchor],
        [_blurBackground.trailingAnchor constraintEqualToAnchor:self.trailingAnchor],
        [_blurBackground.bottomAnchor constraintEqualToAnchor:self.bottomAnchor],

        // 顶部发光线
        [topGlow.topAnchor constraintEqualToAnchor:self.topAnchor],
        [topGlow.leadingAnchor constraintEqualToAnchor:self.leadingAnchor],
        [topGlow.trailingAnchor constraintEqualToAnchor:self.trailingAnchor],
        [topGlow.heightAnchor constraintEqualToConstant:1],

        // 麦克风按钮
        [_voiceButton.leadingAnchor constraintEqualToAnchor:self.leadingAnchor constant:10],
        [_voiceButton.centerYAnchor constraintEqualToAnchor:_containerView.centerYAnchor],
        [_voiceButton.widthAnchor constraintEqualToConstant:40],
        [_voiceButton.heightAnchor constraintEqualToConstant:40],

        // 脉冲环与麦克风按钮重叠
        [_voicePulseRing.centerXAnchor constraintEqualToAnchor:_voiceButton.centerXAnchor],
        [_voicePulseRing.centerYAnchor constraintEqualToAnchor:_voiceButton.centerYAnchor],
        [_voicePulseRing.widthAnchor constraintEqualToConstant:40],
        [_voicePulseRing.heightAnchor constraintEqualToConstant:40],

        // 输入框容器
        [_containerView.topAnchor constraintEqualToAnchor:self.topAnchor constant:10],
        [_containerView.leadingAnchor constraintEqualToAnchor:_voiceButton.trailingAnchor constant:6],
        [_containerView.trailingAnchor constraintEqualToAnchor:_sendButton.leadingAnchor constant:-6],
        [_containerView.bottomAnchor constraintEqualToAnchor:self.safeAreaLayoutGuide.bottomAnchor constant:-10],

        // 发送按钮
        [_sendButton.trailingAnchor constraintEqualToAnchor:self.trailingAnchor constant:-10],
        [_sendButton.centerYAnchor constraintEqualToAnchor:_containerView.centerYAnchor],
        [_sendButton.widthAnchor constraintEqualToConstant:36],
        [_sendButton.heightAnchor constraintEqualToConstant:36],

        // 文字输入
        [_textView.topAnchor constraintEqualToAnchor:_containerView.topAnchor constant:3],
        [_textView.leadingAnchor constraintEqualToAnchor:_containerView.leadingAnchor constant:14],
        [_textView.trailingAnchor constraintEqualToAnchor:_containerView.trailingAnchor constant:-14],
        [_textView.bottomAnchor constraintEqualToAnchor:_containerView.bottomAnchor constant:-3],
        _textViewHeightConstraint,

        [_placeholderLabel.leadingAnchor constraintEqualToAnchor:_textView.leadingAnchor constant:5],
        [_placeholderLabel.centerYAnchor constraintEqualToAnchor:_textView.centerYAnchor]
    ]];
}

- (void)layoutSubviews {
    [super layoutSubviews];
    // 更新发送按钮渐变层 frame
    _sendGradientLayer.frame = _sendButton.bounds;
}

- (void)containerTapped {
    if (self.enabled) {
        [self.textView becomeFirstResponder];
    }
}

- (void)voiceButtonTapped {
    if ([self.delegate respondsToSelector:@selector(inputViewDidRequestVoiceInput:)]) {
        [self.delegate inputViewDidRequestVoiceInput:self];
    }
}

- (void)sendButtonTapped {
    if (self.loading) {
        if ([self.delegate respondsToSelector:@selector(inputViewDidRequestStop:)]) {
            [self.delegate inputViewDidRequestStop:self];
        }
        return;
    }
    NSString *text = [self.textView.text stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    if (text.length > 0 && self.enabled) {
        if ([self.delegate respondsToSelector:@selector(inputView:didSendMessage:)]) {
            [self.delegate inputView:self didSendMessage:text];
        }
    }
}

- (void)clearText {
    self.textView.text = @"";
    [self textViewDidChange:self.textView];
}

- (void)setText:(NSString *)text {
    self.textView.text = text ?: @"";
    [self textViewDidChange:self.textView];
}

- (void)setEnabled:(BOOL)enabled {
    _enabled = enabled;
    self.textView.editable = enabled;
    [self updateSendButton];
    self.alpha = enabled ? 1.0 : 0.6;
}

- (void)setLoading:(BOOL)loading {
    _loading = loading;
    [self updateSendButton];
}

- (void)updateSendButton {
    BOOL hasText = self.textView.text.length > 0;
    if (self.loading) {
        // 停止状态：红色霓虹
        self.sendButton.enabled = YES;
        UIImage *stopImage = [UIImage systemImageNamed:@"stop.fill"
                                     withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:16 weight:UIFontWeightBold]];
        [self.sendButton setImage:stopImage forState:UIControlStateNormal];
        self.sendButton.tintColor = [UIColor whiteColor];
        _sendGradientLayer.colors = @[
            (id)TechTheme.neonRed.CGColor,
            (id)[TechTheme.neonRed colorWithAlphaComponent:0.7].CGColor
        ];
        [TechTheme applyNeonGlow:self.sendButton color:TechTheme.neonRed radius:8];
    } else if (self.enabled && hasText) {
        // 可发送：青色霓虹渐变
        self.sendButton.enabled = YES;
        UIImage *sendImage = [UIImage systemImageNamed:@"arrow.up"
                                     withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:16 weight:UIFontWeightBold]];
        [self.sendButton setImage:sendImage forState:UIControlStateNormal];
        self.sendButton.tintColor = [UIColor whiteColor];
        _sendGradientLayer.colors = @[
            (id)[TechTheme.neonCyan colorWithAlphaComponent:0.95].CGColor,
            (id)[TechTheme.neonBlue colorWithAlphaComponent:0.9].CGColor
        ];
        [TechTheme applyNeonGlow:self.sendButton color:TechTheme.neonCyan radius:8];
    } else {
        // 禁用状态
        self.sendButton.enabled = NO;
        UIImage *sendImage = [UIImage systemImageNamed:@"arrow.up"
                                     withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:16 weight:UIFontWeightBold]];
        [self.sendButton setImage:sendImage forState:UIControlStateNormal];
        self.sendButton.tintColor = [UIColor whiteColor];
        _sendGradientLayer.colors = @[
            (id)[TechTheme.neonCyan colorWithAlphaComponent:0.25].CGColor,
            (id)[TechTheme.neonBlue colorWithAlphaComponent:0.2].CGColor
        ];
        self.sendButton.layer.shadowOpacity = 0;
    }
}

- (void)setVoiceInputActive:(BOOL)voiceInputActive {
    _voiceInputActive = voiceInputActive;
    self.voiceButton.selected = voiceInputActive;
    if (voiceInputActive) {
        self.voiceButton.tintColor = TechTheme.neonRed;
        self.voiceButton.backgroundColor = [TechTheme.neonRed colorWithAlphaComponent:0.15];
        _voicePulseRing.alpha = 1;
        [TechTheme addPulseAnimation:_voicePulseRing color:[TechTheme.neonRed colorWithAlphaComponent:0.4]];
    } else {
        self.voiceButton.tintColor = TechTheme.textSecondary;
        self.voiceButton.backgroundColor = [TechTheme.neonCyan colorWithAlphaComponent:0.08];
        _voicePulseRing.alpha = 0;
        [TechTheme removePulseAnimation:_voicePulseRing];
    }
}

#pragma mark - UITextViewDelegate

- (void)textViewDidChange:(UITextView *)textView {
    self.placeholderLabel.hidden = textView.text.length > 0;
    [self updateSendButton];
    
    CGFloat maxHeight = 120;
    CGSize sizeThatFits = [textView sizeThatFits:CGSizeMake(textView.frame.size.width, CGFLOAT_MAX)];
    CGFloat newHeight = MIN(MAX(sizeThatFits.height, 36), maxHeight);
    
    if (self.textViewHeightConstraint.constant != newHeight) {
        self.textViewHeightConstraint.constant = newHeight;
        textView.scrollEnabled = newHeight >= maxHeight;
        [self layoutIfNeeded];
    }
}

@end
