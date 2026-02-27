#import "ThinkingBlockView.h"

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
    self.layer.cornerRadius = 6;
    self.backgroundColor = [UIColor colorWithWhite:0.95 alpha:0.5];
    if (@available(iOS 13.0, *)) {
        self.backgroundColor = [UIColor colorWithDynamicProvider:^UIColor * _Nonnull(UITraitCollection * _Nonnull traitCollection) {
            return traitCollection.userInterfaceStyle == UIUserInterfaceStyleDark
                ? [UIColor colorWithWhite:0.2 alpha:0.5]
                : [UIColor colorWithWhite:0.95 alpha:0.5];
        }];
    }
    
    _headerButton = [UIButton buttonWithType:UIButtonTypeSystem];
    _headerButton.translatesAutoresizingMaskIntoConstraints = NO;
    _headerButton.contentHorizontalAlignment = UIControlContentHorizontalAlignmentLeft;
    _headerButton.titleLabel.font = [UIFont systemFontOfSize:12 weight:UIFontWeightMedium];
    [_headerButton setTitleColor:[UIColor secondaryLabelColor] forState:UIControlStateNormal];
    [_headerButton addTarget:self action:@selector(headerTapped) forControlEvents:UIControlEventTouchUpInside];
    _headerButton.backgroundColor = [UIColor colorWithWhite:0.9 alpha:0.5];
    if (@available(iOS 13.0, *)) {
        _headerButton.backgroundColor = [UIColor colorWithDynamicProvider:^UIColor * _Nonnull(UITraitCollection * _Nonnull traitCollection) {
            return traitCollection.userInterfaceStyle == UIUserInterfaceStyleDark
                ? [UIColor colorWithWhite:0.25 alpha:0.5]
                : [UIColor colorWithWhite:0.9 alpha:0.5];
        }];
    }
    [self addSubview:_headerButton];
    
    _contentContainer = [[UIView alloc] init];
    _contentContainer.translatesAutoresizingMaskIntoConstraints = NO;
    _contentContainer.clipsToBounds = YES;
    [self addSubview:_contentContainer];
    
    _contentLabel = [[UILabel alloc] init];
    _contentLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _contentLabel.font = [UIFont systemFontOfSize:12];
    _contentLabel.textColor = [UIColor secondaryLabelColor];
    _contentLabel.numberOfLines = 0;
    _contentLabel.text = _thinkingContent;
    [_contentContainer addSubview:_contentLabel];
    
    [NSLayoutConstraint activateConstraints:@[
        [_headerButton.topAnchor constraintEqualToAnchor:self.topAnchor],
        [_headerButton.leadingAnchor constraintEqualToAnchor:self.leadingAnchor],
        [_headerButton.trailingAnchor constraintEqualToAnchor:self.trailingAnchor],
        [_headerButton.heightAnchor constraintEqualToConstant:32],
        
        [_contentContainer.topAnchor constraintEqualToAnchor:_headerButton.bottomAnchor constant:4],
        [_contentContainer.leadingAnchor constraintEqualToAnchor:self.leadingAnchor],
        [_contentContainer.trailingAnchor constraintEqualToAnchor:self.trailingAnchor],
        [_contentContainer.bottomAnchor constraintEqualToAnchor:self.bottomAnchor],
        
        [_contentLabel.topAnchor constraintEqualToAnchor:_contentContainer.topAnchor],
        [_contentLabel.leadingAnchor constraintEqualToAnchor:_contentContainer.leadingAnchor],
        [_contentLabel.trailingAnchor constraintEqualToAnchor:_contentContainer.trailingAnchor],
        [_contentLabel.bottomAnchor constraintEqualToAnchor:_contentContainer.bottomAnchor]
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
        if (!isStreaming && !_isCollapsed) {
            [self setCollapsed:YES animated:YES];
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
        [UIView animateWithDuration:0.2 animations:updateBlock];
    } else {
        updateBlock();
    }
}

- (void)updateHeaderTitle {
    NSString *chevron = _isCollapsed ? @"▼" : @"▲";
    NSString *title = [NSString stringWithFormat:@"🧠 思考过程 %@", chevron];
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
