#import "SettingsViewController.h"
#import "ServerConfig.h"
#import "WebSocketService.h"
#import <AVFoundation/AVFoundation.h>
#import "TechTheme.h"
#import "TTSService.h"

static NSString * const kUserDefaultsTTSEnabled = @"ttsEnabled";
static NSString * const kUserDefaultsSTTSilenceSeconds = @"sttSilenceSeconds";
static NSString * const kUserDefaultsSTTNoSpeechTimeoutSeconds = @"sttNoSpeechTimeoutSeconds";

typedef NS_ENUM(NSInteger, SettingsSection) {
    SettingsSectionServer = 0,
    SettingsSectionStatus,
    SettingsSectionVoice,
    SettingsSectionActions,
    SettingsSectionCount
};

@interface SettingsViewController () <UITextFieldDelegate>

@property (nonatomic, strong) UITextField *serverURLField;
@property (nonatomic, strong) UITextField *tokenField;
@property (nonatomic, strong) UILabel *connectionStatusLabel;
@property (nonatomic, strong) UILabel *modelLabel;
@property (nonatomic, assign) BOOL isConnected;
@property (nonatomic, copy, nullable) NSString *currentModel;
@property (nonatomic, strong) UISwitch *ttsSwitch;

@end

#pragma mark - QRScannerViewController (Forward Declaration)

@interface QRScannerViewController : UIViewController <AVCaptureMetadataOutputObjectsDelegate>

@property (nonatomic, strong) AVCaptureSession *captureSession;
@property (nonatomic, strong) AVCaptureVideoPreviewLayer *previewLayer;
@property (nonatomic, copy) void (^completionHandler)(NSString * _Nullable);

@end

@implementation SettingsViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    
    self.title = NSLocalizedString(@"settings", nil);
    self.tableView.backgroundColor = TechTheme.backgroundPrimary;
    self.tableView.separatorColor = [TechTheme.neonCyan colorWithAlphaComponent:0.12];

    // 导航栏深色科技风格
    if (@available(iOS 13.0, *)) {
        UINavigationBarAppearance *appearance = [[UINavigationBarAppearance alloc] init];
        [appearance configureWithTransparentBackground];
        appearance.backgroundColor = [TechTheme.backgroundSecondary colorWithAlphaComponent:0.92];
        appearance.titleTextAttributes = @{
            NSForegroundColorAttributeName: TechTheme.neonCyan,
            NSFontAttributeName: [UIFont monospacedSystemFontOfSize:16 weight:UIFontWeightSemibold]
        };
        self.navigationController.navigationBar.standardAppearance = appearance;
        self.navigationController.navigationBar.scrollEdgeAppearance = appearance;
        self.navigationController.navigationBar.tintColor = TechTheme.neonCyan;
    }
    
    UIBarButtonItem *doneButton = [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemDone target:self action:@selector(doneButtonTapped)];
    self.navigationItem.rightBarButtonItem = doneButton;
    
    UIBarButtonItem *scanButton = [[UIBarButtonItem alloc] initWithImage:[UIImage systemImageNamed:@"qrcode.viewfinder"] style:UIBarButtonItemStylePlain target:self action:@selector(scanQRCode)];
    self.navigationItem.leftBarButtonItem = scanButton;
    
    [self loadCurrentConfig];
}

- (void)viewWillAppear:(BOOL)animated {
    [super viewWillAppear:animated];
    [self checkServerStatus];
}

#pragma mark - Actions

- (void)doneButtonTapped {
    [self saveConfig];
    [self dismissViewControllerAnimated:YES completion:nil];
}

- (void)scanQRCode {
    AVAuthorizationStatus status = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo];
    
    if (status == AVAuthorizationStatusNotDetermined) {
        [AVCaptureDevice requestAccessForMediaType:AVMediaTypeVideo completionHandler:^(BOOL granted) {
            if (granted) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    [self presentQRScanner];
                });
            }
        }];
    } else if (status == AVAuthorizationStatusAuthorized) {
        [self presentQRScanner];
    } else {
        UIAlertController *alert = [UIAlertController alertControllerWithTitle:NSLocalizedString(@"camera_access", nil) message:NSLocalizedString(@"camera_access_message", nil) preferredStyle:UIAlertControllerStyleAlert];
        [alert addAction:[UIAlertAction actionWithTitle:NSLocalizedString(@"ok", nil) style:UIAlertActionStyleDefault handler:nil]];
        [self presentViewController:alert animated:YES completion:nil];
    }
}

- (void)presentQRScanner {
    QRScannerViewController *scanner = [[QRScannerViewController alloc] init];
    scanner.completionHandler = ^(NSString * _Nullable result) {
        if (result) {
            [self parseQRCodeResult:result];
        }
    };
    UINavigationController *nav = [[UINavigationController alloc] initWithRootViewController:scanner];
    [self presentViewController:nav animated:YES completion:nil];
}

- (void)parseQRCodeResult:(NSString *)result {
    NSData *data = [result dataUsingEncoding:NSUTF8StringEncoding];
    NSError *error;
    NSDictionary *json = [NSJSONSerialization JSONObjectWithData:data options:0 error:&error];
    
    if (json && [json isKindOfClass:[NSDictionary class]]) {
        NSString *url = json[@"url"];
        NSString *token = json[@"token"];
        
        if (url) {
            self.serverURLField.text = url;
        }
        if (token) {
            self.tokenField.text = token;
        }
        
        [self saveConfig];
        [self checkServerStatus];
    } else {
        if ([result hasPrefix:@"http://"] || [result hasPrefix:@"https://"] || 
            [result hasPrefix:@"ws://"] || [result hasPrefix:@"wss://"]) {
            self.serverURLField.text = result;
            [self saveConfig];
            [self checkServerStatus];
        }
    }
}

- (void)ttsSwitchChanged:(UISwitch *)sender {
    [[NSUserDefaults standardUserDefaults] setBool:sender.isOn forKey:kUserDefaultsTTSEnabled];
    [[NSUserDefaults standardUserDefaults] synchronize];
}

- (void)showVoicePicker {
    NSArray<AVSpeechSynthesisVoice *> *voices = [TTSService availableChineseVoices];
    AVSpeechSynthesisVoice *current = [TTSService sharedService].currentVoice;

    UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"选择朗读声音"
                                                                  message:@"选中的语音会立即试听"
                                                           preferredStyle:UIAlertControllerStyleActionSheet];

    // 自动选择选项
    UIAlertAction *autoAction = [UIAlertAction actionWithTitle:@"🔄 自动（最高质量）" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        [[TTSService sharedService] setPreferredVoiceWithIdentifier:nil];
        [self.tableView reloadData];
    }];
    [alert addAction:autoAction];

    for (AVSpeechSynthesisVoice *voice in voices) {
        NSString *qualityStr = @"普通";
        if ((NSInteger)voice.quality >= 2) qualityStr = @"增强";
        if ((NSInteger)voice.quality >= 3) qualityStr = @"优质";

        NSString *title = [NSString stringWithFormat:@"%@ [%@] %@", voice.name, qualityStr, voice.language];
        if ([voice.identifier isEqualToString:current.identifier]) {
            title = [NSString stringWithFormat:@"✓ %@", title];
        }

        UIAlertAction *action = [UIAlertAction actionWithTitle:title style:UIAlertActionStyleDefault handler:^(UIAlertAction *a) {
            [[TTSService sharedService] setPreferredVoiceWithIdentifier:voice.identifier];
            // 试听
            [[TTSService sharedService] speak:@"你好，我是你的语音助手"];
            [self.tableView reloadData];
        }];
        [alert addAction:action];
    }

    [alert addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];

    // iPad 兼容
    alert.popoverPresentationController.sourceView = self.tableView;
    alert.popoverPresentationController.sourceRect = [self.tableView rectForRowAtIndexPath:[NSIndexPath indexPathForRow:1 inSection:SettingsSectionVoice]];

    [self presentViewController:alert animated:YES completion:nil];
}

- (void)connectButtonTapped {
    [self saveConfig];
    [[WebSocketService sharedService] disconnect];
    [[WebSocketService sharedService] connect];
    [self checkServerStatus];
}

- (void)disconnectButtonTapped {
    [[WebSocketService sharedService] disconnect];
    [self checkServerStatus];
}

#pragma mark - Config

- (void)loadCurrentConfig {
    ServerConfig *config = [ServerConfig sharedConfig];
    self.serverURLField.text = config.serverURL;
    self.tokenField.text = config.authToken;
}

- (void)saveConfig {
    ServerConfig *config = [ServerConfig sharedConfig];
    config.serverURL = self.serverURLField.text ?: @"";
    config.authToken = self.tokenField.text;
    [config save];
}

- (void)checkServerStatus {
    self.connectionStatusLabel.text = NSLocalizedString(@"checking", nil);
    self.connectionStatusLabel.textColor = [UIColor secondaryLabelColor];
    
    [[WebSocketService sharedService] checkServerHealth:^(BOOL available, NSString *model) {
        dispatch_async(dispatch_get_main_queue(), ^{
            self.isConnected = available;
            self.currentModel = model;
            
            if (available) {
                self.connectionStatusLabel.text = NSLocalizedString(@"server_available", nil);
                self.connectionStatusLabel.textColor = [UIColor systemGreenColor];
                self.modelLabel.text = model ?: NSLocalizedString(@"unknown", nil);
            } else {
                self.connectionStatusLabel.text = NSLocalizedString(@"server_unavailable", nil);
                self.connectionStatusLabel.textColor = [UIColor systemRedColor];
                self.modelLabel.text = @"-";
            }
            
            [self.tableView reloadData];
        });
    }];
}

#pragma mark - UITableViewDataSource

- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView {
    return SettingsSectionCount;
}

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    switch (section) {
        case SettingsSectionServer: return 2;
        case SettingsSectionStatus: return 2;
        case SettingsSectionVoice: return 3;
        case SettingsSectionActions: return 2;
        default: return 0;
    }
}

- (NSString *)tableView:(UITableView *)tableView titleForHeaderInSection:(NSInteger)section {
    switch (section) {
        case SettingsSectionServer: return NSLocalizedString(@"server_configuration", nil);
        case SettingsSectionStatus: return NSLocalizedString(@"status", nil);
        case SettingsSectionVoice: return NSLocalizedString(@"voice_section", nil);
        case SettingsSectionActions: return NSLocalizedString(@"actions", nil);
        default: return nil;
    }
}

- (NSString *)tableView:(UITableView *)tableView titleForFooterInSection:(NSInteger)section {
    if (section == SettingsSectionServer) {
        return NSLocalizedString(@"server_config_footer", nil);
    }
    if (section == SettingsSectionVoice) {
        return @"\u2139\uFE0F \u53EF\u5728 \u8BBE\u7F6E > \u8F85\u52A9\u529F\u80FD > \u5B9E\u65F6\u8BED\u97F3 > \u6DFB\u52A0\u9996\u9009\u58F0\u97F3 \u4E2D\u4E0B\u8F7D\u66F4\u591A\u9AD8\u8D28\u91CF\u8BED\u97F3";
    }
    return nil;
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    UITableViewCell *cell;
    
    switch (indexPath.section) {
        case SettingsSectionServer: {
            cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleDefault reuseIdentifier:nil];
            cell.selectionStyle = UITableViewCellSelectionStyleNone;
            
            UITextField *textField = [[UITextField alloc] init];
            textField.translatesAutoresizingMaskIntoConstraints = NO;
            textField.delegate = self;
            textField.clearButtonMode = UITextFieldViewModeWhileEditing;
            textField.autocapitalizationType = UITextAutocapitalizationTypeNone;
            textField.autocorrectionType = UITextAutocorrectionTypeNo;
            [cell.contentView addSubview:textField];
            
            UILabel *label = [[UILabel alloc] init];
            label.translatesAutoresizingMaskIntoConstraints = NO;
            label.font = [UIFont systemFontOfSize:15];
            label.textColor = [UIColor labelColor];
            [cell.contentView addSubview:label];
            
            [NSLayoutConstraint activateConstraints:@[
                [label.leadingAnchor constraintEqualToAnchor:cell.contentView.leadingAnchor constant:16],
                [label.topAnchor constraintEqualToAnchor:cell.contentView.topAnchor constant:12],
                [label.bottomAnchor constraintEqualToAnchor:cell.contentView.bottomAnchor constant:-12],
                [label.widthAnchor constraintEqualToConstant:80],
                
                [textField.leadingAnchor constraintEqualToAnchor:label.trailingAnchor constant:8],
                [textField.trailingAnchor constraintEqualToAnchor:cell.contentView.trailingAnchor constant:-16],
                [textField.centerYAnchor constraintEqualToAnchor:label.centerYAnchor]
            ]];
            
            if (indexPath.row == 0) {
                label.text = NSLocalizedString(@"url", nil);
                textField.placeholder = NSLocalizedString(@"url_placeholder", nil);
                textField.keyboardType = UIKeyboardTypeURL;
                textField.text = [ServerConfig sharedConfig].serverURL;
                self.serverURLField = textField;
            } else {
                label.text = NSLocalizedString(@"token", nil);
                textField.placeholder = NSLocalizedString(@"token_placeholder", nil);
                textField.secureTextEntry = YES;
                textField.text = [ServerConfig sharedConfig].authToken;
                self.tokenField = textField;
            }
            break;
        }
        
        case SettingsSectionStatus: {
            cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleValue1 reuseIdentifier:nil];
            cell.selectionStyle = UITableViewCellSelectionStyleNone;
            
            if (indexPath.row == 0) {
                cell.textLabel.text = NSLocalizedString(@"connection", nil);
                if (!self.connectionStatusLabel) {
                    self.connectionStatusLabel = [[UILabel alloc] init];
                    self.connectionStatusLabel.font = [UIFont systemFontOfSize:15];
                    self.connectionStatusLabel.textAlignment = NSTextAlignmentRight;
                }
                cell.accessoryView = self.connectionStatusLabel;
                [self.connectionStatusLabel sizeToFit];
            } else {
                cell.textLabel.text = NSLocalizedString(@"model", nil);
                if (!self.modelLabel) {
                    self.modelLabel = [[UILabel alloc] init];
                    self.modelLabel.font = [UIFont systemFontOfSize:15];
                    self.modelLabel.textColor = [UIColor secondaryLabelColor];
                    self.modelLabel.textAlignment = NSTextAlignmentRight;
                    self.modelLabel.text = @"-";
                }
                cell.accessoryView = self.modelLabel;
                [self.modelLabel sizeToFit];
            }
            break;
        }
        
        case SettingsSectionVoice: {
            cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
            cell.selectionStyle = UITableViewCellSelectionStyleNone;
            if (indexPath.row == 0) {
                cell.textLabel.text = NSLocalizedString(@"tts_read_reply", nil);
                if (!self.ttsSwitch) {
                    self.ttsSwitch = [[UISwitch alloc] init];
                    [self.ttsSwitch addTarget:self action:@selector(ttsSwitchChanged:) forControlEvents:UIControlEventValueChanged];
                }
                self.ttsSwitch.on = [[NSUserDefaults standardUserDefaults] boolForKey:kUserDefaultsTTSEnabled];
                cell.accessoryView = self.ttsSwitch;
            } else if (indexPath.row == 1) {
                cell.textLabel.text = @"\u6717\u8BFB\u58F0\u97F3";
                AVSpeechSynthesisVoice *voice = [TTSService sharedService].currentVoice;
                NSString *qualityStr = @"";
                if ((NSInteger)voice.quality >= 2) qualityStr = @" (\u589E\u5F3A)";
                if ((NSInteger)voice.quality >= 3) qualityStr = @" (\u4F18\u8D28)";
                cell.detailTextLabel.text = [NSString stringWithFormat:@"%@%@ - %@", voice.name, qualityStr, voice.language];
                cell.detailTextLabel.textColor = [UIColor secondaryLabelColor];
                cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator;
                cell.selectionStyle = UITableViewCellSelectionStyleDefault;
            } else {
                cell.textLabel.text = NSLocalizedString(@"stt_voice_input", nil);
                cell.detailTextLabel.text = NSLocalizedString(@"stt_voice_input_hint", nil);
                cell.detailTextLabel.textColor = [UIColor secondaryLabelColor];
                cell.detailTextLabel.numberOfLines = 2;
            }
            break;
        }
        
        case SettingsSectionActions: {
            cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleDefault reuseIdentifier:nil];
            cell.textLabel.textAlignment = NSTextAlignmentCenter;
            
            if (indexPath.row == 0) {
                cell.textLabel.text = NSLocalizedString(@"connect", nil);
                cell.textLabel.textColor = [UIColor systemBlueColor];
            } else {
                cell.textLabel.text = NSLocalizedString(@"disconnect", nil);
                cell.textLabel.textColor = [UIColor systemRedColor];
            }
            break;
        }
    }
    
    return cell;
}

#pragma mark - UITableViewDelegate

- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    
    if (indexPath.section == SettingsSectionVoice && indexPath.row == 0) {
        [self.ttsSwitch setOn:!self.ttsSwitch.isOn animated:YES];
        [self ttsSwitchChanged:self.ttsSwitch];
    }
    
    if (indexPath.section == SettingsSectionVoice && indexPath.row == 1) {
        [self showVoicePicker];
    }
    
    if (indexPath.section == SettingsSectionActions) {
        if (indexPath.row == 0) {
            [self connectButtonTapped];
        } else {
            [self disconnectButtonTapped];
        }
    }
}

#pragma mark - UITextFieldDelegate

- (void)textFieldDidEndEditing:(UITextField *)textField {
    [self saveConfig];
}

- (BOOL)textFieldShouldReturn:(UITextField *)textField {
    [textField resignFirstResponder];
    return YES;
}

@end

#pragma mark - QRScannerViewController Implementation

@implementation QRScannerViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    
    self.title = NSLocalizedString(@"scan_qr_code", nil);
    self.view.backgroundColor = [UIColor blackColor];
    
    UIBarButtonItem *cancelButton = [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemCancel target:self action:@selector(cancelTapped)];
    self.navigationItem.leftBarButtonItem = cancelButton;
    
    [self setupCamera];
}

- (void)viewWillAppear:(BOOL)animated {
    [super viewWillAppear:animated];
    
    if (self.captureSession && !self.captureSession.isRunning) {
        dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
            [self.captureSession startRunning];
        });
    }
}

- (void)viewWillDisappear:(BOOL)animated {
    [super viewWillDisappear:animated];
    
    if (self.captureSession && self.captureSession.isRunning) {
        dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
            [self.captureSession stopRunning];
        });
    }
}

- (void)setupCamera {
    self.captureSession = [[AVCaptureSession alloc] init];
    
    AVCaptureDevice *device = [AVCaptureDevice defaultDeviceWithMediaType:AVMediaTypeVideo];
    if (!device) {
        [self showError:NSLocalizedString(@"camera_unavailable", nil)];
        return;
    }
    
    NSError *error;
    AVCaptureDeviceInput *input = [AVCaptureDeviceInput deviceInputWithDevice:device error:&error];
    if (error) {
        [self showError:error.localizedDescription];
        return;
    }
    
    if ([self.captureSession canAddInput:input]) {
        [self.captureSession addInput:input];
    }
    
    AVCaptureMetadataOutput *output = [[AVCaptureMetadataOutput alloc] init];
    if ([self.captureSession canAddOutput:output]) {
        [self.captureSession addOutput:output];
        [output setMetadataObjectsDelegate:self queue:dispatch_get_main_queue()];
        output.metadataObjectTypes = @[AVMetadataObjectTypeQRCode];
    }
    
    self.previewLayer = [AVCaptureVideoPreviewLayer layerWithSession:self.captureSession];
    self.previewLayer.frame = self.view.bounds;
    self.previewLayer.videoGravity = AVLayerVideoGravityResizeAspectFill;
    [self.view.layer addSublayer:self.previewLayer];
    
    UIView *overlay = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 250, 250)];
    overlay.center = self.view.center;
    overlay.layer.borderColor = [UIColor whiteColor].CGColor;
    overlay.layer.borderWidth = 2;
    overlay.layer.cornerRadius = 12;
    [self.view addSubview:overlay];
}

- (void)cancelTapped {
    if (self.completionHandler) {
        self.completionHandler(nil);
    }
    [self dismissViewControllerAnimated:YES completion:nil];
}

- (void)showError:(NSString *)message {
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:NSLocalizedString(@"error", nil) message:message preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:NSLocalizedString(@"ok", nil) style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        [self dismissViewControllerAnimated:YES completion:nil];
    }]];
    [self presentViewController:alert animated:YES completion:nil];
}

#pragma mark - AVCaptureMetadataOutputObjectsDelegate

- (void)captureOutput:(AVCaptureOutput *)output didOutputMetadataObjects:(NSArray<__kindof AVMetadataObject *> *)metadataObjects fromConnection:(AVCaptureConnection *)connection {
    if (metadataObjects.count == 0) return;
    
    AVMetadataMachineReadableCodeObject *codeObject = metadataObjects.firstObject;
    if ([codeObject.type isEqualToString:AVMetadataObjectTypeQRCode]) {
        [self.captureSession stopRunning];
        
        AudioServicesPlaySystemSound(kSystemSoundID_Vibrate);
        
        if (self.completionHandler) {
            self.completionHandler(codeObject.stringValue);
        }
        [self dismissViewControllerAnimated:YES completion:nil];
    }
}

@end
