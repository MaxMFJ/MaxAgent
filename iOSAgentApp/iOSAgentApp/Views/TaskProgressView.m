#import "TaskProgressView.h"

static CGFloat const kHeaderHeight = 44.0;
static CGFloat const kProgressBarHeight = 4.0;
static CGFloat const kActionLogRowHeight = 36.0;
static CGFloat const kMaxExpandedHeight = 300.0;
static CGFloat const kPadding = 12.0;
static CGFloat const kCornerRadius = 12.0;

@interface ActionLogCell : UITableViewCell
@property (nonatomic, strong) UILabel *statusLabel;
@property (nonatomic, strong) UILabel *iterationLabel;
@property (nonatomic, strong) UILabel *descriptionLabel;
@property (nonatomic, strong) UILabel *timeLabel;
@end

@implementation ActionLogCell

- (instancetype)initWithStyle:(UITableViewCellStyle)style reuseIdentifier:(NSString *)reuseIdentifier {
    self = [super initWithStyle:style reuseIdentifier:reuseIdentifier];
    if (self) {
        self.backgroundColor = [UIColor clearColor];
        self.selectionStyle = UITableViewCellSelectionStyleNone;
        
        _statusLabel = [[UILabel alloc] init];
        _statusLabel.font = [UIFont systemFontOfSize:14];
        _statusLabel.translatesAutoresizingMaskIntoConstraints = NO;
        [self.contentView addSubview:_statusLabel];
        
        _iterationLabel = [[UILabel alloc] init];
        _iterationLabel.font = [UIFont monospacedDigitSystemFontOfSize:11 weight:UIFontWeightMedium];
        _iterationLabel.textColor = [UIColor secondaryLabelColor];
        _iterationLabel.translatesAutoresizingMaskIntoConstraints = NO;
        [self.contentView addSubview:_iterationLabel];
        
        _descriptionLabel = [[UILabel alloc] init];
        _descriptionLabel.font = [UIFont systemFontOfSize:13];
        _descriptionLabel.textColor = [UIColor labelColor];
        _descriptionLabel.lineBreakMode = NSLineBreakByTruncatingTail;
        _descriptionLabel.translatesAutoresizingMaskIntoConstraints = NO;
        [self.contentView addSubview:_descriptionLabel];
        
        _timeLabel = [[UILabel alloc] init];
        _timeLabel.font = [UIFont monospacedDigitSystemFontOfSize:10 weight:UIFontWeightRegular];
        _timeLabel.textColor = [UIColor tertiaryLabelColor];
        _timeLabel.textAlignment = NSTextAlignmentRight;
        _timeLabel.translatesAutoresizingMaskIntoConstraints = NO;
        [self.contentView addSubview:_timeLabel];
        
        [NSLayoutConstraint activateConstraints:
             @[[_statusLabel.leadingAnchor constraintEqualToAnchor:self.contentView.leadingAnchor constant:kPadding],
            [_statusLabel.centerYAnchor constraintEqualToAnchor:self.contentView.centerYAnchor],
            [_statusLabel.widthAnchor constraintEqualToConstant:24],
            
            [_iterationLabel.leadingAnchor constraintEqualToAnchor:_statusLabel.trailingAnchor constant:4],
            [_iterationLabel.centerYAnchor constraintEqualToAnchor:self.contentView.centerYAnchor],
            [_iterationLabel.widthAnchor constraintEqualToConstant:28],
            
            [_timeLabel.trailingAnchor constraintEqualToAnchor:self.contentView.trailingAnchor constant:-kPadding],
            [_timeLabel.centerYAnchor constraintEqualToAnchor:self.contentView.centerYAnchor],
            [_timeLabel.widthAnchor constraintEqualToConstant:50],
            
            [_descriptionLabel.leadingAnchor constraintEqualToAnchor:_iterationLabel.trailingAnchor constant:8],
            [_descriptionLabel.trailingAnchor constraintEqualToAnchor:_timeLabel.leadingAnchor constant:-8],
            [_descriptionLabel.centerYAnchor constraintEqualToAnchor:self.contentView.centerYAnchor]
        ]];
    }
    return self;
}

- (void)configureWithEntry:(ActionLogEntry *)entry {
    self.statusLabel.text = [entry statusIcon];
    self.iterationLabel.text = [NSString stringWithFormat:@"#%ld", (long)entry.iteration];
    self.descriptionLabel.text = [entry shortDescription];
    
    if (entry.executionTimeMs > 0) {
        if (entry.executionTimeMs >= 1000) {
            self.timeLabel.text = [NSString stringWithFormat:@"%.1fs", entry.executionTimeMs / 1000.0];
        } else {
            self.timeLabel.text = [NSString stringWithFormat:@"%ldms", (long)entry.executionTimeMs];
        }
    } else {
        self.timeLabel.text = @"";
    }
    
    // 根据状态设置颜色
    switch (entry.status) {
        case ActionLogStatusFailed:
            self.descriptionLabel.textColor = [UIColor systemRedColor];
            break;
        case ActionLogStatusExecuting:
            self.descriptionLabel.textColor = [UIColor systemBlueColor];
            break;
        default:
            self.descriptionLabel.textColor = [UIColor labelColor];
            break;
    }
}

@end

#pragma mark - TaskProgressView

@interface TaskProgressView () <UITableViewDataSource, UITableViewDelegate>

@property (nonatomic, strong) UIView *headerView;
@property (nonatomic, strong) UILabel *titleLabel;
@property (nonatomic, strong) UILabel *statusLabel;
@property (nonatomic, strong) UIButton *toggleButton;
@property (nonatomic, strong) UIButton *stopButton;
@property (nonatomic, strong) UIProgressView *progressBar;
@property (nonatomic, strong) UITableView *actionLogsTable;
@property (nonatomic, strong) UIActivityIndicatorView *loadingIndicator;
@property (nonatomic, strong) UILabel *llmStatusLabel;

@property (nonatomic, strong) NSLayoutConstraint *tableHeightConstraint;

@end

@implementation TaskProgressView

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
    self.backgroundColor = [UIColor secondarySystemBackgroundColor];
    self.layer.cornerRadius = kCornerRadius;
    self.clipsToBounds = YES;
    
    // Header
    _headerView = [[UIView alloc] init];
    _headerView.backgroundColor = [UIColor tertiarySystemBackgroundColor];
    _headerView.translatesAutoresizingMaskIntoConstraints = NO;
    [self addSubview:_headerView];
    
    // Loading indicator
    _loadingIndicator = [[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleMedium];
    _loadingIndicator.translatesAutoresizingMaskIntoConstraints = NO;
    _loadingIndicator.hidesWhenStopped = YES;
    [_headerView addSubview:_loadingIndicator];
    
    // Title label
    _titleLabel = [[UILabel alloc] init];
    _titleLabel.text = @"🤖 任务执行中";
    _titleLabel.font = [UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    _titleLabel.textColor = [UIColor labelColor];
    _titleLabel.translatesAutoresizingMaskIntoConstraints = NO;
    [_headerView addSubview:_titleLabel];
    
    // Status label (步骤 3/10)
    _statusLabel = [[UILabel alloc] init];
    _statusLabel.font = [UIFont monospacedDigitSystemFontOfSize:12 weight:UIFontWeightMedium];
    _statusLabel.textColor = [UIColor secondaryLabelColor];
    _statusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    [_headerView addSubview:_statusLabel];
    
    // Toggle button
    _toggleButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [_toggleButton setImage:[UIImage systemImageNamed:@"chevron.up"] forState:UIControlStateNormal];
    [_toggleButton addTarget:self action:@selector(toggleTapped:) forControlEvents:UIControlEventTouchUpInside];
    _toggleButton.translatesAutoresizingMaskIntoConstraints = NO;
    [_headerView addSubview:_toggleButton];
    
    // Stop button
    _stopButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [_stopButton setImage:[UIImage systemImageNamed:@"stop.fill"] forState:UIControlStateNormal];
    _stopButton.tintColor = [UIColor systemRedColor];
    [_stopButton addTarget:self action:@selector(stopTapped:) forControlEvents:UIControlEventTouchUpInside];
    _stopButton.translatesAutoresizingMaskIntoConstraints = NO;
    [_headerView addSubview:_stopButton];
    
    // Progress bar
    _progressBar = [[UIProgressView alloc] initWithProgressViewStyle:UIProgressViewStyleBar];
    _progressBar.progressTintColor = [UIColor systemBlueColor];
    _progressBar.trackTintColor = [UIColor systemGray5Color];
    _progressBar.translatesAutoresizingMaskIntoConstraints = NO;
    [self addSubview:_progressBar];
    
    // LLM status label
    _llmStatusLabel = [[UILabel alloc] init];
    _llmStatusLabel.text = @"☁️ LLM 请求中...";
    _llmStatusLabel.font = [UIFont systemFontOfSize:11];
    _llmStatusLabel.textColor = [UIColor systemBlueColor];
    _llmStatusLabel.hidden = YES;
    _llmStatusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    [self addSubview:_llmStatusLabel];
    
    // Action logs table
    _actionLogsTable = [[UITableView alloc] initWithFrame:CGRectZero style:UITableViewStylePlain];
    _actionLogsTable.backgroundColor = [UIColor clearColor];
    _actionLogsTable.separatorStyle = UITableViewCellSeparatorStyleNone;
    _actionLogsTable.dataSource = self;
    _actionLogsTable.delegate = self;
    _actionLogsTable.rowHeight = kActionLogRowHeight;
    _actionLogsTable.translatesAutoresizingMaskIntoConstraints = NO;
    [_actionLogsTable registerClass:[ActionLogCell class] forCellReuseIdentifier:@"ActionLogCell"];
    [self addSubview:_actionLogsTable];
    
    // Constraints
    _tableHeightConstraint = [_actionLogsTable.heightAnchor constraintEqualToConstant:0];
    
    [NSLayoutConstraint activateConstraints:@[
        // Header
        [_headerView.topAnchor constraintEqualToAnchor:self.topAnchor],
        [_headerView.leadingAnchor constraintEqualToAnchor:self.leadingAnchor],
        [_headerView.trailingAnchor constraintEqualToAnchor:self.trailingAnchor],
        [_headerView.heightAnchor constraintEqualToConstant:kHeaderHeight],
        
        // Loading indicator
        [_loadingIndicator.leadingAnchor constraintEqualToAnchor:_headerView.leadingAnchor constant:kPadding],
        [_loadingIndicator.centerYAnchor constraintEqualToAnchor:_headerView.centerYAnchor],
        
        // Title
        [_titleLabel.leadingAnchor constraintEqualToAnchor:_loadingIndicator.trailingAnchor constant:8],
        [_titleLabel.centerYAnchor constraintEqualToAnchor:_headerView.centerYAnchor],
        
        // Status
        [_statusLabel.leadingAnchor constraintEqualToAnchor:_titleLabel.trailingAnchor constant:12],
        [_statusLabel.centerYAnchor constraintEqualToAnchor:_headerView.centerYAnchor],
        
        // Stop button
        [_stopButton.trailingAnchor constraintEqualToAnchor:_toggleButton.leadingAnchor constant:-8],
        [_stopButton.centerYAnchor constraintEqualToAnchor:_headerView.centerYAnchor],
        [_stopButton.widthAnchor constraintEqualToConstant:32],
        [_stopButton.heightAnchor constraintEqualToConstant:32],
        
        // Toggle button
        [_toggleButton.trailingAnchor constraintEqualToAnchor:_headerView.trailingAnchor constant:-kPadding],
        [_toggleButton.centerYAnchor constraintEqualToAnchor:_headerView.centerYAnchor],
        [_toggleButton.widthAnchor constraintEqualToConstant:32],
        [_toggleButton.heightAnchor constraintEqualToConstant:32],
        
        // Progress bar
        [_progressBar.topAnchor constraintEqualToAnchor:_headerView.bottomAnchor],
        [_progressBar.leadingAnchor constraintEqualToAnchor:self.leadingAnchor],
        [_progressBar.trailingAnchor constraintEqualToAnchor:self.trailingAnchor],
        [_progressBar.heightAnchor constraintEqualToConstant:kProgressBarHeight],
        
        // LLM status
        [_llmStatusLabel.topAnchor constraintEqualToAnchor:_progressBar.bottomAnchor constant:4],
        [_llmStatusLabel.leadingAnchor constraintEqualToAnchor:self.leadingAnchor constant:kPadding],
        
        // Table
        [_actionLogsTable.topAnchor constraintEqualToAnchor:_progressBar.bottomAnchor constant:4],
        [_actionLogsTable.leadingAnchor constraintEqualToAnchor:self.leadingAnchor],
        [_actionLogsTable.trailingAnchor constraintEqualToAnchor:self.trailingAnchor],
        [_actionLogsTable.bottomAnchor constraintEqualToAnchor:self.bottomAnchor],
        _tableHeightConstraint,
    ]];
    
    [self updateToggleButtonIcon];
}

#pragma mark - Public Methods

- (BOOL)isRunning {
    return self.taskProgress.isRunning;
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
    [self scrollToLatestAction];
}

- (void)handleActionExecuting:(NSDictionary *)data {
    [_taskProgress handleActionExecuting:data];
    [_actionLogsTable reloadData];
}

- (void)handleActionResult:(NSDictionary *)data {
    [_taskProgress handleActionResult:data];
    [_actionLogsTable reloadData];
}

- (void)handleTaskComplete:(NSDictionary *)data {
    [_taskProgress handleTaskComplete:data];
    [self updateUI];
    [_loadingIndicator stopAnimating];
    _stopButton.hidden = YES;
}

- (void)handleTaskStopped:(NSDictionary *)data {
    [_taskProgress handleTaskStopped:data];
    [self updateUI];
    [_loadingIndicator stopAnimating];
    _stopButton.hidden = YES;
}

- (void)handleLLMRequestStart:(NSDictionary *)data {
    [_taskProgress handleLLMRequestStart:data];
    _llmStatusLabel.hidden = NO;
}

- (void)handleLLMRequestEnd:(NSDictionary *)data {
    [_taskProgress handleLLMRequestEnd:data];
    _llmStatusLabel.hidden = YES;
}

- (void)reset {
    _taskProgress = nil;
    [_actionLogsTable reloadData];
    [_loadingIndicator stopAnimating];
    _progressBar.progress = 0;
    _statusLabel.text = @"";
    _titleLabel.text = @"🤖 任务执行中";
    _llmStatusLabel.hidden = YES;
    _stopButton.hidden = NO;
    [self updateTableHeight];
}

- (CGFloat)requiredHeight {
    CGFloat baseHeight = kHeaderHeight + kProgressBarHeight;
    if (_isExpanded && _taskProgress.actionLogs.count > 0) {
        CGFloat tableHeight = MIN(_taskProgress.actionLogs.count * kActionLogRowHeight, kMaxExpandedHeight - baseHeight);
        return baseHeight + tableHeight + 8;
    }
    return baseHeight;
}

#pragma mark - Private Methods

- (void)updateUI {
    if (!_taskProgress) return;
    
    // Update title
    if (_taskProgress.isCompleted) {
        if (_taskProgress.finalSuccess) {
            _titleLabel.text = @"✅ 任务完成";
        } else {
            _titleLabel.text = @"⚠️ 任务停止";
        }
    } else if (_taskProgress.isRunning) {
        _titleLabel.text = @"🤖 任务执行中";
        [_loadingIndicator startAnimating];
    }
    
    // Update status
    _statusLabel.text = [NSString stringWithFormat:@"步骤 %ld/%ld",
                         (long)_taskProgress.currentIteration,
                         (long)_taskProgress.maxIterations];
    
    // Update progress bar
    _progressBar.progress = [_taskProgress progressPercentage];
    
    // Update stop button visibility
    _stopButton.hidden = !_taskProgress.isRunning;
    
    // Update table
    [_actionLogsTable reloadData];
    [self updateTableHeight];
}

- (void)updateTableHeight {
    if (_isExpanded && _taskProgress.actionLogs.count > 0) {
        CGFloat height = MIN(_taskProgress.actionLogs.count * kActionLogRowHeight, kMaxExpandedHeight - kHeaderHeight - kProgressBarHeight);
        _tableHeightConstraint.constant = height;
        _actionLogsTable.hidden = NO;
    } else {
        _tableHeightConstraint.constant = 0;
        _actionLogsTable.hidden = YES;
    }
    [self setNeedsLayout];
}

- (void)updateToggleButtonIcon {
    NSString *iconName = _isExpanded ? @"chevron.up" : @"chevron.down";
    [_toggleButton setImage:[UIImage systemImageNamed:iconName] forState:UIControlStateNormal];
}

- (void)scrollToLatestAction {
    if (_taskProgress.actionLogs.count > 0 && _isExpanded) {
        NSIndexPath *lastRow = [NSIndexPath indexPathForRow:_taskProgress.actionLogs.count - 1 inSection:0];
        [_actionLogsTable scrollToRowAtIndexPath:lastRow atScrollPosition:UITableViewScrollPositionBottom animated:YES];
    }
}

#pragma mark - Actions

- (void)toggleTapped:(UIButton *)sender {
    _isExpanded = !_isExpanded;
    [self updateToggleButtonIcon];
    [self updateTableHeight];
    
    if ([_delegate respondsToSelector:@selector(taskProgressViewDidToggle:)]) {
        [_delegate taskProgressViewDidToggle:self];
    }
}

- (void)stopTapped:(UIButton *)sender {
    if ([_delegate respondsToSelector:@selector(taskProgressViewDidRequestStop:)]) {
        [_delegate taskProgressViewDidRequestStop:self];
    }
}

#pragma mark - UITableViewDataSource

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    return _taskProgress.actionLogs.count;
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    ActionLogCell *cell = [tableView dequeueReusableCellWithIdentifier:@"ActionLogCell" forIndexPath:indexPath];
    ActionLogEntry *entry = _taskProgress.actionLogs[indexPath.row];
    [cell configureWithEntry:entry];
    return cell;
}

#pragma mark - UITableViewDelegate

- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    ActionLogEntry *entry = _taskProgress.actionLogs[indexPath.row];
    if ([_delegate respondsToSelector:@selector(taskProgressView:didSelectActionLog:)]) {
        [_delegate taskProgressView:self didSelectActionLog:entry];
    }
}

@end
