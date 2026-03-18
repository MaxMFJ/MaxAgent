#import "GroupChatViewController.h"
#import "GroupChat.h"
#import "TechTheme.h"

static NSString *const kSystemCellId = @"SystemCell";
static NSString *const kAgentCellId  = @"AgentCell";

// MARK: - GroupChatViewController

@interface GroupChatViewController ()
@property (nonatomic, strong) UITableView *tableView;
@property (nonatomic, strong) UIView *taskPanelView;
@property (nonatomic, strong) UILabel *taskStatLabel;
@property (nonatomic, strong) UIProgressView *progressBar;
@property (nonatomic, strong) UIView *readOnlyBar;
@end

@implementation GroupChatViewController

// MARK: - Lifecycle

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = TechTheme.backgroundPrimary;
    [self setupNavigationBar];
    [self setupTaskPanel];
    [self setupTableView];
    [self setupReadOnlyBar];
    [self refreshTaskPanel];
}

// MARK: - Navigation Bar

- (void)setupNavigationBar {
    self.title = self.groupChat.title ?: @"协作群聊";
    
    if (@available(iOS 13.0, *)) {
        UINavigationBarAppearance *appearance = [[UINavigationBarAppearance alloc] init];
        [appearance configureWithOpaqueBackground];
        appearance.backgroundColor = [TechTheme.backgroundSecondary colorWithAlphaComponent:0.85];
        appearance.titleTextAttributes = @{
            NSForegroundColorAttributeName: TechTheme.neonCyan,
            NSFontAttributeName: [TechTheme fontDisplaySize:15 weight:UIFontWeightSemibold]
        };
        self.navigationItem.standardAppearance = appearance;
        self.navigationItem.scrollEdgeAppearance = appearance;
    }
    
    UIBarButtonItem *back = [[UIBarButtonItem alloc] initWithTitle:@"返回对话"
                                                             style:UIBarButtonItemStylePlain
                                                            target:self
                                                            action:@selector(didTapBack)];
    self.navigationItem.leftBarButtonItem = back;
}

- (void)didTapBack {
    if ([self.delegate respondsToSelector:@selector(groupChatViewControllerDidRequestBack:)]) {
        [self.delegate groupChatViewControllerDidRequestBack:self];
    } else {
        [self.navigationController popViewControllerAnimated:YES];
    }
}

// MARK: - Task Panel

- (void)setupTaskPanel {
    _taskPanelView = [[UIView alloc] init];
    _taskPanelView.backgroundColor = [TechTheme.backgroundSecondary colorWithAlphaComponent:0.7];
    _taskPanelView.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:_taskPanelView];

    _progressBar = [[UIProgressView alloc] initWithProgressViewStyle:UIProgressViewStyleDefault];
    _progressBar.translatesAutoresizingMaskIntoConstraints = NO;
    _progressBar.trackTintColor = [TechTheme.backgroundCard colorWithAlphaComponent:0.5];
    _progressBar.progressTintColor = TechTheme.neonCyan;
    [_taskPanelView addSubview:_progressBar];

    _taskStatLabel = [[UILabel alloc] init];
    _taskStatLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _taskStatLabel.font = [TechTheme fontMonoSize:10 weight:UIFontWeightMedium];
    _taskStatLabel.textColor = TechTheme.textSecondary;
    _taskStatLabel.numberOfLines = 1;
    [_taskPanelView addSubview:_taskStatLabel];

    [NSLayoutConstraint activateConstraints:@[
        [_taskPanelView.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor],
        [_taskPanelView.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [_taskPanelView.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [_taskPanelView.heightAnchor constraintEqualToConstant:44],

        [_progressBar.topAnchor constraintEqualToAnchor:_taskPanelView.topAnchor constant:8],
        [_progressBar.leadingAnchor constraintEqualToAnchor:_taskPanelView.leadingAnchor constant:12],
        [_progressBar.trailingAnchor constraintEqualToAnchor:_taskPanelView.trailingAnchor constant:-12],

        [_taskStatLabel.topAnchor constraintEqualToAnchor:_progressBar.bottomAnchor constant:4],
        [_taskStatLabel.leadingAnchor constraintEqualToAnchor:_taskPanelView.leadingAnchor constant:12],
        [_taskStatLabel.trailingAnchor constraintEqualToAnchor:_taskPanelView.trailingAnchor constant:-12],
    ]];
}

- (void)refreshTaskPanel {
    GroupTaskSummary *ts = self.groupChat.taskSummary;
    NSInteger total = ts.total;
    NSInteger done = ts.completed + ts.failed;
    float progress = total > 0 ? (float)done / total : 0;
    _progressBar.progress = progress;

    NSString *stat = [NSString stringWithFormat:@"总计 %ld  ✅ %ld  🔄 %ld  ⏳ %ld",
                      (long)ts.total, (long)ts.completed, (long)ts.running, (long)ts.pending];
    if (ts.failed > 0) {
        stat = [stat stringByAppendingFormat:@"  ❌ %ld", (long)ts.failed];
    }
    _taskStatLabel.text = stat;
}

// MARK: - Table View

- (void)setupTableView {
    _tableView = [[UITableView alloc] initWithFrame:CGRectZero style:UITableViewStylePlain];
    _tableView.translatesAutoresizingMaskIntoConstraints = NO;
    _tableView.dataSource = self;
    _tableView.delegate = self;
    _tableView.backgroundColor = [UIColor clearColor];
    _tableView.separatorStyle = UITableViewCellSeparatorStyleNone;
    _tableView.allowsSelection = NO;
    [_tableView registerClass:[UITableViewCell class] forCellReuseIdentifier:kSystemCellId];
    [_tableView registerClass:[UITableViewCell class] forCellReuseIdentifier:kAgentCellId];
    [self.view addSubview:_tableView];

    [NSLayoutConstraint activateConstraints:@[
        [_tableView.topAnchor constraintEqualToAnchor:_taskPanelView.bottomAnchor],
        [_tableView.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [_tableView.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
    ]];
}

// MARK: - Read-Only Bar

- (void)setupReadOnlyBar {
    _readOnlyBar = [[UIView alloc] init];
    _readOnlyBar.translatesAutoresizingMaskIntoConstraints = NO;
    _readOnlyBar.backgroundColor = [TechTheme.backgroundSecondary colorWithAlphaComponent:0.85];
    [self.view addSubview:_readOnlyBar];

    UILabel *label = [[UILabel alloc] init];
    label.translatesAutoresizingMaskIntoConstraints = NO;
    label.text = @"👀 只读模式 — 群聊由 Agent 自动驱动";
    label.font = [TechTheme fontMonoSize:11 weight:UIFontWeightMedium];
    label.textColor = TechTheme.textSecondary;
    label.textAlignment = NSTextAlignmentCenter;
    [_readOnlyBar addSubview:label];

    [NSLayoutConstraint activateConstraints:@[
        [_readOnlyBar.topAnchor constraintEqualToAnchor:_tableView.bottomAnchor],
        [_readOnlyBar.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [_readOnlyBar.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [_readOnlyBar.bottomAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.bottomAnchor],
        [_readOnlyBar.heightAnchor constraintEqualToConstant:36],

        [label.centerXAnchor constraintEqualToAnchor:_readOnlyBar.centerXAnchor],
        [label.centerYAnchor constraintEqualToAnchor:_readOnlyBar.centerYAnchor],
    ]];
}

// MARK: - UITableViewDataSource

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    return self.groupChat.messages.count;
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    GroupMessage *msg = self.groupChat.messages[indexPath.row];

    if (msg.senderRole == ParticipantRoleSystem) {
        UITableViewCell *cell = [tableView dequeueReusableCellWithIdentifier:kSystemCellId forIndexPath:indexPath];
        cell.backgroundColor = [UIColor clearColor];
        cell.selectionStyle = UITableViewCellSelectionStyleNone;
        cell.textLabel.text = msg.content;
        cell.textLabel.font = [TechTheme fontMonoSize:10 weight:UIFontWeightMedium];
        cell.textLabel.textColor = TechTheme.textSecondary;
        cell.textLabel.textAlignment = NSTextAlignmentCenter;
        cell.textLabel.numberOfLines = 0;
        return cell;
    }

    UITableViewCell *cell = [tableView dequeueReusableCellWithIdentifier:kAgentCellId forIndexPath:indexPath];
    cell.backgroundColor = [UIColor clearColor];
    cell.selectionStyle = UITableViewCellSelectionStyleNone;

    // Remove old subviews to reconfigure  
    for (UIView *sv in cell.contentView.subviews) { [sv removeFromSuperview]; }

    UIColor *accentColor;
    if (msg.senderRole == ParticipantRoleMain) {
        accentColor = TechTheme.neonCyan;
    } else if (msg.senderRole == ParticipantRoleMonitor) {
        accentColor = TechTheme.neonPurple;
    } else {
        accentColor = TechTheme.neonOrange;
    }

    // Emoji avatar
    UILabel *emojiLabel = [[UILabel alloc] init];
    emojiLabel.translatesAutoresizingMaskIntoConstraints = NO;
    emojiLabel.text = [self emojiForSender:msg.senderId];
    emojiLabel.font = [UIFont systemFontOfSize:16];
    emojiLabel.textAlignment = NSTextAlignmentCenter;
    emojiLabel.backgroundColor = [accentColor colorWithAlphaComponent:0.1];
    emojiLabel.layer.cornerRadius = 14;
    emojiLabel.clipsToBounds = YES;
    [cell.contentView addSubview:emojiLabel];

    // Name + badge
    UILabel *nameLabel = [[UILabel alloc] init];
    nameLabel.translatesAutoresizingMaskIntoConstraints = NO;
    nameLabel.text = msg.senderName;
    nameLabel.font = [TechTheme fontBodySize:11 weight:UIFontWeightSemibold];
    nameLabel.textColor = accentColor;
    [cell.contentView addSubview:nameLabel];

    NSString *badge = [self badgeForType:msg.msgType];
    UILabel *badgeLabel = nil;
    if (badge) {
        badgeLabel = [[UILabel alloc] init];
        badgeLabel.translatesAutoresizingMaskIntoConstraints = NO;
        badgeLabel.text = badge;
        badgeLabel.font = [TechTheme fontMonoSize:8 weight:UIFontWeightSemibold];
        badgeLabel.textColor = [UIColor whiteColor];
        badgeLabel.backgroundColor = [accentColor colorWithAlphaComponent:0.6];
        badgeLabel.layer.cornerRadius = 3;
        badgeLabel.clipsToBounds = YES;
        badgeLabel.textAlignment = NSTextAlignmentCenter;
        [cell.contentView addSubview:badgeLabel];
    }

    // Content
    UILabel *contentLabel = [[UILabel alloc] init];
    contentLabel.translatesAutoresizingMaskIntoConstraints = NO;
    contentLabel.text = msg.content;
    contentLabel.font = [TechTheme fontBodySize:12 weight:UIFontWeightRegular];
    contentLabel.textColor = TechTheme.textPrimary;
    contentLabel.numberOfLines = 0;
    [cell.contentView addSubview:contentLabel];

    // Constraints
    [NSLayoutConstraint activateConstraints:@[
        [emojiLabel.leadingAnchor constraintEqualToAnchor:cell.contentView.leadingAnchor constant:12],
        [emojiLabel.topAnchor constraintEqualToAnchor:cell.contentView.topAnchor constant:8],
        [emojiLabel.widthAnchor constraintEqualToConstant:28],
        [emojiLabel.heightAnchor constraintEqualToConstant:28],

        [nameLabel.leadingAnchor constraintEqualToAnchor:emojiLabel.trailingAnchor constant:8],
        [nameLabel.topAnchor constraintEqualToAnchor:cell.contentView.topAnchor constant:8],

        [contentLabel.leadingAnchor constraintEqualToAnchor:emojiLabel.trailingAnchor constant:8],
        [contentLabel.topAnchor constraintEqualToAnchor:nameLabel.bottomAnchor constant:2],
        [contentLabel.trailingAnchor constraintEqualToAnchor:cell.contentView.trailingAnchor constant:-12],
        [contentLabel.bottomAnchor constraintEqualToAnchor:cell.contentView.bottomAnchor constant:-8],
    ]];

    if (badgeLabel) {
        [NSLayoutConstraint activateConstraints:@[
            [badgeLabel.leadingAnchor constraintEqualToAnchor:nameLabel.trailingAnchor constant:4],
            [badgeLabel.centerYAnchor constraintEqualToAnchor:nameLabel.centerYAnchor],
            [badgeLabel.widthAnchor constraintGreaterThanOrEqualToConstant:24],
            [badgeLabel.heightAnchor constraintEqualToConstant:14],
        ]];
    }

    // Background tint
    UIView *bg = [[UIView alloc] init];
    bg.translatesAutoresizingMaskIntoConstraints = NO;
    bg.backgroundColor = [accentColor colorWithAlphaComponent:0.04];
    bg.layer.cornerRadius = 8;
    [cell.contentView insertSubview:bg atIndex:0];
    [NSLayoutConstraint activateConstraints:@[
        [bg.topAnchor constraintEqualToAnchor:cell.contentView.topAnchor constant:2],
        [bg.leadingAnchor constraintEqualToAnchor:cell.contentView.leadingAnchor constant:8],
        [bg.trailingAnchor constraintEqualToAnchor:cell.contentView.trailingAnchor constant:-8],
        [bg.bottomAnchor constraintEqualToAnchor:cell.contentView.bottomAnchor constant:-2],
    ]];

    return cell;
}

- (CGFloat)tableView:(UITableView *)tableView heightForRowAtIndexPath:(NSIndexPath *)indexPath {
    return UITableViewAutomaticDimension;
}

- (CGFloat)tableView:(UITableView *)tableView estimatedHeightForRowAtIndexPath:(NSIndexPath *)indexPath {
    GroupMessage *msg = self.groupChat.messages[indexPath.row];
    return msg.senderRole == ParticipantRoleSystem ? 30 : 60;
}

// MARK: - Public Methods

- (void)appendMessage:(GroupMessage *)message {
    [self.groupChat addMessage:message];
    NSIndexPath *ip = [NSIndexPath indexPathForRow:self.groupChat.messages.count - 1 inSection:0];
    [self.tableView insertRowsAtIndexPaths:@[ip] withRowAnimation:UITableViewRowAnimationFade];
    dispatch_async(dispatch_get_main_queue(), ^{
        [self.tableView scrollToRowAtIndexPath:ip atScrollPosition:UITableViewScrollPositionBottom animated:YES];
    });
}

- (void)updateStatus:(GroupChatStatusType)status summary:(GroupTaskSummary *)summary {
    [self.groupChat updateStatus:status summary:summary];
    [self refreshTaskPanel];
}

// MARK: - Helpers

- (NSString *)emojiForSender:(NSString *)senderId {
    for (GroupParticipant *p in self.groupChat.participants) {
        if ([p.participantId isEqualToString:senderId]) {
            return p.emoji;
        }
    }
    return @"🤖";
}

- (nullable NSString *)badgeForType:(GroupMessageTypeValue)type {
    switch (type) {
        case GroupMessageTypeTaskAssign: return @" 分配 ";
        case GroupMessageTypeTaskComplete: return @" 完成 ";
        case GroupMessageTypeTaskFailed: return @" 失败 ";
        case GroupMessageTypeTaskProgress: return @" 进度 ";
        case GroupMessageTypePlan: return @" 计划 ";
        case GroupMessageTypeConclusion: return @" 总结 ";
        case GroupMessageTypeMonitorReport: return @" 报告 ";
        case GroupMessageTypeStatusUpdate: return @" 状态 ";
        case GroupMessageTypeText: return nil;
    }
}

@end
