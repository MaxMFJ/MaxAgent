#import "ConversationListViewController.h"
#import "ConversationManager.h"

@interface ConversationListViewController () <UITableViewDataSource, UITableViewDelegate>

@property (nonatomic, strong) UITableView *tableView;
@property (nonatomic, strong) NSMutableArray<Conversation *> *conversations;

@end

@implementation ConversationListViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    
    self.title = NSLocalizedString(@"conversations", nil);
    self.view.backgroundColor = [UIColor systemBackgroundColor];
    
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
    [_tableView registerClass:[UITableViewCell class] forCellReuseIdentifier:@"ConversationCell"];
    _tableView.rowHeight = 60;
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
    
    if (!cell) {
        cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:@"ConversationCell"];
    }
    
    Conversation *conversation = self.conversations[indexPath.row];
    ConversationManager *manager = [ConversationManager sharedManager];
    
    cell.textLabel.text = conversation.title;
    
    NSDateFormatter *formatter = [[NSDateFormatter alloc] init];
    formatter.dateStyle = NSDateFormatterShortStyle;
    formatter.timeStyle = NSDateFormatterShortStyle;
    
    NSString *messageCount = [NSString stringWithFormat:@"%lu %@", (unsigned long)conversation.messages.count, NSLocalizedString(@"messages", @"messages")];
    NSString *timeStr = [formatter stringFromDate:conversation.updatedAt];
    cell.detailTextLabel.text = [NSString stringWithFormat:@"%@ · %@", messageCount, timeStr];
    cell.detailTextLabel.textColor = [UIColor secondaryLabelColor];
    
    if ([conversation.conversationId isEqualToString:manager.currentConversation.conversationId]) {
        cell.accessoryType = UITableViewCellAccessoryCheckmark;
        cell.textLabel.font = [UIFont boldSystemFontOfSize:17];
    } else {
        cell.accessoryType = UITableViewCellAccessoryNone;
        cell.textLabel.font = [UIFont systemFontOfSize:17];
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
