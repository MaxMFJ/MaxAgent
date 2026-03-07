#import "AgentLiveView.h"
#import "TechTheme.h"

static CGFloat const kHeaderHeight = 40.0;
static CGFloat const kContentPadding = 12.0;
static CGFloat const kCornerRadius = 12.0;
static CGFloat const kActionLogRowHeight = 28.0;
static CGFloat const kMaxExpandedHeight = 220.0;
static CGFloat const kGridSize = 20.0;

@interface AgentLiveView ()

@property (nonatomic, strong) UIView *containerView;
@property (nonatomic, strong) CAShapeLayer *gridLayer;
@property (nonatomic, strong) CAShapeLayer *borderLayer;
@property (nonatomic, strong) CAShapeLayer *cornerBracketsLayer;
@property (nonatomic, strong) UILabel *headerLabel;
@property (nonatomic, strong) UILabel *statusLabel;
@property (nonatomic, strong) UILabel *iterLabel;
@property (nonatomic, strong) UIButton *toggleButton;
@property (nonatomic, strong) UIButton *stopButton;
@property (nonatomic, strong) UIScrollView *contentScrollView;
@property (nonatomic, strong) UIStackView *actionLogStack;
@property (nonatomic, strong) NSLayoutConstraint *contentHeightConstraint;
@property (nonatomic, strong) NSLayoutConstraint *actionLogHeightConstraint;

@end

@implementation AgentLiveView

- (instancetype)initWithFrame:(CGRect)frame {
    self = [super initWithFrame:frame];
    if (self) {
        [self setupUI];
        _isExpanded = YES;
    }
    return self;
}

- (instancetype)initWithCoder:(NSCoder *)coder {
    self = [super initWithCoder:coder];
    if (self) {
        [self setupUI];
        _isExpanded = YES;
    }
    return self;
}

- (void)setupUI {
    self.backgroundColor = [UIColor clearColor];
    self.clipsToBounds = NO;

    _containerView = [[UIView alloc] init];
    _containerView.backgroundColor = [TechTheme backgroundCard];
    _containerView.layer.cornerRadius = kCornerRadius;
    _containerView.clipsToBounds = YES;
    _containerView.translatesAutoresizingMaskIntoConstraints = NO;
    [self addSubview:_containerView];

    [self setupGridBackground];
    [self setupHeader];
    [self setupContent];
    [self setupBorderAndCorners];

    [NSLayoutConstraint activateConstraints:@[
        [_containerView.topAnchor constraintEqualToAnchor:self.topAnchor],
        [_containerView.leadingAnchor constraintEqualToAnchor:self.leadingAnchor],
        [_containerView.trailingAnchor constraintEqualToAnchor:self.trailingAnchor],
        [_containerView.bottomAnchor constraintEqualToAnchor:self.bottomAnchor],
    ]];
}

- (void)setupGridBackground {
    _gridLayer = [CAShapeLayer layer];
    _gridLayer.name = @"GridLayer";
    _gridLayer.strokeColor = [[TechTheme neonCyan] colorWithAlphaComponent:0.12].CGColor;
    _gridLayer.lineWidth = 0.5;
    _gridLayer.fillColor = nil;
    [_containerView.layer insertSublayer:_gridLayer atIndex:0];
}

- (void)setupHeader {
    UIView *header = [[UIView alloc] init];
    header.backgroundColor = [TechTheme backgroundSecondary];
    header.translatesAutoresizingMaskIntoConstraints = NO;
    [_containerView addSubview:header];

    _headerLabel = [[UILabel alloc] init];
    _headerLabel.font = [TechTheme fontMonoSize:10 weight:UIFontWeightBold];
    _headerLabel.textColor = [TechTheme neonCyan];
    _headerLabel.text = @"MACAGENT | NEURAL LINK";
    _headerLabel.translatesAutoresizingMaskIntoConstraints = NO;
    [header addSubview:_headerLabel];

    _statusLabel = [[UILabel alloc] init];
    _statusLabel.font = [TechTheme fontMonoSize:9 weight:UIFontWeightMedium];
    _statusLabel.textColor = [TechTheme textSecondary];
    _statusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    [header addSubview:_statusLabel];

    _iterLabel = [[UILabel alloc] init];
    _iterLabel.font = [TechTheme fontMonoSize:9 weight:UIFontWeightMedium];
    _iterLabel.textColor = [[TechTheme textSecondary] colorWithAlphaComponent:0.8];
    _iterLabel.translatesAutoresizingMaskIntoConstraints = NO;
    [header addSubview:_iterLabel];

    _stopButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [_stopButton setImage:[UIImage systemImageNamed:@"stop.fill"] forState:UIControlStateNormal];
    _stopButton.tintColor = [TechTheme neonRed];
    [_stopButton addTarget:self action:@selector(stopTapped:) forControlEvents:UIControlEventTouchUpInside];
    _stopButton.translatesAutoresizingMaskIntoConstraints = NO;
    [header addSubview:_stopButton];

    _toggleButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [_toggleButton setImage:[UIImage systemImageNamed:@"chevron.up"] forState:UIControlStateNormal];
    _toggleButton.tintColor = [TechTheme textSecondary];
    [_toggleButton addTarget:self action:@selector(toggleTapped:) forControlEvents:UIControlEventTouchUpInside];
    _toggleButton.translatesAutoresizingMaskIntoConstraints = NO;
    [header addSubview:_toggleButton];

    [NSLayoutConstraint activateConstraints:@[
        [header.topAnchor constraintEqualToAnchor:_containerView.topAnchor],
        [header.leadingAnchor constraintEqualToAnchor:_containerView.leadingAnchor],
        [header.trailingAnchor constraintEqualToAnchor:_containerView.trailingAnchor],
        [header.heightAnchor constraintEqualToConstant:kHeaderHeight],

        [_headerLabel.leadingAnchor constraintEqualToAnchor:header.leadingAnchor constant:kContentPadding],
        [_headerLabel.centerYAnchor constraintEqualToAnchor:header.centerYAnchor],

        [_statusLabel.leadingAnchor constraintEqualToAnchor:_headerLabel.trailingAnchor constant:8],
        [_statusLabel.centerYAnchor constraintEqualToAnchor:header.centerYAnchor],

        [_iterLabel.leadingAnchor constraintEqualToAnchor:_statusLabel.trailingAnchor constant:12],
        [_iterLabel.centerYAnchor constraintEqualToAnchor:header.centerYAnchor],

        [_stopButton.trailingAnchor constraintEqualToAnchor:_toggleButton.leadingAnchor constant:-4],
        [_stopButton.centerYAnchor constraintEqualToAnchor:header.centerYAnchor],
        [_stopButton.widthAnchor constraintEqualToConstant:32],
        [_stopButton.heightAnchor constraintEqualToConstant:32],

        [_toggleButton.trailingAnchor constraintEqualToAnchor:header.trailingAnchor constant:-kContentPadding],
        [_toggleButton.centerYAnchor constraintEqualToAnchor:header.centerYAnchor],
        [_toggleButton.widthAnchor constraintEqualToConstant:32],
        [_toggleButton.heightAnchor constraintEqualToConstant:32],
    ]];
}

- (void)setupContent {
    _contentScrollView = [[UIScrollView alloc] init];
    _contentScrollView.showsVerticalScrollIndicator = NO;
    _contentScrollView.translatesAutoresizingMaskIntoConstraints = NO;
    [_containerView addSubview:_contentScrollView];

    _actionLogStack = [[UIStackView alloc] init];
    _actionLogStack.axis = UILayoutConstraintAxisVertical;
    _actionLogStack.spacing = 2;
    _actionLogStack.translatesAutoresizingMaskIntoConstraints = NO;
    [_contentScrollView addSubview:_actionLogStack];

    [NSLayoutConstraint activateConstraints:@[
        [_contentScrollView.topAnchor constraintEqualToAnchor:_containerView.topAnchor constant:kHeaderHeight],
        [_contentScrollView.leadingAnchor constraintEqualToAnchor:_containerView.leadingAnchor],
        [_contentScrollView.trailingAnchor constraintEqualToAnchor:_containerView.trailingAnchor],
        [_contentScrollView.bottomAnchor constraintEqualToAnchor:_containerView.bottomAnchor],

        [_actionLogStack.topAnchor constraintEqualToAnchor:_contentScrollView.topAnchor constant:kContentPadding],
        [_actionLogStack.leadingAnchor constraintEqualToAnchor:_contentScrollView.leadingAnchor constant:kContentPadding],
        [_actionLogStack.trailingAnchor constraintEqualToAnchor:_contentScrollView.trailingAnchor constant:-kContentPadding],
        [_actionLogStack.bottomAnchor constraintEqualToAnchor:_contentScrollView.bottomAnchor constant:-kContentPadding],
        [_actionLogStack.widthAnchor constraintEqualToAnchor:_contentScrollView.widthAnchor constant:-(kContentPadding * 2)],
    ]];
}

- (void)setupBorderAndCorners {
    _borderLayer = [CAShapeLayer layer];
    _borderLayer.name = @"BorderLayer";
    _borderLayer.strokeColor = [TechTheme neonCyan].CGColor;
    _borderLayer.lineWidth = 1.0;
    _borderLayer.fillColor = nil;
    _borderLayer.opacity = 0.6;
    [_containerView.layer addSublayer:_borderLayer];

    _cornerBracketsLayer = [CAShapeLayer layer];
    _cornerBracketsLayer.name = @"CornerBrackets";
    _cornerBracketsLayer.strokeColor = [[TechTheme neonCyan] colorWithAlphaComponent:0.7].CGColor;
    _cornerBracketsLayer.lineWidth = 1.0;
    _cornerBracketsLayer.fillColor = nil;
    [_containerView.layer addSublayer:_cornerBracketsLayer];
}

- (void)layoutSubviews {
    [super layoutSubviews];
    [self updateGridPath];
    [self updateBorderPath];
}

- (void)updateGridPath {
    CGRect bounds = _containerView.bounds;
    if (bounds.size.width <= 0 || bounds.size.height <= 0) return;

    UIBezierPath *path = [UIBezierPath bezierPath];
    CGFloat w = bounds.size.width;
    CGFloat h = bounds.size.height;

    for (CGFloat x = 0; x <= w + kGridSize; x += kGridSize) {
        [path moveToPoint:CGPointMake(x, 0)];
        [path addLineToPoint:CGPointMake(x, h)];
    }
    for (CGFloat y = 0; y <= h + kGridSize; y += kGridSize) {
        [path moveToPoint:CGPointMake(0, y)];
        [path addLineToPoint:CGPointMake(w, y)];
    }
    _gridLayer.path = path.CGPath;
    _gridLayer.frame = bounds;
}

- (void)updateBorderPath {
    CGRect bounds = _containerView.bounds;
    if (bounds.size.width <= 0 || bounds.size.height <= 0) return;

    _borderLayer.path = [UIBezierPath bezierPathWithRoundedRect:bounds cornerRadius:kCornerRadius].CGPath;
    _borderLayer.frame = bounds;

    CGFloat pad = 12;
    CGFloat bw = 16;
    CGFloat t = 2;
    UIBezierPath *corners = [UIBezierPath bezierPath];
    // TL
    [corners moveToPoint:CGPointMake(pad, pad)];
    [corners addLineToPoint:CGPointMake(pad + bw, pad)];
    [corners addLineToPoint:CGPointMake(pad + bw, pad + t)];
    [corners moveToPoint:CGPointMake(pad, pad)];
    [corners addLineToPoint:CGPointMake(pad, pad + bw)];
    [corners addLineToPoint:CGPointMake(pad + t, pad + bw)];
    // TR
    [corners moveToPoint:CGPointMake(bounds.size.width - pad, pad)];
    [corners addLineToPoint:CGPointMake(bounds.size.width - pad - bw, pad)];
    [corners addLineToPoint:CGPointMake(bounds.size.width - pad - bw, pad + t)];
    [corners moveToPoint:CGPointMake(bounds.size.width - pad, pad)];
    [corners addLineToPoint:CGPointMake(bounds.size.width - pad, pad + bw)];
    [corners addLineToPoint:CGPointMake(bounds.size.width - pad - t, pad + bw)];
    // BL
    [corners moveToPoint:CGPointMake(pad, bounds.size.height - pad)];
    [corners addLineToPoint:CGPointMake(pad + bw, bounds.size.height - pad)];
    [corners addLineToPoint:CGPointMake(pad + bw, bounds.size.height - pad - t)];
    [corners moveToPoint:CGPointMake(pad, bounds.size.height - pad)];
    [corners addLineToPoint:CGPointMake(pad, bounds.size.height - pad - bw)];
    [corners addLineToPoint:CGPointMake(pad + t, bounds.size.height - pad - bw)];
    // BR
    [corners moveToPoint:CGPointMake(bounds.size.width - pad, bounds.size.height - pad)];
    [corners addLineToPoint:CGPointMake(bounds.size.width - pad - bw, bounds.size.height - pad)];
    [corners addLineToPoint:CGPointMake(bounds.size.width - pad - bw, bounds.size.height - pad - t)];
    [corners moveToPoint:CGPointMake(bounds.size.width - pad, bounds.size.height - pad)];
    [corners addLineToPoint:CGPointMake(bounds.size.width - pad, bounds.size.height - pad - bw)];
    [corners addLineToPoint:CGPointMake(bounds.size.width - pad - t, bounds.size.height - pad - bw)];

    _cornerBracketsLayer.path = corners.CGPath;
    _cornerBracketsLayer.frame = bounds;
}

#pragma mark - Public

- (BOOL)isRunning {
    return _taskProgress.isRunning;
}

- (void)updateWithTaskProgress:(TaskProgress *)progress {
    _taskProgress = progress;
    [self updateUI];
}

- (void)handleActionPlan:(NSDictionary *)data {
    if (!_taskProgress) {
        NSString *taskId = data[@"task_id"] ?: @"";
        _taskProgress = [TaskProgress progressWithTaskId:taskId description:@""];
        _taskProgress.isRunning = YES;
    }
    [_taskProgress handleActionPlan:data];
    [self updateUI];
}

- (void)handleActionExecuting:(NSDictionary *)data {
    [_taskProgress handleActionExecuting:data];
    [self updateUI];
}

- (void)handleActionResult:(NSDictionary *)data {
    [_taskProgress handleActionResult:data];
    [self updateUI];
}

- (void)handleTaskComplete:(NSDictionary *)data {
    [_taskProgress handleTaskComplete:data];
    [self updateUI];
}

- (void)handleTaskStopped:(NSDictionary *)data {
    [_taskProgress handleTaskStopped:data];
    [self updateUI];
}

- (void)handleLLMRequestStart:(NSDictionary *)data {
    [_taskProgress handleLLMRequestStart:data];
    [self updateUI];
}

- (void)handleLLMRequestEnd:(NSDictionary *)data {
    [_taskProgress handleLLMRequestEnd:data];
    [self updateUI];
}

- (void)reset {
    _taskProgress = nil;
    [self rebuildActionLogs];
    _statusLabel.text = @"";
    _iterLabel.text = @"";
    _headerLabel.text = @"MACAGENT | NEURAL LINK";
    _stopButton.hidden = NO;
    [self updateBorderColor:NO];
}

- (CGFloat)requiredHeight {
    CGFloat base = kHeaderHeight + kContentPadding * 2;
    if (!_isExpanded || !_taskProgress || _taskProgress.actionLogs.count == 0) {
        return base;
    }
    CGFloat logHeight = MIN(_taskProgress.actionLogs.count * kActionLogRowHeight, kMaxExpandedHeight - base);
    return base + logHeight;
}

#pragma mark - Private

- (void)updateUI {
    if (!_taskProgress) return;

    BOOL isThinking = _taskProgress.isLLMRequesting;
    NSString *displayTool = [self lastNonLLMActionType];

    if (isThinking) {
        _headerLabel.text = @"MACAGENT | NEURAL LINK • ACTIVE";
        _statusLabel.text = @"PROCESSING...";
        _statusLabel.textColor = [TechTheme neonPurple];
        [self updateBorderColor:YES];
    } else if (displayTool.length > 0) {
        _headerLabel.text = @"MACAGENT | NEURAL LINK • EXEC";
        _statusLabel.text = [NSString stringWithFormat:@"RUN_%@", [displayTool uppercaseString]];
        _statusLabel.textColor = [TechTheme neonOrange];
        [self updateBorderColor:NO];
    } else {
        _headerLabel.text = @"MACAGENT | NEURAL LINK";
        _statusLabel.text = [self standbyStatusText];
        _statusLabel.textColor = [TechTheme textSecondary];
        [self updateBorderColor:NO];
    }

    _iterLabel.text = [NSString stringWithFormat:@"ITER:%ld", (long)_taskProgress.currentIteration];
    _stopButton.hidden = !_taskProgress.isRunning;
    [self rebuildActionLogs];
}

- (NSString *)lastNonLLMActionType {
    for (ActionLogEntry *e in [_taskProgress.actionLogs reverseObjectEnumerator]) {
        if (![e.actionType isEqualToString:@"llm_request"]) {
            return [self toolDisplayName:e.actionType];
        }
    }
    return nil;
}

- (NSString *)toolDisplayName:(NSString *)raw {
    NSString *t = [raw lowercaseString];
    if ([t containsString:@"web_search"] || [t containsString:@"search"]) return @"SEARCH";
    if ([t containsString:@"run_shell"] || [t containsString:@"shell"]) return @"SHELL";
    if ([t containsString:@"read_file"] || [t containsString:@"write_file"] || [t containsString:@"file"]) return @"FILE";
    if ([t containsString:@"screenshot"]) return @"SCREENSHOT";
    if ([t containsString:@"call_tool"]) return @"TOOL";
    return [[raw uppercaseString] stringByReplacingOccurrencesOfString:@"_" withString:@" "];
}

- (NSString *)standbyStatusText {
    if (_taskProgress.isCompleted) {
        return _taskProgress.finalSuccess ? @"COMPLETED" : @"FAILED";
    }
    return @"STANDBY";
}

- (void)updateBorderColor:(BOOL)thinking {
    _borderLayer.strokeColor = (thinking ? [TechTheme neonPurple] : [TechTheme neonCyan]).CGColor;
    _borderLayer.opacity = thinking ? 0.9 : 0.5;
    _cornerBracketsLayer.strokeColor = (thinking ? [TechTheme neonPurple] : [TechTheme neonCyan]).CGColor;
}

- (void)rebuildActionLogs {
    for (UIView *v in _actionLogStack.arrangedSubviews) {
        [v removeFromSuperview];
    }

    if (!_isExpanded || !_taskProgress || _taskProgress.actionLogs.count == 0) return;

    for (ActionLogEntry *entry in _taskProgress.actionLogs) {
        UILabel *row = [[UILabel alloc] init];
        row.font = [TechTheme fontMonoSize:9 weight:UIFontWeightMedium];
        row.textColor = [TechTheme textSecondary];
        row.text = [NSString stringWithFormat:@"#%ld %@ %@", (long)entry.iteration, [entry statusIcon], [entry shortDescription]];
        if (entry.status == ActionLogStatusExecuting) {
            row.textColor = [TechTheme neonCyan];
        } else if (entry.status == ActionLogStatusFailed) {
            row.textColor = [TechTheme neonRed];
        } else if (entry.status == ActionLogStatusSuccess) {
            row.textColor = [TechTheme neonGreen];
        }
        row.translatesAutoresizingMaskIntoConstraints = NO;
        [row.heightAnchor constraintEqualToConstant:kActionLogRowHeight].active = YES;
        [_actionLogStack addArrangedSubview:row];
    }
}

- (void)toggleTapped:(UIButton *)sender {
    _isExpanded = !_isExpanded;
    [_toggleButton setImage:[UIImage systemImageNamed:_isExpanded ? @"chevron.up" : @"chevron.down"] forState:UIControlStateNormal];
    [self rebuildActionLogs];
    if ([_delegate respondsToSelector:@selector(agentLiveViewDidToggle:)]) {
        [_delegate agentLiveViewDidToggle:self];
    }
}

- (void)stopTapped:(UIButton *)sender {
    if ([_delegate respondsToSelector:@selector(agentLiveViewDidRequestStop:)]) {
        [_delegate agentLiveViewDidRequestStop:self];
    }
}

@end
