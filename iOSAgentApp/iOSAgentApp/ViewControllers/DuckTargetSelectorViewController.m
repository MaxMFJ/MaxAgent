#import "DuckTargetSelectorViewController.h"
#import "Duck.h"
#import "DuckApiService.h"
#import "TechTheme.h"

@interface DuckTargetSelectorViewController ()

@property (nonatomic, strong) NSArray<Duck *> *ducks;
@property (nonatomic, assign) BOOL loading;

@end

@implementation DuckTargetSelectorViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = @"选择对话对象";
    self.view.backgroundColor = TechTheme.backgroundPrimary;
    self.tableView.backgroundColor = [UIColor clearColor];
    self.tableView.separatorColor = [TechTheme.neonCyan colorWithAlphaComponent:0.3];
    
    self.navigationItem.leftBarButtonItem = [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemCancel target:self action:@selector(cancelTapped)];
    
    _ducks = @[];
    _loading = YES;
    [self fetchDucks];
}

- (void)fetchDucks {
    __weak typeof(self) wself = self;
    [[DuckApiService sharedService] fetchDuckListWithCompletion:^(NSArray<Duck *> * _Nullable ducks, NSError * _Nullable error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            __strong typeof(wself) self = wself;
            if (!self) return;
            self.loading = NO;
            if (error) {
                NSLog(@"[DuckTarget] Fetch error: %@", error);
                self.ducks = @[];
            } else {
                self.ducks = ducks ?: @[];
            }
            [self.tableView reloadData];
        });
    }];
}

- (void)cancelTapped {
    [self dismissViewControllerAnimated:YES completion:nil];
}

#pragma mark - Table view data source

- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView {
    return 2;
}

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    if (section == 0) return 1;
    if (self.loading) return 1;
    return self.ducks.count > 0 ? self.ducks.count : 1;
}

- (NSString *)tableView:(UITableView *)tableView titleForHeaderInSection:(NSInteger)section {
    if (section == 0) return @"主 Agent";
    return @"子 Duck";
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    static NSString *cellId = @"Cell";
    UITableViewCell *cell = [tableView dequeueReusableCellWithIdentifier:cellId];
    if (!cell) {
        cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:cellId];
        cell.backgroundColor = [TechTheme.backgroundSecondary colorWithAlphaComponent:0.6];
        cell.textLabel.textColor = TechTheme.textPrimary;
        cell.detailTextLabel.textColor = TechTheme.textSecondary;
    }
    
    if (indexPath.section == 0) {
        cell.textLabel.text = @"主 Agent";
        cell.detailTextLabel.text = @"与主 Agent 对话";
        cell.imageView.image = [UIImage systemImageNamed:@"brain.head.profile"];
        cell.imageView.tintColor = TechTheme.neonCyan;
    } else {
        if (self.loading) {
            cell.textLabel.text = @"加载中...";
            cell.detailTextLabel.text = nil;
            cell.imageView.image = nil;
        } else if (self.ducks.count == 0) {
            cell.textLabel.text = @"暂无在线 Duck";
            cell.detailTextLabel.text = @"请先在 Mac 端启动子 Duck";
            cell.imageView.image = nil;
        } else {
            Duck *duck = self.ducks[indexPath.row];
            cell.textLabel.text = duck.name;
            NSString *status = [duck.status isEqualToString:@"online"] ? @"🟢 在线" :
                               ([duck.status isEqualToString:@"busy"] ? @"🟡 忙碌" : @"🔴 离线");
            cell.detailTextLabel.text = [NSString stringWithFormat:@"%@ · %@%@", duck.duckType, status, duck.isLocal ? @" · 本地" : @""];
            cell.imageView.image = [UIImage systemImageNamed:@"bird"];
            cell.imageView.tintColor = TechTheme.neonGreen;
        }
    }
    
    return cell;
}

- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    
    if (indexPath.section == 0) {
        [self.delegate duckTargetSelectorDidSelectMain];
        [self dismissViewControllerAnimated:YES completion:nil];
        return;
    }
    
    if (self.loading || self.ducks.count == 0) return;
    
    Duck *duck = self.ducks[indexPath.row];
    if ([duck.status isEqualToString:@"offline"]) {
        UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"Duck 已离线"
                                                                       message:@"请选择其他 Duck 或主 Agent"
                                                                preferredStyle:UIAlertControllerStyleAlert];
        [alert addAction:[UIAlertAction actionWithTitle:@"确定" style:UIAlertActionStyleDefault handler:nil]];
        [self presentViewController:alert animated:YES completion:nil];
        return;
    }
    
    [self.delegate duckTargetSelectorDidSelectDuck:duck];
    [self dismissViewControllerAnimated:YES completion:nil];
}

@end
