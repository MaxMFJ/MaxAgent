#import "ThinkingBlockView.h"
#import "TechTheme.h"

@interface ThinkingBlockView ()

@property (nonatomic, strong) UIButton *headerButton;
@property (nonatomic, strong) UILabel *contentLabel;
@property (nonatomic, strong) UIView *contentContainer;
@property (nonatomic, strong) NSLayoutConstraint *contentContainerHeightConstraint;
@property (nonatomic, assign) BOOL isCollapsed;

@end

@implementation ThinkingBlockView

- (instancetype)initWithThinkingContent:(NSString *)content isStreaming:(BOOL)streaming {
    self = [super initWithFrame:CGRectZero];
    if (self) {
        _thinkingContent = [content copy];
        _isStreaming = streaming;
        _isCollapsed = !streaming;  // 输出完成后默认折叠
        [self setupUI];
    }
    return self;
}

- (void)setupUI {
    self.translatesAutoresizingMaskIntoConstraints = NO;
    self.layer.cornerRadius = 10;
    self.clipsToBounds = YES;

    // 深色背景 + 紫色调
    self.backgroundColor = [TechTheme.neonPurple colorWithAlphaComponent:0.07];

    // 1px 霓虹紫色边框
    self.layer.borderWidth = 1.0;
    self.layer.borderColor = [TechTheme.neonPurple colorWithAlphaComponent:0.35].CGColor;

    // 发光效果
    [TechTheme applyNeonGlow:self color:[TechTheme.neonPurple colorWithAlphaComponent:0.3] radius:5];

    // --- Header 按钮 ---
    _headerButton = [UIButton buttonWithType:UIButtonTypeCustom];
    _headerButton.translatesAutoresizingMaskIntoConstraints = NO;
    _headerButton.contentHorizontalAlignment = UIControlContentHorizontalAlignmentLeft;
    _headerButton.titleLabel.font = [TechTheme fontMonoSize:11 weight:UIFontWeightMedium];
    [_headerButton setTitleColor:[TechTheme.neonPurple colorWithAlphaComponent:0.9] forState:UIControlStateNormal];
    [_headerButton addTarget:self action:@selector(headerTapped) forControlEvents:UIControlEventTouchUpInside];
    _headerButton.backgroundColor = [TechTheme.neonPurple colorWithAlphaComponent:0.1];
    [self addSubview:_headerButton];

    // --- 内容区 ---
    _contentContainer = [[UIView alloc] init];
    _contentContainer.translatesAutoresizingMaskIntoConstraints = NO;
    _contentContainer.clipsToBounds = YES;
    [self addSubview:_contentContainer];

    // 内容区顶部分隔线
    UIView *divider = [[UIView alloc] init];
    divider.translatesAutoresizingMaskIntoConstraints = NO;
    divider.backgroundColor = [TechTheme.neonPurple colorWithAlphaComponent:0.25];
    [_contentContainer addSubview:divider];
    [NSLayoutConstraint activateConstraints:@[
        [divider.topAnchor constraintEqualToAnchor:_contentContainer.topAnchor],
        [divider.leadingAnchor constraintEqualToAnchor:_contentContainer.leadingAnchor],
        [divider.trailingAnchor constraintEqualToAnchor:_contentContainer.trailingAnchor],
        [divider.heightAnchor constraintEqualToConstant:0.5]
    ]];

    _contentLabel = [[UILabel alloc] init];
    _contentLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _contentLabel.font = [TechTheme fontBodySize:11.5 weight:UIFontWeightRegular];
    _contentLabel.textColor = [TechTheme.neonPurple colorWithAlphaComponent:0.75];
    _contentLabel.numberOfLines = 0;
    _contentLabel.text = _thinkingContent;
    [_contentContainer addSubview:_contentLabel];

    [NSLayoutConstraint activateConstraints:@[
        [_headerButton.topAnchor constraintEqualToAnchor:self.topAnchor],
        [_headerButton.leadingAnchor constraintEqualToAnchor:self.leadingAnchor],
        [_headerButton.trailingAnchor constraintEqualToAnchor:self.trailingAnchor],
        [_headerButton.heightAnchor constraintEqualToConstant:30],

        [_contentContainer.topAnchor constraintEqualToAnchor:_headerButton.bottomAnchor],
        [_contentContainer.leadingAnchor constraintEqualToAnchor:self.leadingAnchor],
        [_contentContainer.trailingAnchor constraintEqualToAnchor:self.trailingAnchor],
        [_contentContainer.bottomAnchor constraintEqualToAnchor:self.bottomAnchor],

        [_contentLabel.topAnchor constraintEqualToAnchor:_contentContainer.topAnchor constant:8],
        [_contentLabel.leadingAnchor constraintEqualToAnchor:_contentContainer.leadingAnchor constant:12],
        [_contentLabel.trailingAnchor constraintEqualToAnchor:_contentContainer.trailingAnchor constant:-12],
        [_contentLabel.bottomAnchor constraintEqualToAnchor:_contentContainer.bottomAnchor constant:-8]
    ]];

    _contentContainerHeightConstraint = [_contentContainer.heightAnchor constraintEqualToConstant:0];

    [self updateHeaderTitle];
    [self updateContentVisibility];
}

- (void)setThinkingContent:(NSString *)thinkingContent {
    _thinkingContent = [thinkingContent copy];
    _contentLabel.text = thinkingContent;
}

- (void)setIsStreaming:(BOOL)isStreaming {
    if (_isStreaming != isStreaming) {
        _isStreaming = isStreaming;
        if (isStreaming) {
            // 扫描线动画：思考中
            [TechTheme addScanAnimation:_headerButton];
        } else {
            // 移除扫描线，自动折叠
            for (CALayer *l in [_headerButton.layer.sublayers copy]) {
                if ([l.name isEqualToString:@"ScanLine"]) [l removeFromSuperlayer];
            }
            if (!_isCollapsed) {
                [self setCollapsed:YES animated:YES];
            }
        }
    }
}

- (void)headerTapped {
    [self setCollapsed:!_isCollapsed animated:YES];
    if ([_delegate respondsToSelector:@selector(thinkingBlockViewDidToggle:)]) {
        [_delegate thinkingBlockViewDidToggle:self];
    }
}

- (void)setCollapsed:(BOOL)collapsed animated:(BOOL)animated {
    _isCollapsed = collapsed;
    [self updateHeaderTitle];

    void (^updateBlock)(void) = ^{
        [self updateContentVisibility];
    };

    if (animated) {
        [UIView animateWithDuration:0.28
                              delay:0
             usingSpringWithDamping:0.8
              initialSpringVelocity:0.3
                            options:UIViewAnimationOptionCurveEaseInOut
                         animations:updateBlock
                         completion:nil];
    } else {
        updateBlock();
    }
}

- (void)updateHeaderTitle {
    NSString *chevron = _isCollapsed ? @"▶" : @"▼";
    NSString *stream = _isStreaming ? @" ·" : @"";
    NSString *title = [NSString stringWithFormat:@"◈ NEURAL THINKING%@ %@", stream, chevron];
    [_headerButton setTitle:title forState:UIControlStateNormal];
}

- (void)updateContentVisibility {
    if (_isCollapsed) {
        _contentContainerHeightConstraint.priority = UILayoutPriorityRequired;
        _contentContainerHeightConstraint.constant = 0;
        _contentContainerHeightConstraint.active = YES;
    } else {
        _contentContainerHeightConstraint.active = NO;
    }
}

@end
