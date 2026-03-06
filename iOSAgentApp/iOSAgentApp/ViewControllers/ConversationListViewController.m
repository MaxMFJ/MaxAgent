#import "ConversationListViewController.h"
#import "ConversationManager.h"
#import "TechTheme.h"

@interface ConversationListViewController () <UITableViewDataSource, UITableViewDelegate>

@property (nonatomic, strong) UITableView *tableView;
@property (nonatomic, strong) NSMutableArray<Conversation *> *conversations;

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
    [_tableView registerClass:[UITableViewCell class] forCellReuseIdentifier:@"ConversationCell"];
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

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    return self.conversations.count;
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    UITableViewCell *cell = [tableView dequeueReusableCellWithIdentifier:@"ConversationCell" forIndexPath:indexPath];

    Conversation *conversation = self.conversations[indexPath.row];
    ConversationManager *manager = [ConversationManager sharedManager];
    BOOL isActive = [conversation.conversationId isEqualToString:manager.currentConversation.conversationId];

    // 重用时清理旧进度条
    cell.backgroundColor = isActive
        ? [TechTheme.neonCyan colorWithAlphaComponent:0.07]
        : [UIColor clearColor];
    cell.selectedBackgroundView = [[UIView alloc] init];
    cell.selectedBackgroundView.backgroundColor = [TechTheme.neonCyan colorWithAlphaComponent:0.12];

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

    return cell;
}

- (BOOL)tableView:(UITableView *)tableView canEditRowAtIndexPath:(NSIndexPath *)indexPath {
    return YES;
}

- (void)tableView:(UITableView *)tableView commitEditingStyle:(UITableViewCellEditingStyle)editingStyle forRowAtIndexPath:(NSIndexPath *)indexPath {
    if (editingStyle == UITableViewCellEditingStyleDelete) {
        Conversation *conversation = self.conversations[indexPath.row];
        
        ConversationManager *manager = [ConversationManager sharedManager];
        [manager deleteConversation:conversation];
        
        [tableView deleteRowsAtIndexPaths:@[indexPath] withRowAnimation:UITableViewRowAnimationFade];
        
        if ([self.delegate respondsToSelector:@selector(didDeleteConversation:)]) {
            [self.delegate didDeleteConversation:conversation];
        }
    }
}

#pragma mark - UITableViewDelegate

- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    
    Conversation *conversation = self.conversations[indexPath.row];
    
    ConversationManager *manager = [ConversationManager sharedManager];
    [manager selectConversation:conversation];
    
    if ([self.delegate respondsToSelector:@selector(didSelectConversation:)]) {
        [self.delegate didSelectConversation:conversation];
    }
    
    [self dismiss];
}

- (UISwipeActionsConfiguration *)tableView:(UITableView *)tableView trailingSwipeActionsConfigurationForRowAtIndexPath:(NSIndexPath *)indexPath {
    UIContextualAction *deleteAction = [UIContextualAction contextualActionWithStyle:UIContextualActionStyleDestructive
                                                                               title:NSLocalizedString(@"delete", nil)
                                                                             handler:^(UIContextualAction *action, UIView *sourceView, void (^completionHandler)(BOOL)) {
        Conversation *conversation = self.conversations[indexPath.row];
        ConversationManager *manager = [ConversationManager sharedManager];
        [manager deleteConversation:conversation];
        
        [tableView deleteRowsAtIndexPaths:@[indexPath] withRowAnimation:UITableViewRowAnimationFade];
        
        if ([self.delegate respondsToSelector:@selector(didDeleteConversation:)]) {
            [self.delegate didDeleteConversation:conversation];
        }
        
        completionHandler(YES);
    }];
    
    deleteAction.image = [UIImage systemImageNamed:@"trash"];
    
    return [UISwipeActionsConfiguration configurationWithActions:@[deleteAction]];
}

@end
