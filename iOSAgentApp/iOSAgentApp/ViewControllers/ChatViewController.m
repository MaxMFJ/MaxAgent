#import "ChatViewController.h"
#import "SettingsViewController.h"
#import "ConversationListViewController.h"
#import "WebSocketService.h"
#import "ServerConfig.h"
#import "Message.h"
#import "MessageCell.h"
#import "InputView.h"
#import "ImageZoomViewController.h"
#import "ConversationManager.h"
#import "TTSService.h"
#import "VoiceInputService.h"

@interface ChatViewController () <UITableViewDataSource, UITableViewDelegate, WebSocketServiceDelegate, InputViewDelegate, MessageCellDelegate, ConversationListDelegate>

@property (nonatomic, strong) UITableView *tableView;
@property (nonatomic, strong) InputView *inputView;
@property (nonatomic, strong) UIView *statusBar;
@property (nonatomic, strong) UILabel *statusLabel;
@property (nonatomic, strong) UIActivityIndicatorView *statusIndicator;

@property (nonatomic, strong, nullable) Message *currentAssistantMessage;
@property (nonatomic, strong) NSLayoutConstraint *inputViewBottomConstraint;
@property (nonatomic, strong, nullable) NSTimer *autonomousTimeoutTimer;

@end

@implementation ChatViewController

static NSString * const kUserDefaultsTTSEnabled = @"ttsEnabled";

- (void)viewDidLoad {
    [super viewDidLoad];
    
    self.view.backgroundColor = [UIColor systemBackgroundColor];
    
    [self setupNavigationBar];
    [self setupUI];
    [self setupKeyboardObservers];
    [self setupWebSocket];
    [self setupVoiceInput];
    [self updateTitle];
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
            [wself.inputView setText:@""];
            if (text.length > 0) {
                [wself inputView:wself.inputView didSendMessage:text];
            }
        });
    };
}

- (void)updateTitle {
    ConversationManager *manager = [ConversationManager sharedManager];
    if (manager.currentConversation) {
        self.title = manager.currentConversation.title;
    } else {
        self.title = NSLocalizedString(@"app_title", nil);
    }
}

- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];
    
    if ([ServerConfig sharedConfig].serverURL.length == 0) {
        [self showSettings];
    } else {
        [[WebSocketService sharedService] connect];
    }
}

#pragma mark - Setup

- (void)setupNavigationBar {
    UIBarButtonItem *newChatButton = [[UIBarButtonItem alloc] initWithImage:[UIImage systemImageNamed:@"square.and.pencil"] style:UIBarButtonItemStylePlain target:self action:@selector(createNewConversation)];
    
    UIBarButtonItem *settingsButton = [[UIBarButtonItem alloc] initWithImage:[UIImage systemImageNamed:@"gear"] style:UIBarButtonItemStylePlain target:self action:@selector(showSettings)];
    
    self.navigationItem.rightBarButtonItems = @[settingsButton, newChatButton];
    
    UIBarButtonItem *conversationsButton = [[UIBarButtonItem alloc] initWithImage:[UIImage systemImageNamed:@"text.bubble"] style:UIBarButtonItemStylePlain target:self action:@selector(showConversationList)];
    
    UIBarButtonItem *clearButton = [[UIBarButtonItem alloc] initWithImage:[UIImage systemImageNamed:@"trash"] style:UIBarButtonItemStylePlain target:self action:@selector(clearChat)];
    
    self.navigationItem.leftBarButtonItems = @[conversationsButton, clearButton];
}

- (void)setupUI {
    _statusBar = [[UIView alloc] init];
    _statusBar.translatesAutoresizingMaskIntoConstraints = NO;
    _statusBar.backgroundColor = [UIColor systemRedColor];
    [self.view addSubview:_statusBar];
    
    _statusIndicator = [[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleMedium];
    _statusIndicator.translatesAutoresizingMaskIntoConstraints = NO;
    _statusIndicator.color = [UIColor whiteColor];
    [_statusBar addSubview:_statusIndicator];
    
    _statusLabel = [[UILabel alloc] init];
    _statusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _statusLabel.font = [UIFont systemFontOfSize:12 weight:UIFontWeightMedium];
    _statusLabel.textColor = [UIColor whiteColor];
    _statusLabel.text = NSLocalizedString(@"status_disconnected", nil);
    [_statusBar addSubview:_statusLabel];
    
    _tableView = [[UITableView alloc] initWithFrame:CGRectZero style:UITableViewStylePlain];
    _tableView.translatesAutoresizingMaskIntoConstraints = NO;
    _tableView.dataSource = self;
    _tableView.delegate = self;
    _tableView.separatorStyle = UITableViewCellSeparatorStyleNone;
    _tableView.backgroundColor = [UIColor systemBackgroundColor];
    _tableView.keyboardDismissMode = UIScrollViewKeyboardDismissModeInteractive;
    [_tableView registerClass:[MessageCell class] forCellReuseIdentifier:@"MessageCell"];
    [self.view addSubview:_tableView];
    
    _inputView = [[InputView alloc] init];
    _inputView.translatesAutoresizingMaskIntoConstraints = NO;
    _inputView.delegate = self;
    [self.view addSubview:_inputView];
    
    _inputViewBottomConstraint = [_inputView.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor];
    
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
        [_tableView.bottomAnchor constraintEqualToAnchor:_inputView.topAnchor],
        
        [_inputView.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [_inputView.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        _inputViewBottomConstraint
    ]];
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
    NSMutableArray<Message *> *messages = [self currentMessages];
    if (messages.count > 0) {
        NSIndexPath *lastIndexPath = [NSIndexPath indexPathForRow:messages.count - 1 inSection:0];
        [self.tableView scrollToRowAtIndexPath:lastIndexPath atScrollPosition:UITableViewScrollPositionBottom animated:YES];
    }
}

- (void)updateStatusBar:(WebSocketConnectionState)state {
    dispatch_async(dispatch_get_main_queue(), ^{
        switch (state) {
            case WebSocketConnectionStateDisconnected:
                self.statusBar.backgroundColor = [UIColor systemRedColor];
                self.statusLabel.text = NSLocalizedString(@"status_disconnected", nil);
                [self.statusIndicator stopAnimating];
                self.inputView.enabled = NO;
                break;
            case WebSocketConnectionStateConnecting:
                self.statusBar.backgroundColor = [UIColor systemOrangeColor];
                self.statusLabel.text = NSLocalizedString(@"status_connecting", nil);
                [self.statusIndicator startAnimating];
                self.inputView.enabled = NO;
                break;
            case WebSocketConnectionStateConnected:
                self.statusBar.backgroundColor = [UIColor systemGreenColor];
                self.statusLabel.text = NSLocalizedString(@"status_connected", nil);
                [self.statusIndicator stopAnimating];
                self.inputView.enabled = YES;
                break;
            case WebSocketConnectionStateReconnecting:
                self.statusBar.backgroundColor = [UIColor systemOrangeColor];
                self.statusLabel.text = NSLocalizedString(@"status_reconnecting", nil);
                [self.statusIndicator startAnimating];
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
    MessageCell *cell = [tableView dequeueReusableCellWithIdentifier:@"MessageCell" forIndexPath:indexPath];
    NSMutableArray<Message *> *messages = [self currentMessages];
    if (indexPath.row < (NSInteger)messages.count) {
        Message *message = messages[indexPath.row];
        cell.delegate = self;
        [cell configureWithMessage:message];
    }
    return cell;
}

#pragma mark - UITableViewDelegate

- (CGFloat)tableView:(UITableView *)tableView estimatedHeightForRowAtIndexPath:(NSIndexPath *)indexPath {
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
    [[WebSocketService sharedService] sendChatMessage:message sessionId:currentConv.conversationId];
}

- (void)inputViewDidRequestVoiceInput:(InputView *)inputView {
    (void)inputView;
    VoiceInputService *voice = [VoiceInputService sharedService];
    if (voice.isRecording) {
        NSString *committed = [voice commitCurrentText];
        self.inputView.voiceInputActive = NO;
        [self.inputView setText:@""];
        if (committed.length > 0) {
            [self inputView:self.inputView didSendMessage:committed];
        }
    } else {
        [voice startRecording];
        self.inputView.voiceInputActive = YES;
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

- (void)webSocketService:(WebSocketService *)service didConnectWithClientId:(NSString *)clientId sessionId:(NSString *)sessionId hasRunningTask:(BOOL)hasRunningTask runningTaskId:(NSString *)runningTaskId hasRunningChat:(BOOL)hasRunningChat {
    NSLog(@"Connected: client=%@, session=%@, running_task=%d, running_chat=%d", 
          clientId, sessionId, hasRunningTask, hasRunningChat);
    
    if (hasRunningChat) {
        dispatch_async(dispatch_get_main_queue(), ^{
            ConversationManager *manager = [ConversationManager sharedManager];
            if (manager.currentConversation && 
                [manager.currentConversation.conversationId isEqualToString:sessionId]) {
                [[WebSocketService sharedService] resumeChat:sessionId];
            }
        });
    }
}

- (void)webSocketService:(WebSocketService *)service didReceiveContent:(NSString *)content {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.currentAssistantMessage) {
            [self.currentAssistantMessage appendContent:content];
            if ([[NSUserDefaults standardUserDefaults] boolForKey:kUserDefaultsTTSEnabled]) {
                NSString *full = self.currentAssistantMessage.content ?: @"";
                [[TTSService sharedService] appendAndSpeakStreamedContent:full];
            }
            NSMutableArray<Message *> *messages = [self currentMessages];
            NSInteger index = [messages indexOfObject:self.currentAssistantMessage];
            if (index != NSNotFound) {
                NSIndexPath *indexPath = [NSIndexPath indexPathForRow:index inSection:0];
                [self.tableView reloadRowsAtIndexPaths:@[indexPath] withRowAnimation:UITableViewRowAnimationNone];
            }
        }
    });
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
        self.inputView.loading = NO;
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

- (void)webSocketService:(WebSocketService *)service didReceiveError:(NSString *)errorMessage {
    dispatch_async(dispatch_get_main_queue(), ^{
        [self cancelAutonomousTimeout];
        self.inputView.loading = NO;
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

- (void)webSocketService:(WebSocketService *)service didResumeChatWithId:(NSString *)taskId bufferedCount:(NSInteger)bufferedCount {
    dispatch_async(dispatch_get_main_queue(), ^{
        NSLog(@"[Chat] Resume chat successful: task=%@, buffered=%ld", taskId, (long)bufferedCount);
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
        if ([type isEqualToString:@"model_selected"]) {
            NSString *modelType = chunk[@"model_type"] ?: @"";
            NSString *reason = chunk[@"reason"] ?: @"";
            NSString *icon = [modelType isEqualToString:@"local"] ? @"🏠" : @"☁️";
            NSString *name = [modelType isEqualToString:@"local"] ? NSLocalizedString(@"model_local", nil) : NSLocalizedString(@"model_remote", nil);
            [append appendFormat:@"%@ 选择模型: %@\n", icon, name];
            if (reason.length) [append appendFormat:@"💡 %@\n\n", reason];
        } else if ([type isEqualToString:@"task_start"]) {
            [append appendString:@"🚀 任务开始执行...\n"];
        } else if ([type isEqualToString:@"action_plan"]) {
            NSDictionary *action = chunk[@"action"];
            NSString *actionType = ([action isKindOfClass:[NSDictionary class]] ? action[@"action_type"] : nil) ?: @"unknown";
            NSString *reasoning = ([action isKindOfClass:[NSDictionary class]] ? action[@"reasoning"] : nil) ?: @"";
            NSNumber *iter = chunk[@"iteration"];
            [append appendFormat:@"\n📋 步骤 %@: %@\n   → %@\n", iter ? iter.stringValue : @"?", actionType, reasoning];
        } else if ([type isEqualToString:@"action_executing"]) {
            NSString *actionType = chunk[@"action_type"] ?: @"";
            [append appendFormat:@"⏳ 执行中: %@\n", actionType];
        } else if ([type isEqualToString:@"action_result"]) {
            id succ = chunk[@"success"];
            BOOL success = ([succ isKindOfClass:[NSNumber class]] ? [succ boolValue] : NO);
            NSString *output = chunk[@"output"] ?: @"";
            NSString *err = chunk[@"error"] ?: @"";
            if (success && output.length) [append appendFormat:@"   ✓ %@\n", output];
            else if (err.length) [append appendFormat:@"   ✗ %@\n", err];
        } else if ([type isEqualToString:@"reflect_start"]) {
            [append appendString:@"\n🔄 反思中...\n"];
        } else if ([type isEqualToString:@"reflect_result"]) {
            NSString *ref = chunk[@"reflection"] ?: chunk[@"error"] ?: @"";
            if (ref.length) [append appendFormat:@"   %@\n", ref];
        } else if ([type isEqualToString:@"task_complete"]) {
            id succ = chunk[@"success"];
            BOOL success = ([succ isKindOfClass:[NSNumber class]] ? [succ boolValue] : NO);
            NSString *summary = chunk[@"summary"] ?: @"";
            [append appendFormat:@"\n%@ 任务完成\n%@\n", success ? @"✅" : @"⚠️", summary];
        } else if ([type isEqualToString:@"task_stopped"]) {
            [append appendFormat:@"\n⏹ %@\n", chunk[@"message"] ?: chunk[@"reason"] ?: NSLocalizedString(@"autonomous_stopped", nil)];
        } else if ([type isEqualToString:@"progress_update"]) {
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
        }
    });
}

#pragma mark - MessageCellDelegate

- (void)messageCell:(MessageCell *)cell didTapImage:(UIImage *)image {
    ImageZoomViewController *zoomVC = [[ImageZoomViewController alloc] initWithImage:image];
    [self presentViewController:zoomVC animated:YES completion:nil];
}

- (void)dealloc {
    [[NSNotificationCenter defaultCenter] removeObserver:self];
}

@end
