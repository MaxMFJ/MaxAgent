#import "ConversationListViewController.h"
#import "ConversationManager.h"
#import "TechTheme.h"

@interface ConversationListViewController () <UITableViewDataSource, UITableViewDelegate>

@property (nonatomic, strong) UITableView *tableView;
@property (nonatomic, strong) NSMutableArray<Conversation *> *conversations;
@property (nonatomic, strong) NSMutableArray<GroupChat *> *mutableGroupChats;

@end

@implementation ConversationListViewController

- (void)viewDidLoad {
    [super viewDidLoad];

    self.title = NSLocalizedString(@"conversations", nil);
    self.view.backgroundColor = TechTheme.backgroundPrimary;

    // 导航栏深色科技风格
    if (@available(iOS 13.0, *)) {
        UINavigationBarAppearance *appearance = [[UINavigationBarAppearance alloc] init];
        [appearance configureWithTransparentBackground];
        appearance.backgroundColor = [TechTheme.backgroundSecondary colorWithAlphaComponent:0.92];
        appearance.titleTextAttributes = @{
            NSForegroundColorAttributeName: TechTheme.neonCyan,
            NSFontAttributeName: [TechTheme fontDisplaySize:16 weight:UIFontWeightSemibold]
        };
        self.navigationController.navigationBar.standardAppearance = appearance;
        self.navigationController.navigationBar.scrollEdgeAppearance = appearance;
        self.navigationController.navigationBar.tintColor = TechTheme.neonCyan;
    }

    ConversationManager *manager = [ConversationManager sharedManager];
    self.conversations = manager.conversations;
    self.mutableGroupChats = [NSMutableArray arrayWithArray:self.groupChats ?: @[]];

    [self setupNavigationBar];
    [self setupTableView];
}

- (void)setupNavigationBar {
    UIBarButtonItem *closeButton = [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemDone target:self action:@selector(dismiss)];
    self.navigationItem.leftBarButtonItem = closeButton;
    
    UIBarButtonItem *newButton = [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemAdd target:self action:@selector(createNewConversation)];
    self.navigationItem.rightBarButtonItem = newButton;
}

- (void)setupTableView {
    _tableView = [[UITableView alloc] initWithFrame:self.view.bounds style:UITableViewStylePlain];
    _tableView.dataSource = self;
    _tableView.delegate = self;
    _tableView.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    _tableView.backgroundColor = [UIColor clearColor];
    _tableView.separatorStyle = UITableViewCellSeparatorStyleSingleLine;
    _tableView.separatorColor = [TechTheme.neonCyan colorWithAlphaComponent:0.1];
    // 这里不注册 class，避免拿到默认 style=default 的 cell（detailTextLabel 为 nil）
    _tableView.rowHeight = 64;
    [self.view addSubview:_tableView];
}

- (void)dismiss {
    [self dismissViewControllerAnimated:YES completion:nil];
}

- (void)createNewConversation {
    ConversationManager *manager = [ConversationManager sharedManager];
    Conversation *newConv = [manager createNewConversation];
    
    [self.tableView reloadData];
    
    if ([self.delegate respondsToSelector:@selector(didSelectConversation:)]) {
        [self.delegate didSelectConversation:newConv];
    }
    
    [self dismiss];
}

#pragma mark - UITableViewDataSource

- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView {
    // section 0: 普通对话；section 1: 群聊（如有）
    return self.mutableGroupChats.count > 0 ? 2 : 1;
}

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    if (section == 0) return self.conversations.count;
    return self.mutableGroupChats.count;
}

- (NSString *)tableView:(UITableView *)tableView titleForHeaderInSection:(NSInteger)section {
    if (section == 0) return NSLocalizedString(@"conversations", nil);
    return NSLocalizedString(@"group_chats", nil);
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    static NSString * const kCellId = @"ConversationCellSubtitle";
    UITableViewCell *cell = [tableView dequeueReusableCellWithIdentifier:kCellId];
    if (!cell) {
        cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:kCellId];
    }

    cell.selectedBackgroundView = [[UIView alloc] init];
    cell.selectedBackgroundView.backgroundColor = [TechTheme.neonCyan colorWithAlphaComponent:0.12];

    if (indexPath.section == 0) {
        Conversation *conversation = self.conversations[indexPath.row];
        ConversationManager *manager = [ConversationManager sharedManager];
        BOOL isActive = [conversation.conversationId isEqualToString:manager.currentConversation.conversationId];

        cell.backgroundColor = isActive
            ? [TechTheme.neonCyan colorWithAlphaComponent:0.07]
            : [UIColor clearColor];

        cell.textLabel.text = conversation.title;
        cell.textLabel.textColor = isActive ? TechTheme.neonCyan : TechTheme.textPrimary;
        cell.textLabel.font = [TechTheme fontBodySize:14 weight:isActive ? UIFontWeightSemibold : UIFontWeightRegular];

        NSDateFormatter *formatter = [[NSDateFormatter alloc] init];
        formatter.dateStyle = NSDateFormatterShortStyle;
        formatter.timeStyle = NSDateFormatterShortStyle;
        NSString *messageCount = [NSString stringWithFormat:@"%lu msgs", (unsigned long)conversation.messages.count];
        NSString *timeStr = [formatter stringFromDate:conversation.updatedAt];
        cell.detailTextLabel.text = [NSString stringWithFormat:@"%@ · %@", messageCount, timeStr];
        cell.detailTextLabel.textColor = isActive ? [TechTheme.neonCyan colorWithAlphaComponent:0.6] : TechTheme.textDim;
        cell.detailTextLabel.font = [TechTheme fontMonoSize:11 weight:UIFontWeightRegular];

        if (isActive) {
            UIImage *checkImg = [UIImage systemImageNamed:@"checkmark.circle.fill"];
            UIImageView *check = [[UIImageView alloc] initWithImage:checkImg];
            check.tintColor = TechTheme.neonCyan;
            check.frame = CGRectMake(0, 0, 20, 20);
            cell.accessoryView = check;
        } else {
            cell.accessoryView = nil;
            cell.accessoryType = UITableViewCellAccessoryNone;
        }
    } else {
        GroupChat *g = self.mutableGroupChats[indexPath.row];
        BOOL isActive = NO;
        if (self.delegate && [self.delegate respondsToSelector:@selector(didSelectGroupChat:)]) {
            // 不追踪“当前活跃群聊”，只做样式统一（不加 check）
            isActive = NO;
        }

        cell.backgroundColor = isActive
            ? [TechTheme.neonPurple colorWithAlphaComponent:0.08]
            : [UIColor clearColor];

        cell.textLabel.text = g.title.length > 0 ? g.title : @"协作群聊";
        cell.textLabel.textColor = TechTheme.neonPurple;
        cell.textLabel.font = [TechTheme fontBodySize:14 weight:UIFontWeightSemibold];

        NSInteger total = g.taskSummary.total;
        NSInteger done = g.taskSummary.completed + g.taskSummary.failed;
        NSString *status = [GroupChat stringFromStatus:g.status] ?: @"active";
        cell.detailTextLabel.text = [NSString stringWithFormat:@"#%@ · %@ · %ld/%ld", g.groupId ?: @"", status, (long)done, (long)total];
        cell.detailTextLabel.textColor = TechTheme.textDim;
        cell.detailTextLabel.font = [TechTheme fontMonoSize:11 weight:UIFontWeightRegular];

        UIImage *icon = [UIImage systemImageNamed:@"person.3.fill"];
        UIImageView *iv = [[UIImageView alloc] initWithImage:icon];
        iv.tintColor = [TechTheme.neonPurple colorWithAlphaComponent:0.9];
        cell.accessoryView = iv;
    }

    return cell;
}

- (BOOL)tableView:(UITableView *)tableView canEditRowAtIndexPath:(NSIndexPath *)indexPath {
    return YES;
}

- (void)tableView:(UITableView *)tableView commitEditingStyle:(UITableViewCellEditingStyle)editingStyle forRowAtIndexPath:(NSIndexPath *)indexPath {
    if (editingStyle == UITableViewCellEditingStyleDelete) {
        if (indexPath.section == 0) {
            Conversation *conversation = self.conversations[indexPath.row];

            ConversationManager *manager = [ConversationManager sharedManager];
            [manager deleteConversation:conversation];

            [tableView deleteRowsAtIndexPaths:@[indexPath] withRowAnimation:UITableViewRowAnimationFade];

            if ([self.delegate respondsToSelector:@selector(didDeleteConversation:)]) {
                [self.delegate didDeleteConversation:conversation];
            }
        } else {
            GroupChat *g = self.mutableGroupChats[indexPath.row];
            [self.mutableGroupChats removeObjectAtIndex:indexPath.row];
            [tableView deleteRowsAtIndexPaths:@[indexPath] withRowAnimation:UITableViewRowAnimationFade];

            if (self.mutableGroupChats.count == 0) {
                // 删除最后一个群聊后，移除 section
                [tableView reloadData];
            }

            if ([self.delegate respondsToSelector:@selector(didDeleteGroupChat:)]) {
                [self.delegate didDeleteGroupChat:g];
            }
        }
    }
}

#pragma mark - UITableViewDelegate

- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    
    if (indexPath.section == 0) {
        Conversation *conversation = self.conversations[indexPath.row];

        ConversationManager *manager = [ConversationManager sharedManager];
        [manager selectConversation:conversation];

        if ([self.delegate respondsToSelector:@selector(didSelectConversation:)]) {
            [self.delegate didSelectConversation:conversation];
        }
        [self dismiss];
    } else {
        GroupChat *g = self.mutableGroupChats[indexPath.row];
        if ([self.delegate respondsToSelector:@selector(didSelectGroupChat:)]) {
            [self.delegate didSelectGroupChat:g];
        }
        [self dismiss];
    }
}

- (UISwipeActionsConfiguration *)tableView:(UITableView *)tableView trailingSwipeActionsConfigurationForRowAtIndexPath:(NSIndexPath *)indexPath {
    UIContextualAction *deleteAction = [UIContextualAction contextualActionWithStyle:UIContextualActionStyleDestructive
                                                                               title:NSLocalizedString(@"delete", nil)
                                                                             handler:^(UIContextualAction *action, UIView *sourceView, void (^completionHandler)(BOOL)) {
        if (indexPath.section == 0) {
            Conversation *conversation = self.conversations[indexPath.row];
            ConversationManager *manager = [ConversationManager sharedManager];
            [manager deleteConversation:conversation];

            [tableView deleteRowsAtIndexPaths:@[indexPath] withRowAnimation:UITableViewRowAnimationFade];

            if ([self.delegate respondsToSelector:@selector(didDeleteConversation:)]) {
                [self.delegate didDeleteConversation:conversation];
            }
        } else {
            GroupChat *g = self.mutableGroupChats[indexPath.row];
            [self.mutableGroupChats removeObjectAtIndex:indexPath.row];
            [tableView deleteRowsAtIndexPaths:@[indexPath] withRowAnimation:UITableViewRowAnimationFade];
            if (self.mutableGroupChats.count == 0) {
                [tableView reloadData];
            }
            if ([self.delegate respondsToSelector:@selector(didDeleteGroupChat:)]) {
                [self.delegate didDeleteGroupChat:g];
            }
        }
        completionHandler(YES);
    }];
    
    deleteAction.image = [UIImage systemImageNamed:@"trash"];
    
    return [UISwipeActionsConfiguration configurationWithActions:@[deleteAction]];
}

@end
