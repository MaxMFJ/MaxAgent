#import "FileDownloadView.h"
#import "TechTheme.h"

// MARK: - 文件扩展名到图标的映射

static NSString *_iconNameForExtension(NSString *ext) {
    static NSDictionary<NSString *, NSString *> *iconMap = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        iconMap = @{
            // 文档
            @"pdf": @"doc.fill",
            @"doc": @"doc.fill",
            @"docx": @"doc.fill",
            @"txt": @"doc.text",
            @"md": @"doc.text",
            @"rtf": @"doc.text",
            @"log": @"doc.text",
            // 表格
            @"xls": @"tablecells",
            @"xlsx": @"tablecells",
            @"csv": @"tablecells",
            // 演示
            @"ppt": @"play.rectangle",
            @"pptx": @"play.rectangle",
            @"key": @"play.rectangle",
            // 压缩
            @"zip": @"doc.zipper",
            @"tar": @"doc.zipper",
            @"gz": @"doc.zipper",
            @"rar": @"doc.zipper",
            @"7z": @"doc.zipper",
            // 代码
            @"py": @"chevron.left.forwardslash.chevron.right",
            @"js": @"chevron.left.forwardslash.chevron.right",
            @"ts": @"chevron.left.forwardslash.chevron.right",
            @"swift": @"chevron.left.forwardslash.chevron.right",
            @"java": @"chevron.left.forwardslash.chevron.right",
            @"c": @"chevron.left.forwardslash.chevron.right",
            @"cpp": @"chevron.left.forwardslash.chevron.right",
            @"h": @"chevron.left.forwardslash.chevron.right",
            @"m": @"chevron.left.forwardslash.chevron.right",
            @"html": @"chevron.left.forwardslash.chevron.right",
            @"css": @"chevron.left.forwardslash.chevron.right",
            @"json": @"chevron.left.forwardslash.chevron.right",
            @"xml": @"chevron.left.forwardslash.chevron.right",
            @"yaml": @"chevron.left.forwardslash.chevron.right",
            @"yml": @"chevron.left.forwardslash.chevron.right",
            @"sh": @"terminal",
            // 音视频
            @"mp3": @"music.note",
            @"mp4": @"film",
            @"mov": @"film",
            @"avi": @"film",
            @"wav": @"waveform",
            // 其他
            @"dmg": @"externaldrive",
            @"app": @"app.gift",
        };
    });
    return iconMap[ext.lowercaseString] ?: @"doc";
}

static UIColor *_iconColorForExtension(NSString *ext) {
    ext = ext.lowercaseString;
    if ([ext isEqualToString:@"pdf"]) return [UIColor systemRedColor];
    if ([@[@"doc", @"docx"] containsObject:ext]) return [UIColor systemBlueColor];
    if ([@[@"xls", @"xlsx", @"csv"] containsObject:ext]) return [UIColor systemGreenColor];
    if ([@[@"ppt", @"pptx", @"key"] containsObject:ext]) return [UIColor systemOrangeColor];
    if ([@[@"zip", @"tar", @"gz", @"rar", @"7z"] containsObject:ext]) return [UIColor systemYellowColor];
    if ([@[@"py"] containsObject:ext]) return [UIColor colorWithRed:0.2 green:0.6 blue:1.0 alpha:1.0];
    if ([@[@"js", @"ts"] containsObject:ext]) return [UIColor systemYellowColor];
    if ([@[@"swift"] containsObject:ext]) return [UIColor systemOrangeColor];
    if ([@[@"mp3", @"wav", @"aac", @"m4a"] containsObject:ext]) return [UIColor systemPinkColor];
    if ([@[@"mp4", @"mov", @"avi", @"mkv"] containsObject:ext]) return [UIColor systemPurpleColor];
    return TechTheme.neonCyan;
}

// 图片扩展名（不应被检测为文件下载）
static NSSet<NSString *> *_imageExtensions(void) {
    static NSSet *exts = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        exts = [NSSet setWithArray:@[@"png", @"jpg", @"jpeg", @"gif", @"webp", @"bmp", @"svg", @"ico"]];
    });
    return exts;
}


@interface FileDownloadView ()

@property (nonatomic, copy) NSString *filePath;
@property (nonatomic, copy) NSString *serverBaseURL;

@property (nonatomic, strong) UIView *iconContainer;
@property (nonatomic, strong) UIImageView *iconView;
@property (nonatomic, strong) UILabel *fileNameLabel;
@property (nonatomic, strong) UILabel *fileInfoLabel;
@property (nonatomic, strong) UILabel *filePathLabel;
@property (nonatomic, strong) UIButton *downloadButton;
@property (nonatomic, strong) UIActivityIndicatorView *spinner;
@property (nonatomic, strong) UILabel *statusLabel;

@property (nonatomic, assign) BOOL isDownloading;

@end


@implementation FileDownloadView

// MARK: - 文件路径检测

+ (NSArray<NSString *> *)detectFilePathsInText:(NSString *)text {
    if (!text || text.length == 0) return @[];

    NSMutableArray<NSString *> *paths = [NSMutableArray array];
    NSRegularExpression *imageRegex = [NSRegularExpression
        regularExpressionWithPattern:@"\\.(png|jpg|jpeg|gif|webp|bmp|svg|ico)$"
        options:NSRegularExpressionCaseInsensitive
        error:nil];

    // 策略1：匹配独立行的绝对路径（允许含空格，因为是整行）
    NSRegularExpression *lineRegex = [NSRegularExpression
        regularExpressionWithPattern:@"(?:^|\\n)\\s*(/[^\\n]*?/[^\\n]*\\.[a-zA-Z0-9]{1,10})\\s*(?:\\n|$)"
        options:0
        error:nil];
    for (NSTextCheckingResult *match in [lineRegex matchesInString:text options:0 range:NSMakeRange(0, text.length)]) {
        NSRange r = [match rangeAtIndex:1];
        if (r.location == NSNotFound) continue;
        NSString *path = [[text substringWithRange:r] stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceCharacterSet]];
        // 去除尾部中文标点
        while (path.length > 0) {
            unichar last = [path characterAtIndex:path.length - 1];
            if (last == 0x3002 || last == 0xFF0C || last == 0xFF1B || last == 0xFF1A || last == 0xFF01 || last == 0xFF1F) {
                path = [path substringToIndex:path.length - 1];
            } else break;
        }
        if ([self validateFilePath:path imageRegex:imageRegex] && ![paths containsObject:path]) {
            [paths addObject:path];
        }
    }

    // 策略2：内联无空格路径
    NSRegularExpression *inlineRegex = [NSRegularExpression
        regularExpressionWithPattern:@"(/[^\\s\"'`\\)），。！？；：\\n]+/[^\\s\"'`\\)），。！？；：\\n]+\\.[a-zA-Z0-9]{1,10})(?=$|\\s|[，。！？；：'\"``\\)）\\n])"
        options:0
        error:nil];
    for (NSTextCheckingResult *match in [inlineRegex matchesInString:text options:0 range:NSMakeRange(0, text.length)]) {
        NSRange r = [match rangeAtIndex:1];
        if (r.location == NSNotFound) continue;
        NSString *path = [text substringWithRange:r];
        if ([self validateFilePath:path imageRegex:imageRegex] && ![paths containsObject:path]) {
            [paths addObject:path];
        }
    }

    // 策略3：反引号中的路径
    NSRegularExpression *backtickRegex = [NSRegularExpression
        regularExpressionWithPattern:@"`(/[^`\\n]+/[^`\\n]+\\.[a-zA-Z0-9]{1,10})`"
        options:0
        error:nil];
    for (NSTextCheckingResult *match in [backtickRegex matchesInString:text options:0 range:NSMakeRange(0, text.length)]) {
        NSRange r = [match rangeAtIndex:1];
        if (r.location == NSNotFound) continue;
        NSString *path = [text substringWithRange:r];
        if ([self validateFilePath:path imageRegex:imageRegex] && ![paths containsObject:path]) {
            [paths addObject:path];
        }
    }

    return paths;
}

+ (BOOL)validateFilePath:(NSString *)path imageRegex:(NSRegularExpression *)imageRegex {
    if (![path hasPrefix:@"/"]) return NO;
    NSArray *components = [[path componentsSeparatedByString:@"/"] filteredArrayUsingPredicate:
                           [NSPredicate predicateWithFormat:@"length > 0"]];
    if (components.count < 2) return NO;
    NSString *ext = path.pathExtension;
    if (ext.length == 0 || ext.length > 10) return NO;
    if ([imageRegex numberOfMatchesInString:path options:0 range:NSMakeRange(0, path.length)] > 0) return NO;
    if ([path containsString:@"://"]) return NO;
    if ([path containsString:@"]("] || [path containsString:@"!["]) return NO;
    return YES;
}


// MARK: - 初始化

- (instancetype)initWithFilePath:(NSString *)filePath serverBaseURL:(NSString *)serverBaseURL {
    self = [super initWithFrame:CGRectZero];
    if (self) {
        _filePath = [filePath copy];
        _serverBaseURL = [serverBaseURL copy];
        _isDownloading = NO;
        [self setupUI];
        [self loadFileInfo];
    }
    return self;
}

// MARK: - UI Setup

- (void)setupUI {
    self.translatesAutoresizingMaskIntoConstraints = NO;
    self.backgroundColor = [TechTheme.backgroundSecondary colorWithAlphaComponent:0.8];
    self.layer.cornerRadius = 10;
    self.layer.borderWidth = 1;
    self.layer.borderColor = [TechTheme.neonCyan colorWithAlphaComponent:0.15].CGColor;

    NSString *ext = self.filePath.pathExtension;
    UIColor *accentColor = _iconColorForExtension(ext);

    // 文件图标容器
    _iconContainer = [[UIView alloc] init];
    _iconContainer.translatesAutoresizingMaskIntoConstraints = NO;
    _iconContainer.backgroundColor = [accentColor colorWithAlphaComponent:0.15];
    _iconContainer.layer.cornerRadius = 8;
    [self addSubview:_iconContainer];

    // 文件图标
    _iconView = [[UIImageView alloc] init];
    _iconView.translatesAutoresizingMaskIntoConstraints = NO;
    _iconView.contentMode = UIViewContentModeScaleAspectFit;
    _iconView.tintColor = accentColor;
    NSString *systemName = _iconNameForExtension(ext);
    UIImageSymbolConfiguration *config = [UIImageSymbolConfiguration configurationWithPointSize:18 weight:UIImageSymbolWeightMedium];
    _iconView.image = [UIImage systemImageNamed:systemName withConfiguration:config];
    [_iconContainer addSubview:_iconView];

    // 文件名
    _fileNameLabel = [[UILabel alloc] init];
    _fileNameLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _fileNameLabel.font = [TechTheme fontDisplaySize:14 weight:UIFontWeightMedium];
    _fileNameLabel.textColor = TechTheme.textPrimary;
    _fileNameLabel.text = self.filePath.lastPathComponent;
    _fileNameLabel.lineBreakMode = NSLineBreakByTruncatingMiddle;
    [self addSubview:_fileNameLabel];

    // 文件信息行
    _fileInfoLabel = [[UILabel alloc] init];
    _fileInfoLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _fileInfoLabel.font = [TechTheme fontBodySize:11 weight:UIFontWeightRegular];
    _fileInfoLabel.textColor = TechTheme.textSecondary;
    _fileInfoLabel.text = @"加载中...";
    [self addSubview:_fileInfoLabel];

    // 文件路径
    _filePathLabel = [[UILabel alloc] init];
    _filePathLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _filePathLabel.font = [TechTheme fontMonoSize:10 weight:UIFontWeightRegular];
    _filePathLabel.textColor = [TechTheme.textSecondary colorWithAlphaComponent:0.5];
    _filePathLabel.text = self.filePath;
    _filePathLabel.lineBreakMode = NSLineBreakByTruncatingMiddle;
    [self addSubview:_filePathLabel];

    // 下载按钮
    _downloadButton = [UIButton buttonWithType:UIButtonTypeCustom];
    _downloadButton.translatesAutoresizingMaskIntoConstraints = NO;
    UIImageSymbolConfiguration *btnConfig = [UIImageSymbolConfiguration configurationWithPointSize:14 weight:UIImageSymbolWeightMedium];
    UIImage *downloadIcon = [UIImage systemImageNamed:@"square.and.arrow.down" withConfiguration:btnConfig];
    [_downloadButton setImage:downloadIcon forState:UIControlStateNormal];
    _downloadButton.tintColor = TechTheme.neonCyan;
    _downloadButton.backgroundColor = [TechTheme.neonCyan colorWithAlphaComponent:0.15];
    _downloadButton.layer.cornerRadius = 6;
    [_downloadButton addTarget:self action:@selector(downloadTapped) forControlEvents:UIControlEventTouchUpInside];
    [self addSubview:_downloadButton];

    // 下载中指示器
    _spinner = [[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleMedium];
    _spinner.translatesAutoresizingMaskIntoConstraints = NO;
    _spinner.hidesWhenStopped = YES;
    _spinner.color = TechTheme.neonCyan;
    [self addSubview:_spinner];

    // 状态标签
    _statusLabel = [[UILabel alloc] init];
    _statusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _statusLabel.font = [TechTheme fontBodySize:11 weight:UIFontWeightRegular];
    _statusLabel.textColor = TechTheme.neonGreen;
    _statusLabel.text = @"";
    _statusLabel.hidden = YES;
    [self addSubview:_statusLabel];

    // AutoLayout
    [NSLayoutConstraint activateConstraints:@[
        // 图标容器
        [_iconContainer.leadingAnchor constraintEqualToAnchor:self.leadingAnchor constant:12],
        [_iconContainer.centerYAnchor constraintEqualToAnchor:self.centerYAnchor],
        [_iconContainer.widthAnchor constraintEqualToConstant:40],
        [_iconContainer.heightAnchor constraintEqualToConstant:40],

        [_iconView.centerXAnchor constraintEqualToAnchor:_iconContainer.centerXAnchor],
        [_iconView.centerYAnchor constraintEqualToAnchor:_iconContainer.centerYAnchor],

        // 文件名
        [_fileNameLabel.topAnchor constraintEqualToAnchor:self.topAnchor constant:10],
        [_fileNameLabel.leadingAnchor constraintEqualToAnchor:_iconContainer.trailingAnchor constant:10],
        [_fileNameLabel.trailingAnchor constraintLessThanOrEqualToAnchor:_downloadButton.leadingAnchor constant:-8],

        // 文件信息
        [_fileInfoLabel.topAnchor constraintEqualToAnchor:_fileNameLabel.bottomAnchor constant:2],
        [_fileInfoLabel.leadingAnchor constraintEqualToAnchor:_fileNameLabel.leadingAnchor],
        [_fileInfoLabel.trailingAnchor constraintLessThanOrEqualToAnchor:_downloadButton.leadingAnchor constant:-8],

        // 文件路径
        [_filePathLabel.topAnchor constraintEqualToAnchor:_fileInfoLabel.bottomAnchor constant:2],
        [_filePathLabel.leadingAnchor constraintEqualToAnchor:_fileNameLabel.leadingAnchor],
        [_filePathLabel.trailingAnchor constraintLessThanOrEqualToAnchor:_downloadButton.leadingAnchor constant:-8],
        [_filePathLabel.bottomAnchor constraintEqualToAnchor:self.bottomAnchor constant:-10],

        // 下载按钮
        [_downloadButton.trailingAnchor constraintEqualToAnchor:self.trailingAnchor constant:-12],
        [_downloadButton.centerYAnchor constraintEqualToAnchor:self.centerYAnchor],
        [_downloadButton.widthAnchor constraintEqualToConstant:32],
        [_downloadButton.heightAnchor constraintEqualToConstant:32],

        // 加载中
        [_spinner.centerXAnchor constraintEqualToAnchor:_downloadButton.centerXAnchor],
        [_spinner.centerYAnchor constraintEqualToAnchor:_downloadButton.centerYAnchor],

        // 状态标签
        [_statusLabel.centerXAnchor constraintEqualToAnchor:_downloadButton.centerXAnchor],
        [_statusLabel.centerYAnchor constraintEqualToAnchor:_downloadButton.centerYAnchor],

        // 整体高度
        [self.heightAnchor constraintGreaterThanOrEqualToConstant:64],
    ]];
}


// MARK: - 加载文件信息

- (void)loadFileInfo {
    if (self.serverBaseURL.length == 0) {
        self.fileInfoLabel.text = self.filePath.pathExtension.uppercaseString;
        return;
    }

    NSString *encoded = [self.filePath stringByAddingPercentEncodingWithAllowedCharacters:[NSCharacterSet URLQueryAllowedCharacterSet]];
    NSString *urlStr = [NSString stringWithFormat:@"%@/files/info?path=%@", self.serverBaseURL, encoded];
    NSURL *url = [NSURL URLWithString:urlStr];
    if (!url) {
        self.fileInfoLabel.text = self.filePath.pathExtension.uppercaseString;
        return;
    }

    __weak typeof(self) weakSelf = self;
    NSURLSessionDataTask *task = [[NSURLSession sharedSession] dataTaskWithURL:url completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            __strong typeof(weakSelf) sSelf = weakSelf;
            if (!sSelf) return;

            if (error || !data) {
                sSelf.fileInfoLabel.text = sSelf.filePath.pathExtension.uppercaseString;
                return;
            }

            NSDictionary *json = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
            if (![json isKindOfClass:[NSDictionary class]]) {
                sSelf.fileInfoLabel.text = sSelf.filePath.pathExtension.uppercaseString;
                return;
            }

            NSString *sizeFormatted = json[@"size_formatted"] ?: @"-";
            NSString *ext = json[@"extension"] ?: @"";
            NSString *info = [NSString stringWithFormat:@"%@  ·  %@", sizeFormatted, ext.uppercaseString];
            sSelf.fileInfoLabel.text = info;
        });
    }];
    [task resume];
}


// MARK: - 下载

- (void)downloadTapped {
    if (self.isDownloading) return;
    self.isDownloading = YES;

    self.downloadButton.hidden = YES;
    [self.spinner startAnimating];

    NSString *encoded = [self.filePath stringByAddingPercentEncodingWithAllowedCharacters:[NSCharacterSet URLQueryAllowedCharacterSet]];
    NSString *urlStr = [NSString stringWithFormat:@"%@/files/download?path=%@", self.serverBaseURL, encoded];
    NSURL *url = [NSURL URLWithString:urlStr];

    if (!url) {
        [self showError:@"无效路径"];
        return;
    }

    __weak typeof(self) weakSelf = self;
    NSURLSessionDownloadTask *downloadTask = [[NSURLSession sharedSession] downloadTaskWithURL:url completionHandler:^(NSURL *location, NSURLResponse *response, NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            __strong typeof(weakSelf) sSelf = weakSelf;
            if (!sSelf) return;

            [sSelf.spinner stopAnimating];

            if (error || !location) {
                [sSelf showError:@"下载失败"];
                return;
            }

            // 保存到 Documents 目录
            NSFileManager *fm = [NSFileManager defaultManager];
            NSURL *docsDir = [fm URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
            NSString *fileName = sSelf.filePath.lastPathComponent;
            NSURL *destURL = [docsDir URLByAppendingPathComponent:fileName];

            // 如果已存在，加时间戳
            if ([fm fileExistsAtPath:destURL.path]) {
                NSString *stem = [fileName stringByDeletingPathExtension];
                NSString *ext = fileName.pathExtension;
                NSInteger timestamp = (NSInteger)[[NSDate date] timeIntervalSince1970];
                NSString *newName = ext.length > 0
                    ? [NSString stringWithFormat:@"%@_%ld.%@", stem, (long)timestamp, ext]
                    : [NSString stringWithFormat:@"%@_%ld", stem, (long)timestamp];
                destURL = [docsDir URLByAppendingPathComponent:newName];
            }

            NSError *moveError = nil;
            [fm moveItemAtURL:location toURL:destURL error:&moveError];

            if (moveError) {
                [sSelf showError:@"保存失败"];
                return;
            }

            [sSelf showSuccess];

            // 弹出分享 sheet
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
                [sSelf presentShareSheetForFile:destURL];
            });
        });
    }];
    [downloadTask resume];
}

- (void)presentShareSheetForFile:(NSURL *)fileURL {
    UIActivityViewController *activityVC = [[UIActivityViewController alloc] initWithActivityItems:@[fileURL] applicationActivities:nil];

    // 找到最近的 ViewController
    UIResponder *responder = self;
    while (responder && ![responder isKindOfClass:[UIViewController class]]) {
        responder = [responder nextResponder];
    }
    UIViewController *vc = (UIViewController *)responder;
    if (vc) {
        // iPad 支持
        activityVC.popoverPresentationController.sourceView = self.downloadButton;
        activityVC.popoverPresentationController.sourceRect = self.downloadButton.bounds;
        [vc presentViewController:activityVC animated:YES completion:nil];
    }
}

- (void)showSuccess {
    self.isDownloading = NO;
    self.statusLabel.text = @"✓ 已保存";
    self.statusLabel.textColor = TechTheme.neonGreen;
    self.statusLabel.hidden = NO;

    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(3.0 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        self.statusLabel.hidden = YES;
        self.downloadButton.hidden = NO;
    });
}

- (void)showError:(NSString *)msg {
    self.isDownloading = NO;
    [self.spinner stopAnimating];
    self.statusLabel.text = msg;
    self.statusLabel.textColor = TechTheme.neonRed;
    self.statusLabel.hidden = NO;

    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(3.0 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        self.statusLabel.hidden = YES;
        self.downloadButton.hidden = NO;
    });
}

@end
