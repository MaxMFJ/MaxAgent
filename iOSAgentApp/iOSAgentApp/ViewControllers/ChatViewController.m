#import "ChatViewController.h"
#import "SettingsViewController.h"
#import "ConversationListViewController.h"
#import "DuckTargetSelectorViewController.h"
#import "Duck.h"
#import "WebSocketService.h"
#import "ServerConfig.h"
#import "Message.h"
#import "MessageCell.h"
#import "InputView.h"
#import "ImageZoomViewController.h"
#import "ConversationManager.h"
#import "TTSService.h"
#import "VoiceInputService.h"
#import "TechTheme.h"
#import "VoiceRainbowView.h"
#import "AgentLiveView.h"
#import "ActionLogEntry.h"

@interface ChatViewController () <UITableViewDataSource, UITableViewDelegate, WebSocketServiceDelegate, InputViewDelegate, MessageCellDelegate, ConversationListDelegate, AgentLiveViewDelegate, DuckTargetSelectorDelegate>

@property (nonatomic, strong) UITableView *tableView;
@property (nonatomic, strong) InputView *inputView;
@property (nonatomic, strong) UIView *statusBar;
@property (nonatomic, strong) UILabel *statusLabel;
@property (nonatomic, strong) UIActivityIndicatorView *statusIndicator;

@property (nonatomic, strong, nullable) Message *currentAssistantMessage;
@property (nonatomic, strong) NSLayoutConstraint *inputViewBottomConstraint;
@property (nonatomic, strong, nullable) NSTimer *autonomousTimeoutTimer;
@property (nonatomic, strong) VoiceRainbowView *voiceRainbow;

// 用于消息去重（避免重连时重复显示已有消息）
@property (nonatomic, strong) NSMutableSet<NSString *> *displayedMessageIds;

// Agent Live 面板（赛博朋克风格，内嵌在 Chat 页面）
@property (nonatomic, strong) AgentLiveView *agentLiveView;
@property (nonatomic, strong) NSLayoutConstraint *agentLiveHeightConstraint;
@property (nonatomic, strong) NSLayoutConstraint *tableViewBottomConstraint;

// 网格背景图层（用于动态更新颜色）
@property (nonatomic, strong) CAShapeLayer *gridDim;
@property (nonatomic, strong) CAShapeLayer *gridBright;
@property (nonatomic, strong) CAShapeLayer *nodesDim;
@property (nonatomic, strong) CAShapeLayer *nodesBright;

// 流式输出节流：避免每个 chunk 都触发 cell reload，减少主线程阻塞
@property (nonatomic, strong, nullable) NSDate *lastStreamingUIUpdateTime;
@property (nonatomic, assign) BOOL hasPendingStreamingUpdate;
@property (nonatomic, assign) NSInteger streamingHeightUpdateCounter;

@end

@implementation ChatViewController
static const NSTimeInterval kStreamingThrottleInterval = 0.18; // 180ms，降低 CPU 占用
static const NSInteger kStreamingHeightUpdateDivisor = 6;      // 每 6 次节流更新才刷新行高（约 1s）

static NSString * const kUserDefaultsTTSEnabled = @"ttsEnabled";

- (void)viewDidLoad {
    [super viewDidLoad];

    // 初始化消息去重 set
    self.displayedMessageIds = [NSMutableSet set];

    // 深空黑主背景
    self.view.backgroundColor = TechTheme.backgroundPrimary;

    // 添加网格背景动画
    [self setupGridBackground];
    
    [self setupNavigationBar];
    [self setupUI];
    [self setupKeyboardObservers];
    [self setupWebSocket];
    [self setupVoiceInput];
    [self updateTitle];
    
    // 检查是否有未完成的 streaming 消息需要恢复
    [self checkPendingStreamingMessage];
}

- (void)checkPendingStreamingMessage {
    ConversationManager *manager = [ConversationManager sharedManager];
    Conversation *currentConv = manager.currentConversation;
    if (!currentConv || currentConv.messages.count == 0) {
        return;
    }
    
    Message *lastMessage = currentConv.messages.lastObject;
    if (lastMessage.role == MessageRoleAssistant && lastMessage.status == MessageStatusStreaming) {
        NSLog(@"[Chat] Found pending streaming message, setting as currentAssistantMessage");
        self.currentAssistantMessage = lastMessage;
        // 显示加载状态
        self.inputView.loading = YES;
        // WebSocket 连接成功后会自动触发 resumeChat
    }
}

- (void)setupVoiceInput {
    __weak typeof(self) wself = self;
    [VoiceInputService sharedService].onTextUpdate = ^(NSString *interim, NSString *final) {
        dispatch_async(dispatch_get_main_queue(), ^{
            NSString *show = interim.length > 0 ? interim : (final ?: @"");
            [wself.inputView setText:show];
        });
    };
    [VoiceInputService sharedService].onShouldSubmit = ^(NSString *text) {
        dispatch_async(dispatch_get_main_queue(), ^{
            wself.inputView.voiceInputActive = NO;
            [wself.voiceRainbow stopFlowing];
            [wself.voiceRainbow hideAnimated];
            [wself.inputView setText:@""];
            if (text.length > 0) {
                [wself inputView:wself.inputView didSendMessage:text];
            }
        });
    };
}

- (void)updateTitle {
    ConversationManager *manager = [ConversationManager sharedManager];
    Conversation *conv = manager.currentConversation;
    if (conv) {
        if (conv.targetType == ConversationTargetTypeDuck && conv.targetDuckId.length > 0) {
            self.title = [NSString stringWithFormat:@"🦆 %@", conv.title.length > 0 ? conv.title : @"Duck 对话"];
        } else {
            self.title = conv.title;
        }
    } else {
        self.title = NSLocalizedString(@"app_title", nil);
    }
}

- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];

    // 将彩虹视图添加到 window 最上层（不被导航栏截断）
    if (!_voiceRainbow.superview && self.view.window) {
        _voiceRainbow.frame = self.view.window.bounds;
        _voiceRainbow.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
        [self.view.window addSubview:_voiceRainbow];
    }
    
    if ([ServerConfig sharedConfig].serverURL.length == 0) {
        [self showSettings];
    } else {
        [[WebSocketService sharedService] connect];
    }
}

#pragma mark - Grid Background

- (void)setupGridBackground {
    CGFloat w = UIScreen.mainScreen.bounds.size.width;
    CGFloat h = UIScreen.mainScreen.bounds.size.height;
    CGFloat step = 44;

    // ---- 构建网格路径 ----
    UIBezierPath *linePath = [UIBezierPath bezierPath];
    for (CGFloat x = 0; x < w; x += step) {
        [linePath moveToPoint:CGPointMake(x, 0)];
        [linePath addLineToPoint:CGPointMake(x, h)];
    }
    for (CGFloat y = 0; y < h; y += step) {
        [linePath moveToPoint:CGPointMake(0, y)];
        [linePath addLineToPoint:CGPointMake(w, y)];
    }

    // ---- 构建节点路径 ----
    UIBezierPath *nodePath = [UIBezierPath bezierPath];
    UIBezierPath *nodeBrightPath = [UIBezierPath bezierPath];
    for (CGFloat x = 0; x < w; x += step) {
        for (CGFloat y = 0; y < h; y += step) {
            [nodePath appendPath:[UIBezierPath bezierPathWithOvalInRect:CGRectMake(x - 1.5, y - 1.5, 3, 3)]];
            [nodeBrightPath appendPath:[UIBezierPath bezierPathWithOvalInRect:CGRectMake(x - 2.5, y - 2.5, 5, 5)]];
        }
    }

    // ---- 1. 暗层：始终可见的底色网格 ----
    _gridDim = [CAShapeLayer layer];
    _gridDim.path = linePath.CGPath;
    _gridDim.strokeColor = [TechTheme.neonCyan colorWithAlphaComponent:0.06].CGColor;
    _gridDim.lineWidth = 0.5;
    _gridDim.fillColor = nil;
    _gridDim.frame = CGRectMake(0, 0, w, h);
    [self.view.layer insertSublayer:_gridDim atIndex:0];

    _nodesDim = [CAShapeLayer layer];
    _nodesDim.path = nodePath.CGPath;
    _nodesDim.fillColor = [TechTheme.neonCyan colorWithAlphaComponent:0.08].CGColor;
    _nodesDim.strokeColor = nil;
    _nodesDim.frame = CGRectMake(0, 0, w, h);
    [self.view.layer insertSublayer:_nodesDim atIndex:1];

    // ---- 2. 亮层：通过波浪遮罩让网格明暗波动 ----
    _gridBright = [CAShapeLayer layer];
    _gridBright.path = linePath.CGPath;
    _gridBright.strokeColor = [TechTheme.neonCyan colorWithAlphaComponent:0.30].CGColor;
    _gridBright.lineWidth = 1.0;
    _gridBright.fillColor = nil;
    _gridBright.frame = CGRectMake(0, 0, w, h);
    [self.view.layer insertSublayer:_gridBright atIndex:2];

    _nodesBright = [CAShapeLayer layer];
    _nodesBright.path = nodeBrightPath.CGPath;
    _nodesBright.fillColor = [TechTheme.neonCyan colorWithAlphaComponent:0.40].CGColor;
    _nodesBright.strokeColor = nil;
    _nodesBright.frame = CGRectMake(0, 0, w, h);
    [self.view.layer insertSublayer:_nodesBright atIndex:3];

    // ---- 3. 遮罩：亮带在中间，首尾透明确保无缝循环 ----
    CGFloat maskH = h * 5;
    CAGradientLayer *waveMask = [CAGradientLayer layer];
    waveMask.frame = CGRectMake(0, 0, w, maskH);
    waveMask.startPoint = CGPointMake(0.5, 0);
    waveMask.endPoint   = CGPointMake(0.5, 1);
    // 首尾均为透明，亮带在 0.25~0.50 区间，确保循环首尾无缝
    waveMask.colors = @[
        (id)[UIColor clearColor].CGColor,       // 0.00 头部透明
        (id)[UIColor clearColor].CGColor,       // 0.20
        (id)[UIColor whiteColor].CGColor,       // 0.28 第一道亮带
        (id)[UIColor whiteColor].CGColor,       // 0.32
        (id)[UIColor clearColor].CGColor,       // 0.38
        (id)[[UIColor whiteColor] colorWithAlphaComponent:0.5].CGColor, // 0.44 第二道弱亮带
        (id)[UIColor whiteColor].CGColor,       // 0.48
        (id)[[UIColor whiteColor] colorWithAlphaComponent:0.5].CGColor, // 0.52
        (id)[UIColor clearColor].CGColor,       // 0.58
        (id)[UIColor clearColor].CGColor,       // 0.80 尾部透明
        (id)[UIColor clearColor].CGColor        // 1.00
    ];
    waveMask.locations = @[@0.0, @0.20, @0.28, @0.32, @0.38,
                           @0.44, @0.48, @0.52, @0.58, @0.80, @1.0];
    _gridBright.mask = waveMask;

    // 滚动范围：从亮带在屏幕上方 → 完整扫过 → 亮带在屏幕下方
    CABasicAnimation *waveScroll = [CABasicAnimation animationWithKeyPath:@"position.y"];
    waveScroll.fromValue = @(-maskH * 0.3);
    waveScroll.toValue   = @(h + maskH * 0.3);
    waveScroll.duration  = 16.0;
    waveScroll.repeatCount = HUGE_VALF;
    waveScroll.timingFunction = [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionLinear];
    [waveMask addAnimation:waveScroll forKey:@"waveScroll"];

    // ---- 4. 节点遮罩（同步偏移）----
    CAGradientLayer *nodeMask = [CAGradientLayer layer];
    nodeMask.frame = CGRectMake(0, 0, w, maskH);
    nodeMask.startPoint = CGPointMake(0.5, 0);
    nodeMask.endPoint   = CGPointMake(0.5, 1);
    nodeMask.colors = waveMask.colors;
    nodeMask.locations = waveMask.locations;
    _nodesBright.mask = nodeMask;

    CABasicAnimation *nodeScroll = [CABasicAnimation animationWithKeyPath:@"position.y"];
    nodeScroll.fromValue = @(-maskH * 0.25);
    nodeScroll.toValue   = @(h + maskH * 0.35);
    nodeScroll.duration  = 16.0;
    nodeScroll.repeatCount = HUGE_VALF;
    nodeScroll.timingFunction = [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionLinear];
    [nodeMask addAnimation:nodeScroll forKey:@"nodeScroll"];
}

#pragma mark - Setup

- (void)setupNavigationBar {
    // 导航栏半透明深色 + 霓虹青色按钮
    if (@available(iOS 13.0, *)) {
        UINavigationBarAppearance *appearance = [[UINavigationBarAppearance alloc] init];
        [appearance configureWithTransparentBackground];
        appearance.backgroundColor = [TechTheme.backgroundSecondary colorWithAlphaComponent:0.85];
        appearance.titleTextAttributes = @{
            NSForegroundColorAttributeName: TechTheme.neonCyan,
            NSFontAttributeName: [TechTheme fontDisplaySize:16 weight:UIFontWeightSemibold]
        };
        self.navigationController.navigationBar.standardAppearance = appearance;
        self.navigationController.navigationBar.scrollEdgeAppearance = appearance;
        self.navigationController.navigationBar.tintColor = TechTheme.neonCyan;
    }

    UIBarButtonItem *newChatButton = [[UIBarButtonItem alloc] initWithImage:[UIImage systemImageNamed:@"square.and.pencil"] style:UIBarButtonItemStylePlain target:self action:@selector(createNewConversation)];
    UIBarButtonItem *duckTargetButton = [[UIBarButtonItem alloc] initWithImage:[UIImage systemImageNamed:@"bird"] style:UIBarButtonItemStylePlain target:self action:@selector(showDuckTargetSelector)];
    duckTargetButton.accessibilityLabel = @"选择对话对象";
    UIBarButtonItem *settingsButton = [[UIBarButtonItem alloc] initWithImage:[UIImage systemImageNamed:@"gear"] style:UIBarButtonItemStylePlain target:self action:@selector(showSettings)];
    self.navigationItem.rightBarButtonItems = @[settingsButton, duckTargetButton, newChatButton];

    UIBarButtonItem *conversationsButton = [[UIBarButtonItem alloc] initWithImage:[UIImage systemImageNamed:@"text.bubble"] style:UIBarButtonItemStylePlain target:self action:@selector(showConversationList)];
    UIBarButtonItem *clearButton = [[UIBarButtonItem alloc] initWithImage:[UIImage systemImageNamed:@"trash"] style:UIBarButtonItemStylePlain target:self action:@selector(clearChat)];
    self.navigationItem.leftBarButtonItems = @[conversationsButton, clearButton];
}

- (void)setupUI {
    // 状态栏：玻璃拟态深色 + 霓虹指示灯
    _statusBar = [[UIView alloc] init];
    _statusBar.translatesAutoresizingMaskIntoConstraints = NO;
    _statusBar.backgroundColor = [TechTheme.backgroundSecondary colorWithAlphaComponent:0.92];
    [self.view addSubview:_statusBar];

    // 底部发光线
    UIView *statusGlow = [[UIView alloc] init];
    statusGlow.translatesAutoresizingMaskIntoConstraints = NO;
    statusGlow.backgroundColor = [TechTheme.neonCyan colorWithAlphaComponent:0.4];
    [_statusBar addSubview:statusGlow];
    [NSLayoutConstraint activateConstraints:@[
        [statusGlow.bottomAnchor constraintEqualToAnchor:_statusBar.bottomAnchor],
        [statusGlow.leadingAnchor constraintEqualToAnchor:_statusBar.leadingAnchor],
        [statusGlow.trailingAnchor constraintEqualToAnchor:_statusBar.trailingAnchor],
        [statusGlow.heightAnchor constraintEqualToConstant:1]
    ]];

    // 霓虹状态指示灯（替代 ActivityIndicator）
    _statusIndicator = [[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleMedium];
    _statusIndicator.translatesAutoresizingMaskIntoConstraints = NO;
    _statusIndicator.color = TechTheme.neonRed;
    _statusIndicator.hidesWhenStopped = YES;
    [_statusBar addSubview:_statusIndicator];

    _statusLabel = [[UILabel alloc] init];
    _statusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _statusLabel.font = [TechTheme fontMonoSize:11 weight:UIFontWeightMedium];
    _statusLabel.textColor = TechTheme.textSecondary;
    _statusLabel.text = NSLocalizedString(@"status_disconnected", nil);
    [_statusBar addSubview:_statusLabel];

    // 右侧脉冲圆点（连接状态指示）
    UIView *connDot = [[UIView alloc] init];
    connDot.translatesAutoresizingMaskIntoConstraints = NO;
    connDot.layer.cornerRadius = 5;
    connDot.backgroundColor = TechTheme.neonRed;
    connDot.tag = 9001;
    [_statusBar addSubview:connDot];
    [NSLayoutConstraint activateConstraints:@[
        [connDot.trailingAnchor constraintEqualToAnchor:_statusBar.trailingAnchor constant:-14],
        [connDot.centerYAnchor constraintEqualToAnchor:_statusBar.centerYAnchor],
        [connDot.widthAnchor constraintEqualToConstant:10],
        [connDot.heightAnchor constraintEqualToConstant:10]
    ]];

    _tableView = [[UITableView alloc] initWithFrame:CGRectZero style:UITableViewStylePlain];
    _tableView.translatesAutoresizingMaskIntoConstraints = NO;
    _tableView.dataSource = self;
    _tableView.delegate = self;
    _tableView.separatorStyle = UITableViewCellSeparatorStyleNone;
    _tableView.backgroundColor = [UIColor clearColor];
    _tableView.keyboardDismissMode = UIScrollViewKeyboardDismissModeInteractive;
    // 按角色注册不同的复用标识，避免 assistant↔user 复用时触发昂贵的样式重配置
    [_tableView registerClass:[MessageCell class] forCellReuseIdentifier:@"UserCell"];
    [_tableView registerClass:[MessageCell class] forCellReuseIdentifier:@"AssistantCell"];
    [_tableView registerClass:[MessageCell class] forCellReuseIdentifier:@"ToolCallCell"];
    [_tableView registerClass:[MessageCell class] forCellReuseIdentifier:@"ToolResultCell"];

    UITapGestureRecognizer *dismissTap = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(dismissKeyboard)];
    dismissTap.cancelsTouchesInView = NO;
    [_tableView addGestureRecognizer:dismissTap];

    [self.view addSubview:_tableView];
    
    _inputView = [[InputView alloc] init];
    _inputView.translatesAutoresizingMaskIntoConstraints = NO;
    _inputView.delegate = self;
    [self.view addSubview:_inputView];
    
    // Agent Live 面板（在输入框上方，赛博朋克 2077 风格）
    _agentLiveView = [[AgentLiveView alloc] init];
    _agentLiveView.translatesAutoresizingMaskIntoConstraints = NO;
    _agentLiveView.delegate = self;
    _agentLiveView.hidden = YES;
    [self.view addSubview:_agentLiveView];
    
    _inputViewBottomConstraint = [_inputView.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor];
    _agentLiveHeightConstraint = [_agentLiveView.heightAnchor constraintEqualToConstant:0];
    _tableViewBottomConstraint = [_tableView.bottomAnchor constraintEqualToAnchor:_agentLiveView.topAnchor];
    
    [NSLayoutConstraint activateConstraints:@[
        [_statusBar.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor],
        [_statusBar.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [_statusBar.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [_statusBar.heightAnchor constraintEqualToConstant:28],
        
        [_statusIndicator.leadingAnchor constraintEqualToAnchor:_statusBar.leadingAnchor constant:12],
        [_statusIndicator.centerYAnchor constraintEqualToAnchor:_statusBar.centerYAnchor],
        
        [_statusLabel.leadingAnchor constraintEqualToAnchor:_statusIndicator.trailingAnchor constant:8],
        [_statusLabel.centerYAnchor constraintEqualToAnchor:_statusBar.centerYAnchor],
        
        [_tableView.topAnchor constraintEqualToAnchor:_statusBar.bottomAnchor],
        [_tableView.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [_tableView.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        _tableViewBottomConstraint,
        
        // Agent Live 面板
        [_agentLiveView.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor constant:8],
        [_agentLiveView.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor constant:-8],
        [_agentLiveView.bottomAnchor constraintEqualToAnchor:_inputView.topAnchor constant:-8],
        _agentLiveHeightConstraint,
        
        [_inputView.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [_inputView.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        _inputViewBottomConstraint
    ]];

    // 语音模式彩虹边缘叠加层（延迟到 viewDidAppear 添加到 window）
    _voiceRainbow = [[VoiceRainbowView alloc] init];
}

- (void)setupKeyboardObservers {
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(keyboardWillShow:) name:UIKeyboardWillShowNotification object:nil];
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(keyboardWillHide:) name:UIKeyboardWillHideNotification object:nil];
}

- (void)setupWebSocket {
    [WebSocketService sharedService].delegate = self;
}

#pragma mark - Actions

- (void)createNewConversation {
    ConversationManager *manager = [ConversationManager sharedManager];
    Conversation *newConversation = [manager createNewConversation];
    
    [self updateTitle];
    [self.tableView reloadData];
    [self scrollToBottom];
    
    [[WebSocketService sharedService] createNewSession:newConversation.conversationId];
}

- (void)showConversationList {
    ConversationListViewController *listVC = [[ConversationListViewController alloc] init];
    listVC.delegate = self;
    UINavigationController *nav = [[UINavigationController alloc] initWithRootViewController:listVC];
    [self presentViewController:nav animated:YES completion:nil];
}

- (void)switchToConversation:(Conversation *)conversation {
    [[TTSService sharedService] stop];
    ConversationManager *manager = [ConversationManager sharedManager];
    [manager selectConversation:conversation];
    
    self.currentAssistantMessage = nil;
    [self.tableView reloadData];
    [self scrollToBottom];
    
    [[WebSocketService sharedService] createNewSession:conversation.conversationId];
}

#pragma mark - ConversationListDelegate

- (void)didSelectConversation:(Conversation *)conversation {
    [self switchToConversation:conversation];
    [self updateTitle];
}

- (void)didDeleteConversation:(Conversation *)conversation {
    if ([conversation.conversationId isEqualToString:[ConversationManager sharedManager].currentConversation.conversationId]) {
        [self.tableView reloadData];
        [self updateTitle];
    }
}

- (void)showSettings {
    SettingsViewController *settingsVC = [[SettingsViewController alloc] init];
    UINavigationController *nav = [[UINavigationController alloc] initWithRootViewController:settingsVC];
    [self presentViewController:nav animated:YES completion:nil];
}

- (void)showDuckTargetSelector {
    DuckTargetSelectorViewController *vc = [[DuckTargetSelectorViewController alloc] initWithStyle:UITableViewStyleInsetGrouped];
    vc.delegate = self;
    UINavigationController *nav = [[UINavigationController alloc] initWithRootViewController:vc];
    [self presentViewController:nav animated:YES completion:nil];
}

#pragma mark - DuckTargetSelectorDelegate

- (void)duckTargetSelectorDidSelectMain {
    ConversationManager *manager = [ConversationManager sharedManager];
    Conversation *conv = [manager createNewConversation];
    [self switchToConversation:conv];
    [self updateTitle];
}

- (void)duckTargetSelectorDidSelectDuck:(Duck *)duck {
    ConversationManager *manager = [ConversationManager sharedManager];
    Conversation *conv = [manager createNewConversationWithDuckId:duck.duckId];
    conv.title = [NSString stringWithFormat:@"与 %@ 对话", duck.name];
    [self switchToConversation:conv];
    [self updateTitle];
}

- (void)clearChat {
    [[TTSService sharedService] stop];
    ConversationManager *manager = [ConversationManager sharedManager];
    Conversation *currentConv = manager.currentConversation;
    
    if (!currentConv || currentConv.messages.count == 0) {
        return;
    }
    
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:NSLocalizedString(@"clear_chat", nil) 
                                                                   message:NSLocalizedString(@"clear_chat_message", nil) 
                                                            preferredStyle:UIAlertControllerStyleAlert];
    
    [alert addAction:[UIAlertAction actionWithTitle:NSLocalizedString(@"cancel", nil) 
                                              style:UIAlertActionStyleCancel 
                                            handler:nil]];
    [alert addAction:[UIAlertAction actionWithTitle:NSLocalizedString(@"clear", nil) 
                                              style:UIAlertActionStyleDestructive 
                                            handler:^(UIAlertAction *action) {
        [currentConv.messages removeAllObjects];
        currentConv.updatedAt = [NSDate date];
        self.currentAssistantMessage = nil;
        [self.tableView reloadData];
        
        [[WebSocketService sharedService] clearSession:currentConv.conversationId];
        [manager saveConversations];
    }]];
    
    [self presentViewController:alert animated:YES completion:nil];
}

#pragma mark - Keyboard

- (void)dismissKeyboard {
    [self.view endEditing:YES];
}

- (void)keyboardWillShow:(NSNotification *)notification {
    CGRect keyboardFrame = [notification.userInfo[UIKeyboardFrameEndUserInfoKey] CGRectValue];
    NSTimeInterval duration = [notification.userInfo[UIKeyboardAnimationDurationUserInfoKey] doubleValue];
    
    self.inputViewBottomConstraint.constant = -keyboardFrame.size.height;
    
    [UIView animateWithDuration:duration animations:^{
        [self.view layoutIfNeeded];
    }];
    
    [self scrollToBottom];
}

- (void)keyboardWillHide:(NSNotification *)notification {
    NSTimeInterval duration = [notification.userInfo[UIKeyboardAnimationDurationUserInfoKey] doubleValue];
    
    self.inputViewBottomConstraint.constant = 0;
    
    [UIView animateWithDuration:duration animations:^{
        [self.view layoutIfNeeded];
    }];
}

#pragma mark - Helpers

- (NSMutableArray<Message *> *)currentMessages {
    return [ConversationManager sharedManager].currentConversation.messages ?: [NSMutableArray array];
}

- (void)scrollToBottom {
    NSInteger rowCount = [self.tableView numberOfRowsInSection:0];
    if (rowCount > 0) {
        NSIndexPath *lastIndexPath = [NSIndexPath indexPathForRow:rowCount - 1 inSection:0];
        [self.tableView scrollToRowAtIndexPath:lastIndexPath atScrollPosition:UITableViewScrollPositionBottom animated:YES];
    }
}

/// 流式输出期间的自动滚动：仅当用户在底部附近且未手动滚动时触发
- (void)scrollToBottomDuringStreaming {
    // 用户正在手动滚动时不干预
    if (self.tableView.isDragging || self.tableView.isDecelerating) return;

    CGFloat contentHeight = self.tableView.contentSize.height;
    CGFloat frameHeight = self.tableView.bounds.size.height;
    if (contentHeight <= frameHeight) return;

    CGFloat offsetY = self.tableView.contentOffset.y;
    CGFloat distFromBottom = contentHeight - offsetY - frameHeight;

    // 用户在底部 50pt 范围内才自动滚动（避免打断手动上滑浏览）
    if (distFromBottom < 50) {
        CGFloat maxOffsetY = contentHeight - frameHeight + self.tableView.contentInset.bottom;
        if (maxOffsetY > 0) {
            self.tableView.contentOffset = CGPointMake(0, maxOffsetY);
        }
    }
}

- (void)updateGridColorForState:(WebSocketConnectionState)state {
    UIColor *color;
    if (state == WebSocketConnectionStateConnected) {
        color = TechTheme.neonCyan;
    } else {
        color = TechTheme.neonRed;
    }
    _gridDim.strokeColor    = [color colorWithAlphaComponent:0.06].CGColor;
    _nodesDim.fillColor     = [color colorWithAlphaComponent:0.08].CGColor;
    _gridBright.strokeColor = [color colorWithAlphaComponent:0.30].CGColor;
    _nodesBright.fillColor  = [color colorWithAlphaComponent:0.40].CGColor;
}

- (void)updateStatusBar:(WebSocketConnectionState)state {
    dispatch_async(dispatch_get_main_queue(), ^{
        UIView *connDot = [self.statusBar viewWithTag:9001];
        [self updateGridColorForState:state];

        switch (state) {
            case WebSocketConnectionStateDisconnected:
                self.statusLabel.text = NSLocalizedString(@"status_disconnected", nil);
                self.statusLabel.textColor = TechTheme.textDim;
                self.statusIndicator.color = TechTheme.neonRed;
                [self.statusIndicator stopAnimating];
                connDot.backgroundColor = TechTheme.neonRed;
                [TechTheme removePulseAnimation:connDot];
                self.inputView.enabled = NO;
                break;
            case WebSocketConnectionStateConnecting:
                self.statusLabel.text = NSLocalizedString(@"status_connecting", nil);
                self.statusLabel.textColor = TechTheme.neonOrange;
                self.statusIndicator.color = TechTheme.neonOrange;
                [self.statusIndicator startAnimating];
                connDot.backgroundColor = TechTheme.neonOrange;
                [TechTheme addPulseAnimation:connDot color:[TechTheme.neonOrange colorWithAlphaComponent:0.5]];
                self.inputView.enabled = NO;
                break;
            case WebSocketConnectionStateConnected:
                self.statusLabel.text = NSLocalizedString(@"status_connected", nil);
                self.statusLabel.textColor = TechTheme.neonGreen;
                self.statusIndicator.color = TechTheme.neonGreen;
                [self.statusIndicator stopAnimating];
                connDot.backgroundColor = TechTheme.neonGreen;
                [TechTheme removePulseAnimation:connDot];
                [TechTheme applyNeonGlow:connDot color:TechTheme.neonGreen radius:5];
                self.inputView.enabled = YES;
                break;
            case WebSocketConnectionStateReconnecting:
                self.statusLabel.text = NSLocalizedString(@"status_reconnecting", nil);
                self.statusLabel.textColor = TechTheme.neonOrange;
                self.statusIndicator.color = TechTheme.neonOrange;
                [self.statusIndicator startAnimating];
                connDot.backgroundColor = TechTheme.neonOrange;
                [TechTheme addPulseAnimation:connDot color:[TechTheme.neonOrange colorWithAlphaComponent:0.5]];
                self.inputView.enabled = NO;
                break;
        }
    });
}

#pragma mark - UITableViewDataSource

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    return [self currentMessages].count;
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    NSMutableArray<Message *> *messages = [self currentMessages];
    if (indexPath.row >= (NSInteger)messages.count) {
        return [tableView dequeueReusableCellWithIdentifier:@"AssistantCell" forIndexPath:indexPath];
    }
    Message *message = messages[indexPath.row];
    NSString *reuseId;
    switch (message.role) {
        case MessageRoleUser:       reuseId = @"UserCell"; break;
        case MessageRoleToolCall:   reuseId = @"ToolCallCell"; break;
        case MessageRoleToolResult: reuseId = @"ToolResultCell"; break;
        default:                    reuseId = @"AssistantCell"; break;
    }
    MessageCell *cell = [tableView dequeueReusableCellWithIdentifier:reuseId forIndexPath:indexPath];
    cell.delegate = self;
    [cell configureWithMessage:message];
    return cell;
}

#pragma mark - UITableViewDelegate

- (CGFloat)tableView:(UITableView *)tableView heightForRowAtIndexPath:(NSIndexPath *)indexPath {
    NSMutableArray<Message *> *messages = [self currentMessages];
    if (indexPath.row >= (NSInteger)messages.count) return 80;
    Message *message = messages[indexPath.row];
    return [MessageCell heightForMessage:message tableViewWidth:tableView.bounds.size.width];
}

- (CGFloat)tableView:(UITableView *)tableView estimatedHeightForRowAtIndexPath:(NSIndexPath *)indexPath {
    // 根据消息内容长度估算行高，减少滚动时的高度跳变
    NSMutableArray<Message *> *messages = [self currentMessages];
    if (indexPath.row < (NSInteger)messages.count) {
        Message *message = messages[indexPath.row];
        NSUInteger len = message.content.length;
        if (message.role == MessageRoleUser) {
            return MAX(60, MIN(len * 0.4 + 60, 300));
        }
        // assistant / tool 消息通常更长
        return MAX(80, MIN(len * 0.3 + 80, 600));
    }
    return 80;
}

- (UIContextMenuConfiguration *)tableView:(UITableView *)tableView contextMenuConfigurationForRowAtIndexPath:(NSIndexPath *)indexPath point:(CGPoint)point {
    NSMutableArray<Message *> *messages = [self currentMessages];
    if (indexPath.row >= (NSInteger)messages.count) return nil;
    
    Message *message = messages[indexPath.row];
    
    return [UIContextMenuConfiguration configurationWithIdentifier:nil previewProvider:nil actionProvider:^UIMenu * _Nullable(NSArray<UIMenuElement *> * _Nonnull suggestedActions) {
        NSMutableArray<UIMenuElement *> *actions = [NSMutableArray array];
        
        UIAction *copyAction = [UIAction actionWithTitle:NSLocalizedString(@"copy", nil) image:[UIImage systemImageNamed:@"doc.on.doc"] identifier:nil handler:^(__kindof UIAction * _Nonnull action) {
            if (message.content.length > 0) {
                [UIPasteboard generalPasteboard].string = message.content;
            }
        }];
        [actions addObject:copyAction];

        // TTS 朗读
        BOOL ttsPlaying = [TTSService sharedService].isSpeaking;
        NSString *ttsTitle = ttsPlaying ? @"停止朗读" : @"朗读";
        NSString *ttsIcon = ttsPlaying ? @"speaker.slash" : @"speaker.wave.2";
        UIAction *ttsAction = [UIAction actionWithTitle:ttsTitle image:[UIImage systemImageNamed:ttsIcon] identifier:nil handler:^(__kindof UIAction * _Nonnull action) {
            if (ttsPlaying) {
                [[TTSService sharedService] stop];
            } else if (message.content.length > 0) {
                [[TTSService sharedService] speak:message.content];
            }
        }];
        [actions addObject:ttsAction];
        
        if (message.role == MessageRoleUser) {
            UIAction *editAction = [UIAction actionWithTitle:NSLocalizedString(@"re_edit", nil) image:[UIImage systemImageNamed:@"pencil"] identifier:nil handler:^(__kindof UIAction * _Nonnull action) {
                [self editMessage:message];
            }];
            [actions addObject:editAction];
            
            UIAction *deleteAction = [UIAction actionWithTitle:NSLocalizedString(@"delete", nil) image:[UIImage systemImageNamed:@"trash"] identifier:nil handler:^(__kindof UIAction * _Nonnull action) {
                [self deleteMessage:message];
            }];
            deleteAction.attributes = UIMenuElementAttributesDestructive;
            [actions addObject:deleteAction];
        }
        
        return [UIMenu menuWithTitle:@"" children:actions];
    }];
}

- (void)editMessage:(Message *)message {
    NSMutableArray<Message *> *messages = [self currentMessages];
    NSInteger idx = [messages indexOfObject:message];
    if (idx == NSNotFound) return;
    
    [self.inputView setText:message.content];
    
    NSRange range = NSMakeRange(idx, messages.count - idx);
    [messages removeObjectsInRange:range];
    self.currentAssistantMessage = nil;
    
    ConversationManager *manager = [ConversationManager sharedManager];
    Conversation *currentConv = manager.currentConversation;
    if (currentConv) {
        currentConv.updatedAt = [NSDate date];
        [[WebSocketService sharedService] clearSession:currentConv.conversationId];
        [manager saveConversations];
    }
    
    [self.tableView reloadData];
    [self scrollToBottom];
}

- (void)deleteMessage:(Message *)message {
    NSMutableArray<Message *> *messages = [self currentMessages];
    NSInteger idx = [messages indexOfObject:message];
    if (idx == NSNotFound) return;
    
    if (message.role == MessageRoleUser) {
        NSInteger deleteCount = 1;
        if (idx + 1 < (NSInteger)messages.count) {
            Message *next = messages[idx + 1];
            if (next.role == MessageRoleAssistant) {
                deleteCount = 2;
                if (next == self.currentAssistantMessage) {
                    self.currentAssistantMessage = nil;
                }
            }
        }
        [messages removeObjectsInRange:NSMakeRange(idx, deleteCount)];
    } else {
        [messages removeObjectAtIndex:idx];
        if (message == self.currentAssistantMessage) {
            self.currentAssistantMessage = nil;
        }
    }
    
    ConversationManager *manager = [ConversationManager sharedManager];
    Conversation *currentConv = manager.currentConversation;
    
    if (messages.count == 0 && currentConv) {
        [[WebSocketService sharedService] clearSession:currentConv.conversationId];
    }
    
    if (currentConv) {
        currentConv.updatedAt = [NSDate date];
        [manager saveConversations];
    }
    
    [self.tableView reloadData];
    [self scrollToBottom];
}

#pragma mark - InputViewDelegate

- (void)inputView:(InputView *)inputView didSendMessage:(NSString *)message {
    ConversationManager *manager = [ConversationManager sharedManager];
    Conversation *currentConv = manager.currentConversation;
    
    if (!currentConv) {
        currentConv = [manager createNewConversation];
    }
    
    Message *userMessage = [Message userMessageWithContent:message];
    [currentConv.messages addObject:userMessage];
    
    self.currentAssistantMessage = [Message assistantMessage];
    [currentConv.messages addObject:self.currentAssistantMessage];
    
    currentConv.updatedAt = [NSDate date];
    
    if (currentConv.messages.count == 2) {
        NSUInteger maxLength = MIN(30, message.length);
        currentConv.title = [message substringToIndex:maxLength];
        [self updateTitle];
    }
    
    [manager saveConversations];
    
    [self.tableView reloadData];
    [self scrollToBottom];
    [inputView clearText];
    
    self.inputView.loading = YES;
    if ([[NSUserDefaults standardUserDefaults] boolForKey:kUserDefaultsTTSEnabled]) {
        [[TTSService sharedService] resetStreamState];
    }
    // 远端 LLM 聊天也显示 Agent Live（与自主任务一致）
    [self showAgentLiveViewForChat];
    
    if (currentConv.targetType == ConversationTargetTypeDuck && currentConv.targetDuckId.length > 0) {
        [[WebSocketService sharedService] sendChatToDuck:message duckId:currentConv.targetDuckId sessionId:currentConv.conversationId];
    } else {
        [[WebSocketService sharedService] sendChatMessage:message sessionId:currentConv.conversationId];
    }
}

- (void)inputViewDidRequestVoiceInput:(InputView *)inputView {
    (void)inputView;
    
    // 未连接服务器时禁止开启语音模式
    if (!self.inputView.voiceInputActive &&
        [WebSocketService sharedService].connectionState != WebSocketConnectionStateConnected) {
        UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"无法使用语音"
                                                                       message:@"请先连接服务器后再使用语音输入"
                                                                preferredStyle:UIAlertControllerStyleAlert];
        [alert addAction:[UIAlertAction actionWithTitle:@"确定" style:UIAlertActionStyleDefault handler:nil]];
        [self presentViewController:alert animated:YES completion:nil];
        return;
    }
    
    VoiceInputService *voice = [VoiceInputService sharedService];
    
    // 用 UI 状态判断当前是否处于语音模式（比 voice.isRecording 更可靠，
    // 因为 startRecording 可能内部失败但 UI 已切换）
    if (self.inputView.voiceInputActive || voice.isRecording) {
        // 关闭语音模式
        NSString *committed = @"";
        if (voice.isRecording) {
            committed = [voice commitCurrentText];
        } else {
            [voice stopRecording]; // 确保清理
        }
        self.inputView.voiceInputActive = NO;
        [self.voiceRainbow stopFlowing];
        [self.voiceRainbow hideAnimated];
        [self.inputView setText:@""];
        if (committed.length > 0) {
            [self inputView:self.inputView didSendMessage:committed];
        }
    } else {
        // 开启语音模式
        [voice startRecording];
        self.inputView.voiceInputActive = YES;
        [self.voiceRainbow showAnimated];
        [self.voiceRainbow startFlowing];
    }
}

- (void)inputView:(InputView *)inputView didRequestSendAsAutonomousTask:(NSString *)text {
    (void)inputView;
    ConversationManager *manager = [ConversationManager sharedManager];
    Conversation *currentConv = manager.currentConversation;
    if (!currentConv) {
        currentConv = [manager createNewConversation];
    }
    NSString *userContent = [NSString stringWithFormat:@"🤖 [自主任务] %@", text];
    Message *userMessage = [Message userMessageWithContent:userContent];
    [currentConv.messages addObject:userMessage];
    self.currentAssistantMessage = [Message assistantMessage];
    self.currentAssistantMessage.content = NSLocalizedString(@"autonomous_starting", nil);
    [currentConv.messages addObject:self.currentAssistantMessage];
    currentConv.updatedAt = [NSDate date];
    if (currentConv.messages.count == 2) {
        NSUInteger maxLength = MIN(30, userContent.length);
        currentConv.title = [userContent substringToIndex:maxLength];
        [self updateTitle];
    }
    [manager saveConversations];
    [self.tableView reloadData];
    [self scrollToBottom];
    [self.inputView clearText];
    self.inputView.loading = YES;
    [self cancelAutonomousTimeout];
    __weak typeof(self) wself = self;
    self.autonomousTimeoutTimer = [NSTimer scheduledTimerWithTimeInterval:600 repeats:NO block:^(NSTimer * _Nonnull t) {
        dispatch_async(dispatch_get_main_queue(), ^{
            __strong typeof(wself) self = wself;
            if (!self) return;
            if (self.inputView.loading && self.currentAssistantMessage) {
                self.inputView.loading = NO;
                [self.currentAssistantMessage appendContent:@"\n\n[超时未收到完成信号，已停止等待]"];
                NSMutableArray<Message *> *messages = [self currentMessages];
                NSInteger idx = [messages indexOfObject:self.currentAssistantMessage];
                if (idx != NSNotFound) {
                    [self.tableView reloadRowsAtIndexPaths:@[[NSIndexPath indexPathForRow:idx inSection:0]] withRowAnimation:UITableViewRowAnimationNone];
                }
                ConversationManager *m = [ConversationManager sharedManager];
                if (m.currentConversation) {
                    m.currentConversation.updatedAt = [NSDate date];
                    [m saveConversations];
                }
                self.currentAssistantMessage = nil;
            }
            [self cancelAutonomousTimeout];
        });
    }];
    [[NSRunLoop mainRunLoop] addTimer:self.autonomousTimeoutTimer forMode:NSRunLoopCommonModes];
    [[WebSocketService sharedService] sendAutonomousTask:text sessionId:currentConv.conversationId];
}

- (void)cancelAutonomousTimeout {
    [self.autonomousTimeoutTimer invalidate];
    self.autonomousTimeoutTimer = nil;
}

- (void)inputViewDidRequestStop:(InputView *)inputView {
    (void)inputView;
    [self cancelAutonomousTimeout];
    [[TTSService sharedService] stop];
    self.inputView.loading = NO;
    
    ConversationManager *manager = [ConversationManager sharedManager];
    Conversation *currentConv = manager.currentConversation;
    
    if (currentConv) {
        [[WebSocketService sharedService] sendStopStream:currentConv.conversationId];
    }
    
    if (self.currentAssistantMessage) {
        self.currentAssistantMessage.content = [self.currentAssistantMessage.content stringByAppendingString:@"\n\n[已终止]"];
        self.currentAssistantMessage.status = MessageStatusComplete;
        NSMutableArray<Message *> *messages = [self currentMessages];
        NSInteger index = [messages indexOfObject:self.currentAssistantMessage];
        if (index != NSNotFound) {
            NSIndexPath *indexPath = [NSIndexPath indexPathForRow:index inSection:0];
            [self.tableView reloadRowsAtIndexPaths:@[indexPath] withRowAnimation:UITableViewRowAnimationNone];
        }
        self.currentAssistantMessage = nil;
        
        if (currentConv) {
            currentConv.updatedAt = [NSDate date];
            [manager saveConversations];
        }
    }
}

#pragma mark - WebSocketServiceDelegate

- (void)webSocketService:(WebSocketService *)service didChangeState:(WebSocketConnectionState)state {
    [self updateStatusBar:state];
}

- (void)webSocketService:(WebSocketService *)service didConnectWithClientId:(NSString *)clientId sessionId:(NSString *)sessionId hasRunningTask:(BOOL)hasRunningTask runningTaskId:(NSString *)runningTaskId hasRunningChat:(BOOL)hasRunningChat hasBufferedChat:(BOOL)hasBufferedChat bufferedChatCount:(NSInteger)bufferedChatCount {
    NSLog(@"Connected: client=%@, session=%@, running_task=%d, running_chat=%d, buffered_chat=%d, buffered_count=%ld", 
          clientId, sessionId, hasRunningTask, hasRunningChat, hasBufferedChat, (long)bufferedChatCount);
    
    dispatch_async(dispatch_get_main_queue(), ^{
        ConversationManager *manager = [ConversationManager sharedManager];
        NSString *localSessionId = manager.currentConversation.conversationId;
        
        // 检查后端 session_id 是否与本地会话匹配
        if (localSessionId && ![localSessionId isEqualToString:sessionId]) {
            // Session 不匹配（App 重启场景），需要先同步 session_id
            NSLog(@"[WebSocket] Session mismatch: backend=%@ local=%@, syncing session", sessionId, localSessionId);
            [[WebSocketService sharedService] createNewSession:localSessionId];
            // 仅当有未完成的 streaming 消息时才发送 resume_chat，
            // 避免已完成的对话被重复发送
            if (self.currentAssistantMessage) {
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
                    NSLog(@"[WebSocket] Resuming pending streaming chat for local session: %@", localSessionId);
                    [[WebSocketService sharedService] resumeChat:localSessionId];
                });
            } else {
                NSLog(@"[WebSocket] No pending streaming message, skipping resume_chat to avoid duplication");
            }
        } else if (hasRunningChat || hasBufferedChat) {
            // Session 匹配且有缓冲消息，直接恢复
            NSLog(@"[WebSocket] Resuming chat: running=%d, buffered=%d", hasRunningChat, hasBufferedChat);
            [[WebSocketService sharedService] resumeChat:sessionId];
        }
    });
}

// 向后兼容旧的 delegate 方法
- (void)webSocketService:(WebSocketService *)service didConnectWithClientId:(NSString *)clientId sessionId:(NSString *)sessionId hasRunningTask:(BOOL)hasRunningTask runningTaskId:(NSString *)runningTaskId hasRunningChat:(BOOL)hasRunningChat {
    NSLog(@"Connected (legacy): client=%@, session=%@, running_task=%d, running_chat=%d", 
          clientId, sessionId, hasRunningTask, hasRunningChat);
    
    dispatch_async(dispatch_get_main_queue(), ^{
        ConversationManager *manager = [ConversationManager sharedManager];
        NSString *localSessionId = manager.currentConversation.conversationId;
        
        // 检查后端 session_id 是否与本地会话匹配
        if (localSessionId && ![localSessionId isEqualToString:sessionId]) {
            NSLog(@"[WebSocket] Session mismatch (legacy): syncing to %@", localSessionId);
            [[WebSocketService sharedService] createNewSession:localSessionId];
            // 仅当有未完成的 streaming 消息时才发送 resume_chat
            if (self.currentAssistantMessage) {
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
                    [[WebSocketService sharedService] resumeChat:localSessionId];
                });
            } else {
                NSLog(@"[WebSocket] No pending streaming message (legacy), skipping resume_chat");
            }
        } else if (hasRunningChat) {
            [[WebSocketService sharedService] resumeChat:sessionId];
        }
    });
}

- (void)webSocketService:(WebSocketService *)service didReceiveContent:(NSString *)content {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.currentAssistantMessage) {
            [self.currentAssistantMessage appendContent:content];
            // TTS 已移至 flushStreamingCellUpdate 节流路径，不再每个 chunk 都处理
            [self throttledUpdateStreamingCell];
        }
    });
}

/// 节流更新流式输出的 cell：每 120ms 最多刷新一次，避免阻塞主线程导致无法滚动
- (void)throttledUpdateStreamingCell {
    NSDate *now = [NSDate date];
    if (self.lastStreamingUIUpdateTime && [now timeIntervalSinceDate:self.lastStreamingUIUpdateTime] < kStreamingThrottleInterval) {
        // 节流期间：标记有待更新，稍后触发
        if (!self.hasPendingStreamingUpdate) {
            self.hasPendingStreamingUpdate = YES;
            NSTimeInterval delay = kStreamingThrottleInterval - [now timeIntervalSinceDate:self.lastStreamingUIUpdateTime];
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(delay * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
                self.hasPendingStreamingUpdate = NO;
                [self flushStreamingCellUpdate];
            });
        }
        return;
    }
    [self flushStreamingCellUpdate];
}

- (void)flushStreamingCellUpdate {
    self.lastStreamingUIUpdateTime = [NSDate date];
    if (!self.currentAssistantMessage) return;

    // TTS 处理移到节流路径，每 ~120ms 最多处理一次（而非每个 chunk）
    if ([[NSUserDefaults standardUserDefaults] boolForKey:kUserDefaultsTTSEnabled]) {
        NSString *full = self.currentAssistantMessage.content ?: @"";
        [[TTSService sharedService] appendAndSpeakStreamedContent:full];
    }

    NSMutableArray<Message *> *messages = [self currentMessages];
    NSInteger index = [messages indexOfObject:self.currentAssistantMessage];
    if (index == NSNotFound) return;

    NSIndexPath *indexPath = [NSIndexPath indexPathForRow:index inSection:0];
    MessageCell *cell = (MessageCell *)[self.tableView cellForRowAtIndexPath:indexPath];
    if (cell) {
        // 直接更新 cell 内容，避免 reloadRows 触发 prepareForReuse 丢失缓存
        [cell configureWithMessage:self.currentAssistantMessage];
    }

    // 每 N 次节流更新才刷新行高，减少 beginUpdates 触发的 layout 开销
    self.streamingHeightUpdateCounter++;
    if (self.streamingHeightUpdateCounter % kStreamingHeightUpdateDivisor == 0) {
        [UIView performWithoutAnimation:^{
            [self.tableView beginUpdates];
            [self.tableView endUpdates];
        }];
    }

    // 流式输出时自动滚动到底部
    [self scrollToBottomDuringStreaming];
}

- (void)webSocketService:(WebSocketService *)service didReceiveToolCall:(NSString *)toolName callId:(NSString *)callId arguments:(NSString *)arguments {
    dispatch_async(dispatch_get_main_queue(), ^{
        // 与 Mac 端一致：不展示工具调用过程，仅保留助手回复
        (void)toolName;
        (void)callId;
        (void)arguments;
    });
}

- (void)webSocketService:(WebSocketService *)service didReceiveToolResult:(NSString *)callId result:(NSString *)result {
    dispatch_async(dispatch_get_main_queue(), ^{
        // 与 Mac 端一致：不展示工具结果 JSON，图片通过 didReceiveImage 并入助手消息
        (void)callId;
        (void)result;
    });
}

- (void)webSocketService:(WebSocketService *)service didReceiveImage:(NSString *)base64 mimeType:(NSString *)mimeType {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.currentAssistantMessage) {
            self.currentAssistantMessage.imageBase64 = base64;
            NSMutableArray<Message *> *messages = [self currentMessages];
            NSInteger index = [messages indexOfObject:self.currentAssistantMessage];
            if (index != NSNotFound) {
                NSIndexPath *indexPath = [NSIndexPath indexPathForRow:index inSection:0];
                [self.tableView reloadRowsAtIndexPaths:@[indexPath] withRowAnimation:UITableViewRowAnimationNone];
                [self scrollToBottom];
            }
        }
    });
}

- (void)webSocketService:(WebSocketService *)service didReceiveUserMessage:(NSString *)content fromClient:(NSString *)clientId clientType:(NSString *)clientType {
    dispatch_async(dispatch_get_main_queue(), ^{
        ConversationManager *manager = [ConversationManager sharedManager];
        Conversation *currentConv = manager.currentConversation;
        
        if (!currentConv) {
            currentConv = [manager createNewConversation];
        }
        
        Message *userMessage = [Message userMessageWithContent:content];
        userMessage.fromClient = clientId;
        userMessage.fromClientType = clientType;
        [currentConv.messages addObject:userMessage];
        
        self.currentAssistantMessage = [Message assistantMessage];
        [currentConv.messages addObject:self.currentAssistantMessage];
        
        currentConv.updatedAt = [NSDate date];
        [manager saveConversations];
        
        [self.tableView reloadData];
        [self scrollToBottom];
    });
}

- (void)webSocketServiceDidCompleteSend:(WebSocketService *)service modelName:(NSString *)modelName tokenUsage:(NSDictionary<NSString *,NSNumber *> *)tokenUsage {
    dispatch_async(dispatch_get_main_queue(), ^{
        [self cancelAutonomousTimeout];
        // 重置流式节流状态
        self.lastStreamingUIUpdateTime = nil;
        self.hasPendingStreamingUpdate = NO;
        self.streamingHeightUpdateCounter = 0;
        self.inputView.loading = NO;
        // 远端 LLM 完成，延迟隐藏 Agent Live
        [self scheduleHideAgentLiveIfNotRunning];
        if (self.currentAssistantMessage) {
            self.currentAssistantMessage.status = MessageStatusComplete;
            self.currentAssistantMessage.modelName = modelName;
            
            if (tokenUsage) {
                NSNumber *totalTokens = tokenUsage[@"total_tokens"];
                if (totalTokens) {
                    NSLog(@"[Chat] Token usage: %@", totalTokens);
                }
            }
            
            NSMutableArray<Message *> *messages = [self currentMessages];
            NSInteger index = [messages indexOfObject:self.currentAssistantMessage];
            if (index != NSNotFound) {
                NSIndexPath *indexPath = [NSIndexPath indexPathForRow:index inSection:0];
                [self.tableView reloadRowsAtIndexPaths:@[indexPath] withRowAnimation:UITableViewRowAnimationNone];
            }
            
            self.currentAssistantMessage = nil;
            
            ConversationManager *manager = [ConversationManager sharedManager];
            if (manager.currentConversation) {
                manager.currentConversation.updatedAt = [NSDate date];
                [manager saveConversations];
            }
        }
        if ([[NSUserDefaults standardUserDefaults] boolForKey:kUserDefaultsTTSEnabled]) {
            [[TTSService sharedService] speakRemainingBuffer];
        }
    });
}

- (void)webSocketServiceDidStop:(WebSocketService *)service {
    dispatch_async(dispatch_get_main_queue(), ^{
        [self cancelAutonomousTimeout];
        self.inputView.loading = NO;
        [self scheduleHideAgentLiveIfNotRunning];
        if (self.currentAssistantMessage) {
            self.currentAssistantMessage.content = [self.currentAssistantMessage.content stringByAppendingString:@"\n\n[已终止]"];
            self.currentAssistantMessage.status = MessageStatusComplete;
            NSMutableArray<Message *> *messages = [self currentMessages];
            NSInteger index = [messages indexOfObject:self.currentAssistantMessage];
            if (index != NSNotFound) {
                NSIndexPath *indexPath = [NSIndexPath indexPathForRow:index inSection:0];
                [self.tableView reloadRowsAtIndexPaths:@[indexPath] withRowAnimation:UITableViewRowAnimationNone];
            }
            self.currentAssistantMessage = nil;
            
            ConversationManager *manager = [ConversationManager sharedManager];
            if (manager.currentConversation) {
                manager.currentConversation.updatedAt = [NSDate date];
                [manager saveConversations];
            }
        }
    });
}

- (void)webSocketServiceDidClearSession:(WebSocketService *)service {
    dispatch_async(dispatch_get_main_queue(), ^{
        self.inputView.loading = NO;
        [self hideAgentLiveView];
        
        ConversationManager *manager = [ConversationManager sharedManager];
        Conversation *currentConv = manager.currentConversation;
        
        if (currentConv) {
            [currentConv.messages removeAllObjects];
            currentConv.updatedAt = [NSDate date];
            [manager saveConversations];
        }
        
        self.currentAssistantMessage = nil;
        [self.tableView reloadData];
    });
}

- (void)webSocketService:(WebSocketService *)service didReceiveMonitorEvent:(NSDictionary *)event sessionId:(NSString *)sessionId taskId:(NSString *)taskId taskType:(NSString *)taskType {
    dispatch_async(dispatch_get_main_queue(), ^{
        ConversationManager *manager = [ConversationManager sharedManager];
        NSString *currentSessionId = manager.currentConversation.conversationId ?: @"";
        if (sessionId.length > 0 && currentSessionId.length > 0 && ![sessionId isEqualToString:currentSessionId]) {
            return;  // 非当前会话的监控事件，忽略
        }
        NSString *evType = event[@"type"];
        if ([taskType isEqualToString:@"chat"]) {
            // 远端 LLM 聊天的 monitor_event
            if ([evType isEqualToString:@"task_start"]) {
                [self showAgentLiveView];
                NSMutableDictionary *taskStartData = [event mutableCopy];
                if (taskId.length) taskStartData[@"task_id"] = taskId;
                if (!self.agentLiveView.taskProgress) {
                    self.agentLiveView.taskProgress = [TaskProgress progressWithTaskId:taskId ?: @"chat" description:event[@"task"] ?: @"LLM 思考中"];
                }
                [self.agentLiveView.taskProgress handleTaskStart:taskStartData];
                [self updateAgentLiveViewHeight];
            } else if ([evType isEqualToString:@"llm_request_start"]) {
                if (self.agentLiveView.taskProgress) {
                    [self.agentLiveView handleLLMRequestStart:event];
                }
            } else if ([evType isEqualToString:@"llm_request_end"]) {
                if (self.agentLiveView.taskProgress) {
                    [self.agentLiveView handleLLMRequestEnd:event];
                }
            } else if ([evType isEqualToString:@"tool_call"]) {
                NSString *toolName = event[@"name"] ?: event[@"tool_name"];
                if (toolName && self.agentLiveView.taskProgress) {
                    [self.agentLiveView.taskProgress recordToolCallForDisplay:toolName];
                    [self.agentLiveView updateWithTaskProgress:self.agentLiveView.taskProgress];
                    [self updateAgentLiveViewHeight];
                }
            } else if ([evType isEqualToString:@"task_complete"] || [evType isEqualToString:@"task_stopped"] || [evType isEqualToString:@"error"]) {
                if (self.agentLiveView.taskProgress) {
                    if ([evType isEqualToString:@"task_complete"]) {
                        [self.agentLiveView handleTaskComplete:event];
                    } else if ([evType isEqualToString:@"task_stopped"]) {
                        [self.agentLiveView handleTaskStopped:event];
                    }
                    [self scheduleHideAgentLiveIfNotRunning];
                }
            }
        }
    });
}

- (void)webSocketService:(WebSocketService *)service didReceiveError:(NSString *)errorMessage {
    dispatch_async(dispatch_get_main_queue(), ^{
        [self cancelAutonomousTimeout];
        self.inputView.loading = NO;
        [self scheduleHideAgentLiveIfNotRunning];
        if (self.currentAssistantMessage) {
            self.currentAssistantMessage.content = [NSString stringWithFormat:NSLocalizedString(@"error_format", nil), errorMessage];
            self.currentAssistantMessage.status = MessageStatusError;
            
            NSMutableArray<Message *> *messages = [self currentMessages];
            NSInteger index = [messages indexOfObject:self.currentAssistantMessage];
            if (index != NSNotFound) {
                NSIndexPath *indexPath = [NSIndexPath indexPathForRow:index inSection:0];
                [self.tableView reloadRowsAtIndexPaths:@[indexPath] withRowAnimation:UITableViewRowAnimationNone];
            }
            
            self.currentAssistantMessage = nil;
            
            ConversationManager *manager = [ConversationManager sharedManager];
            if (manager.currentConversation) {
                manager.currentConversation.updatedAt = [NSDate date];
                [manager saveConversations];
            }
        }
    });
}

- (void)webSocketService:(WebSocketService *)service didReceiveChatToDuckError:(NSString *)errorMessage duckId:(NSString *)duckId {
    dispatch_async(dispatch_get_main_queue(), ^{
        self.inputView.loading = NO;
        [self scheduleHideAgentLiveIfNotRunning];
        if (self.currentAssistantMessage) {
            self.currentAssistantMessage.content = [NSString stringWithFormat:@"❌ %@", errorMessage];
            self.currentAssistantMessage.status = MessageStatusError;
            NSMutableArray<Message *> *messages = [self currentMessages];
            NSInteger index = [messages indexOfObject:self.currentAssistantMessage];
            if (index != NSNotFound) {
                [self.tableView reloadRowsAtIndexPaths:@[[NSIndexPath indexPathForRow:index inSection:0]] withRowAnimation:UITableViewRowAnimationNone];
            }
            self.currentAssistantMessage = nil;
        }
        ConversationManager *manager = [ConversationManager sharedManager];
        if (manager.currentConversation) {
            manager.currentConversation.updatedAt = [NSDate date];
            [manager saveConversations];
        }
        UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"Duck 不可用"
                                                                       message:errorMessage
                                                                preferredStyle:UIAlertControllerStyleAlert];
        [alert addAction:[UIAlertAction actionWithTitle:@"确定" style:UIAlertActionStyleDefault handler:nil]];
        [self presentViewController:alert animated:YES completion:nil];
    });
}

- (void)webSocketService:(WebSocketService *)service didAcceptChatToDuck:(NSString *)duckId taskId:(NSString *)taskId {
    dispatch_async(dispatch_get_main_queue(), ^{
        // Duck 已接受任务，更新占位消息提示正在处理
        if (self.currentAssistantMessage && self.currentAssistantMessage.status == MessageStatusStreaming) {
            self.currentAssistantMessage.content = @"🦆 Duck 正在处理中…";
            NSMutableArray<Message *> *messages = [self currentMessages];
            NSInteger index = [messages indexOfObject:self.currentAssistantMessage];
            if (index != NSNotFound) {
                [self.tableView reloadRowsAtIndexPaths:@[[NSIndexPath indexPathForRow:index inSection:0]] withRowAnimation:UITableViewRowAnimationNone];
            }
        }
        NSLog(@"[Chat] chat_to_duck_accepted: duck_id=%@ task_id=%@", duckId, taskId);
    });
}

- (void)webSocketService:(WebSocketService *)service didReceiveDuckTaskComplete:(NSString *)content success:(BOOL)success sessionId:(NSString *)sessionId {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (!content.length) return;
        ConversationManager *manager = [ConversationManager sharedManager];
        Conversation *conv = nil;
        for (Conversation *c in manager.conversations) {
            if ([c.conversationId isEqualToString:sessionId]) {
                conv = c;
                break;
            }
        }
        if (!conv) return;
        Message *msg = [Message assistantMessage];
        msg.content = content;
        msg.status = success ? MessageStatusComplete : MessageStatusError;
        msg.modelName = @"Duck";
        msg.timestamp = [NSDate date];
        msg.messageId = [[NSUUID UUID] UUIDString];
        [conv.messages addObject:msg];
        conv.updatedAt = [NSDate date];
        [manager saveConversations];
        if (manager.currentConversation == conv) {
            [self.tableView reloadData];
            [self scrollToBottom];
        }
        NSLog(@"[Chat] duck_task_complete: session=%@ success=%d", sessionId, success);
    });
}

- (void)webSocketService:(WebSocketService *)service didReceiveChatToDuckResult:(NSString *)output duckId:(NSString *)duckId taskId:(NSString *)taskId success:(BOOL)success error:(NSString *)errorMessage {
    dispatch_async(dispatch_get_main_queue(), ^{
        self.inputView.loading = NO;
        [self scheduleHideAgentLiveIfNotRunning];

        if (self.currentAssistantMessage) {
            if (success && output.length > 0) {
                self.currentAssistantMessage.content = output;
                self.currentAssistantMessage.status = MessageStatusError;
            } else {
                NSString *msg = errorMessage.length > 0 ? errorMessage : @"Duck 未返回结果";
                self.currentAssistantMessage.content = [NSString stringWithFormat:@"❌ %@", msg];
                self.currentAssistantMessage.status = MessageStatusError;
            }
            NSMutableArray<Message *> *messages = [self currentMessages];
            NSInteger index = [messages indexOfObject:self.currentAssistantMessage];
            if (index != NSNotFound) {
                [self.tableView reloadRowsAtIndexPaths:@[[NSIndexPath indexPathForRow:index inSection:0]] withRowAnimation:UITableViewRowAnimationNone];
            }
            self.currentAssistantMessage = nil;
        }

        ConversationManager *manager = [ConversationManager sharedManager];
        if (manager.currentConversation) {
            manager.currentConversation.updatedAt = [NSDate date];
            [manager saveConversations];
        }
        [self scrollToBottom];
        NSLog(@"[Chat] chat_to_duck_result: duck_id=%@ success=%d", duckId, success);
    });
}

- (void)webSocketService:(WebSocketService *)service didReceiveWebAugmentation:(NSString *)augmentationType query:(NSString *)query {
    dispatch_async(dispatch_get_main_queue(), ^{
        NSLog(@"[Chat] Web augmentation: type=%@, query=%@", augmentationType, query);
    });
}

- (void)webSocketService:(WebSocketService *)service didReceiveExecutionLog:(NSString *)toolName level:(NSString *)level message:(NSString *)message {
    dispatch_async(dispatch_get_main_queue(), ^{
        NSLog(@"[Chat] Execution log [%@] %@: %@", level, toolName, message);
    });
}

- (void)webSocketService:(WebSocketService *)service didReceiveSystemNotification:(NSDictionary *)notification unreadCount:(NSInteger)unreadCount {
    dispatch_async(dispatch_get_main_queue(), ^{
        NSLog(@"[Chat] System notification: %@ (unread: %ld)", notification, (long)unreadCount);
    });
}

- (void)webSocketServiceDidReceiveToolsUpdated:(WebSocketService *)service {
    dispatch_async(dispatch_get_main_queue(), ^{
        NSLog(@"[Chat] Tools updated");
    });
}

- (void)webSocketService:(WebSocketService *)service didResumeChatWithId:(NSString *)taskId status:(NSString *)status bufferedCount:(NSInteger)bufferedCount {
    // 调用带 messageId 的版本，传 nil
    [self webSocketService:service didResumeChatWithId:taskId status:status bufferedCount:bufferedCount messageId:nil];
}

- (void)webSocketService:(WebSocketService *)service didResumeChatWithId:(NSString *)taskId status:(NSString *)status bufferedCount:(NSInteger)bufferedCount messageId:(NSString *)messageId {
    dispatch_async(dispatch_get_main_queue(), ^{
        NSLog(@"[Chat] Resume chat: task=%@, status=%@, buffered=%ld, msgId=%@", taskId, status, (long)bufferedCount, messageId);
        
        // 去重检查：如果这条消息已经显示过，跳过
        if (messageId && [self.displayedMessageIds containsObject:messageId]) {
            NSLog(@"[Chat] Message %@ already displayed, skipping resume", messageId);
            return;
        }
        
        ConversationManager *manager = [ConversationManager sharedManager];
        Conversation *currentConv = manager.currentConversation;
        if (!currentConv) {
            NSLog(@"[Chat] No current conversation for resume");
            return;
        }
        
        // 如果有缓冲的消息要恢复
        if (bufferedCount > 0) {
            // 记录这条消息已处理
            if (messageId) {
                [self.displayedMessageIds addObject:messageId];
            }
            
            // 确保有 assistant message 来接收缓冲内容
            if (!self.currentAssistantMessage) {
                // 检查是否已有 streaming 状态的消息
                Message *lastMessage = currentConv.messages.lastObject;
                if (lastMessage.role == MessageRoleAssistant && lastMessage.status == MessageStatusStreaming) {
                    NSLog(@"[Chat] Using existing streaming message for resume");
                    self.currentAssistantMessage = lastMessage;
                } else if (lastMessage.role == MessageRoleAssistant && lastMessage.content.length > 0) {
                    // 最后一条助手消息已有内容且非 streaming，说明之前的回复已完整接收
                    // 跳过 resume 以避免重复显示相同内容
                    NSLog(@"[Chat] Last assistant message already has content (len=%lu), skipping resume to avoid duplication", (unsigned long)lastMessage.content.length);
                    return;
                } else {
                    NSLog(@"[Chat] Creating new assistant message for resume");
                    self.currentAssistantMessage = [Message assistantMessage];
                    [currentConv.messages addObject:self.currentAssistantMessage];
                }
            }
            
            [self.tableView reloadData];
            [self scrollToBottom];
            self.inputView.loading = YES;
        }
        
        // 如果任务已经完成但没有缓冲消息（可能后端缓冲已清空）
        BOOL isCompleted = [status isEqualToString:@"completed"] || [status isEqualToString:@"stopped"] || [status isEqualToString:@"error"];
        if (isCompleted && bufferedCount == 0 && self.currentAssistantMessage) {
            NSLog(@"[Chat] Task completed but no buffered messages, completing current message");
            if (self.currentAssistantMessage.content.length == 0) {
                self.currentAssistantMessage.content = @"[消息恢复失败]";
            }
            self.currentAssistantMessage.status = MessageStatusComplete;
            self.currentAssistantMessage = nil;
            self.inputView.loading = NO;
            [self.tableView reloadData];
            [manager saveConversations];
        }
    });
}

- (void)webSocketService:(WebSocketService *)service taskResumeDidFail:(NSString *)message {
    dispatch_async(dispatch_get_main_queue(), ^{
        NSLog(@"[Chat] Task resume failed: %@", message);
        
        // 如果有未完成的 streaming 消息，标记为完成
        if (self.currentAssistantMessage) {
            if (self.currentAssistantMessage.content.length == 0) {
                self.currentAssistantMessage.content = @"[消息恢复失败]";
            }
            self.currentAssistantMessage.status = MessageStatusComplete;
            self.currentAssistantMessage = nil;
            self.inputView.loading = NO;
            [self.tableView reloadData];
            
            ConversationManager *manager = [ConversationManager sharedManager];
            [manager saveConversations];
        }
    });
}

- (void)webSocketService:(WebSocketService *)service didReceiveSpeak:(NSString *)text {
    dispatch_async(dispatch_get_main_queue(), ^{
        [[TTSService sharedService] speak:text];
    });
}

- (void)webSocketService:(WebSocketService *)service didReceiveAutonomousChunk:(NSDictionary *)chunk {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (!self.currentAssistantMessage) return;
        NSString *type = chunk[@"type"];
        NSMutableString *append = [NSMutableString string];
        
        // 同时更新 AgentLiveView
        if ([type isEqualToString:@"task_start"]) {
            [self showAgentLiveView];
            NSString *taskId = chunk[@"task_id"] ?: @"";
            NSString *taskDesc = chunk[@"task"] ?: @"";
            self.agentLiveView.taskProgress = [TaskProgress progressWithTaskId:taskId description:taskDesc];
            [self.agentLiveView.taskProgress handleTaskStart:chunk];
            [self updateAgentLiveViewHeight];
            [append appendString:@"🚀 任务开始执行...\n"];
        } else if ([type isEqualToString:@"model_selected"]) {
            NSString *modelType = chunk[@"model_type"] ?: @"";
            NSString *reason = chunk[@"reason"] ?: @"";
            NSString *icon = [modelType isEqualToString:@"local"] ? @"🏠" : @"☁️";
            NSString *name = [modelType isEqualToString:@"local"] ? NSLocalizedString(@"model_local", nil) : NSLocalizedString(@"model_remote", nil);
            [self.agentLiveView.taskProgress handleModelSelected:chunk];
            [append appendFormat:@"%@ 选择模型: %@\n", icon, name];
            if (reason.length) [append appendFormat:@"💡 %@\n\n", reason];
        } else if ([type isEqualToString:@"action_plan"]) {
            [self.agentLiveView handleActionPlan:chunk];
            [self updateAgentLiveViewHeight];
            NSDictionary *action = chunk[@"action"];
            NSString *actionType = ([action isKindOfClass:[NSDictionary class]] ? action[@"action_type"] : nil) ?: @"unknown";
            NSString *reasoning = ([action isKindOfClass:[NSDictionary class]] ? action[@"reasoning"] : nil) ?: @"";
            NSNumber *iter = chunk[@"iteration"];
            [append appendFormat:@"\n📋 步骤 %@: %@\n   → %@\n", iter ? iter.stringValue : @"?", actionType, reasoning];
        } else if ([type isEqualToString:@"action_executing"]) {
            [self.agentLiveView handleActionExecuting:chunk];
            NSString *actionType = chunk[@"action_type"] ?: @"";
            [append appendFormat:@"⏳ 执行中: %@\n", actionType];
        } else if ([type isEqualToString:@"action_result"]) {
            [self.agentLiveView handleActionResult:chunk];
            id succ = chunk[@"success"];
            BOOL success = ([succ isKindOfClass:[NSNumber class]] ? [succ boolValue] : NO);
            NSString *output = chunk[@"output"] ?: @"";
            NSString *err = chunk[@"error"] ?: @"";
            if (success && output.length) [append appendFormat:@"   ✓ %@\n", output];
            else if (err.length) [append appendFormat:@"   ✗ %@\n", err];
        } else if ([type isEqualToString:@"llm_request_start"]) {
            [self.agentLiveView handleLLMRequestStart:chunk];
        } else if ([type isEqualToString:@"llm_request_end"]) {
            [self.agentLiveView handleLLMRequestEnd:chunk];
        } else if ([type isEqualToString:@"reflect_start"]) {
            [append appendString:@"\n🔄 反思中...\n"];
        } else if ([type isEqualToString:@"reflect_result"]) {
            NSString *ref = chunk[@"reflection"] ?: chunk[@"error"] ?: @"";
            if (ref.length) [append appendFormat:@"   %@\n", ref];
        } else if ([type isEqualToString:@"task_complete"]) {
            [self.agentLiveView handleTaskComplete:chunk];
            id succ = chunk[@"success"];
            BOOL success = ([succ isKindOfClass:[NSNumber class]] ? [succ boolValue] : NO);
            NSString *summary = chunk[@"summary"] ?: @"";
            [append appendFormat:@"\n%@ 任务完成\n%@\n", success ? @"✅" : @"⚠️", summary];
        } else if ([type isEqualToString:@"task_stopped"]) {
            [self.agentLiveView handleTaskStopped:chunk];
            [append appendFormat:@"\n⏹ %@\n", chunk[@"message"] ?: chunk[@"reason"] ?: NSLocalizedString(@"autonomous_stopped", nil)];
        } else if ([type isEqualToString:@"progress_update"]) {
            [self.agentLiveView.taskProgress handleProgressUpdate:chunk];
            NSString *msg = chunk[@"message"] ?: @"";
            if (msg.length) [append appendFormat:@"%@\n", msg];
        }
        
        if (append.length > 0) {
            self.currentAssistantMessage.content = [self.currentAssistantMessage.content stringByAppendingString:append];
            NSMutableArray<Message *> *messages = [self currentMessages];
            NSInteger index = [messages indexOfObject:self.currentAssistantMessage];
            if (index != NSNotFound) {
                [self.tableView reloadRowsAtIndexPaths:@[[NSIndexPath indexPathForRow:index inSection:0]] withRowAnimation:UITableViewRowAnimationNone];
                [self scrollToBottom];
            }
        }
        if ([type isEqualToString:@"task_complete"] || [type isEqualToString:@"task_stopped"] || [type isEqualToString:@"error"]) {
            [self cancelAutonomousTimeout];
            self.inputView.loading = NO;
            self.currentAssistantMessage.status = MessageStatusComplete;
            ConversationManager *manager = [ConversationManager sharedManager];
            if (manager.currentConversation) {
                manager.currentConversation.updatedAt = [NSDate date];
                [manager saveConversations];
            }
            self.currentAssistantMessage = nil;
            // 延迟隐藏 Agent Live 面板
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(3.0 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
                if (!self.agentLiveView.isRunning) {
                    [self hideAgentLiveView];
                }
            });
        }
    });
}

#pragma mark - Agent Live View

- (void)showAgentLiveView {
    self.agentLiveView.hidden = NO;
    [self updateAgentLiveViewHeight];
    [UIView animateWithDuration:0.3 animations:^{
        [self.view layoutIfNeeded];
    }];
}

/// 远端 LLM 聊天开始时显示 Agent Live（无 task_start 时先展示占位）
- (void)showAgentLiveViewForChat {
    if (!self.agentLiveView.taskProgress) {
        self.agentLiveView.taskProgress = [TaskProgress progressWithTaskId:@"chat" description:@"LLM 思考中"];
        self.agentLiveView.taskProgress.isRunning = YES;
    }
    [self showAgentLiveView];
}

/// 延迟隐藏 Agent Live（任务/聊天结束后 3 秒）
- (void)scheduleHideAgentLiveIfNotRunning {
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(3.0 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        if (!self.agentLiveView.isRunning) {
            [self hideAgentLiveView];
        }
    });
}

- (void)hideAgentLiveView {
    [UIView animateWithDuration:0.3 animations:^{
        self.agentLiveHeightConstraint.constant = 0;
        [self.view layoutIfNeeded];
    } completion:^(BOOL finished) {
        self.agentLiveView.hidden = YES;
        [self.agentLiveView reset];
    }];
}

- (void)updateAgentLiveViewHeight {
    CGFloat height = [self.agentLiveView requiredHeight];
    self.agentLiveHeightConstraint.constant = height;
    [self.view layoutIfNeeded];
}

#pragma mark - AgentLiveViewDelegate

- (void)agentLiveViewDidToggle:(AgentLiveView *)view {
    [self updateAgentLiveViewHeight];
    [UIView animateWithDuration:0.2 animations:^{
        [self.view layoutIfNeeded];
    }];
}

- (void)agentLiveViewDidRequestStop:(AgentLiveView *)view {
    ConversationManager *manager = [ConversationManager sharedManager];
    NSString *sessionId = manager.currentConversation.conversationId ?: @"default";
    [[WebSocketService sharedService] sendStopStream:sessionId];
}

- (void)agentLiveView:(AgentLiveView *)view didSelectActionLog:(ActionLogEntry *)entry {
    // 显示 action 详情（可选：弹出 alert 或跳转到详情页）
    NSString *detail = [NSString stringWithFormat:@"类型: %@\n状态: %@\n", entry.actionType, [entry statusIcon]];
    if (entry.reasoning.length) {
        detail = [detail stringByAppendingFormat:@"原因: %@\n", entry.reasoning];
    }
    if (entry.output.length) {
        detail = [detail stringByAppendingFormat:@"输出: %@\n", entry.output];
    }
    if (entry.error.length) {
        detail = [detail stringByAppendingFormat:@"错误: %@\n", entry.error];
    }
    
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:[NSString stringWithFormat:@"步骤 %ld", (long)entry.iteration]
                                                                   message:detail
                                                            preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"确定" style:UIAlertActionStyleDefault handler:nil]];
    [self presentViewController:alert animated:YES completion:nil];
}

#pragma mark - Detect Running Task (断线重连恢复)

- (void)webSocketService:(WebSocketService *)service didDetectRunningTask:(NSString *)taskId {
    dispatch_async(dispatch_get_main_queue(), ^{
        ConversationManager *manager = [ConversationManager sharedManager];
        Conversation *currentConv = manager.currentConversation;
        if (currentConv && taskId) {
            // 创建恢复占位消息
            self.currentAssistantMessage = [Message assistantMessage];
            self.currentAssistantMessage.content = @"🔄 检测到任务正在运行，正在恢复...\n";
            [currentConv.messages addObject:self.currentAssistantMessage];
            [self.tableView reloadData];
            [self scrollToBottom];
            self.inputView.loading = YES;
            
            // 显示 Agent Live 面板
            [self showAgentLiveView];
            self.agentLiveView.taskProgress = [TaskProgress progressWithTaskId:taskId description:@"恢复中..."];
            self.agentLiveView.taskProgress.isRunning = YES;
            [self updateAgentLiveViewHeight];
            
            // 发送恢复请求
            [[WebSocketService sharedService] resumeTask:currentConv.conversationId];
        }
    });
}

#pragma mark - MessageCellDelegate

- (void)messageCell:(MessageCell *)cell didTapImage:(UIImage *)image {
    ImageZoomViewController *zoomVC = [[ImageZoomViewController alloc] initWithImage:image];
    [self presentViewController:zoomVC animated:YES completion:nil];
}

- (void)messageCellDidToggleThinking:(MessageCell *)cell {
    NSIndexPath *indexPath = [self.tableView indexPathForCell:cell];
    if (indexPath) {
        [UIView performWithoutAnimation:^{
            [self.tableView reloadRowsAtIndexPaths:@[indexPath] withRowAnimation:UITableViewRowAnimationNone];
        }];
    }
}

#pragma mark - LLM Status (Chat Progress)

- (void)webSocketService:(WebSocketService *)service didReceiveLLMStatus:(NSDictionary *)status {
    dispatch_async(dispatch_get_main_queue(), ^{
        NSString *type = status[@"type"];
        
        if ([type isEqualToString:@"llm_request_start"]) {
            // LLM 请求开始 - 显示加载指示器
            NSString *provider = status[@"provider"] ?: @"";
            NSString *model = status[@"model"] ?: @"";
            NSString *statusText = [NSString stringWithFormat:@"正在请求 %@/%@...", provider, model];
            
            [self.statusIndicator startAnimating];
            self.statusLabel.text = statusText;
            self.statusLabel.textColor = TechTheme.neonCyan;
        }
        else if ([type isEqualToString:@"llm_request_end"]) {
            // LLM 请求结束 - 停止加载指示器
            [self.statusIndicator stopAnimating];
            
            NSNumber *latency = status[@"latency_ms"];
            NSDictionary *usage = status[@"usage"];
            NSNumber *totalTokens = usage[@"total_tokens"];
            
            if (latency && totalTokens) {
                NSString *statusText = [NSString stringWithFormat:@"响应: %@ms, %@ tokens", latency, totalTokens];
                self.statusLabel.text = statusText;
                self.statusLabel.textColor = TechTheme.textSecondary;
                
                // 3秒后恢复默认状态
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(3.0 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
                    if (![self.statusIndicator isAnimating]) {
                        self.statusLabel.text = @"";
                    }
                });
            } else {
                self.statusLabel.text = @"";
            }
        }
    });
}

- (void)dealloc {
    [[NSNotificationCenter defaultCenter] removeObserver:self];
}

@end
