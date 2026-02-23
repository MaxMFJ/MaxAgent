#import "MessageCell.h"

@interface MessageCell ()

@property (nonatomic, strong) UILabel *contentLabel;
@property (nonatomic, strong) UILabel *roleLabel;
@property (nonatomic, strong) UIView *bubbleView;
@property (nonatomic, strong) UIActivityIndicatorView *loadingIndicator;
@property (nonatomic, strong) UIImageView *messageImageView;
@property (nonatomic, strong) UIStackView *bubbleStackView;
@property (nonatomic, strong) NSLayoutConstraint *bubbleLeading;
@property (nonatomic, strong) NSLayoutConstraint *bubbleTrailing;

@end

@implementation MessageCell

- (instancetype)initWithStyle:(UITableViewCellStyle)style reuseIdentifier:(NSString *)reuseIdentifier {
    self = [super initWithStyle:style reuseIdentifier:reuseIdentifier];
    if (self) {
        [self setupUI];
    }
    return self;
}

- (void)setupUI {
    self.selectionStyle = UITableViewCellSelectionStyleNone;
    self.backgroundColor = [UIColor clearColor];
    self.contentView.backgroundColor = [UIColor clearColor];
    
    _bubbleView = [[UIView alloc] init];
    _bubbleView.translatesAutoresizingMaskIntoConstraints = NO;
    _bubbleView.layer.cornerRadius = 16;
    _bubbleView.clipsToBounds = YES;
    [self.contentView addSubview:_bubbleView];
    
    _roleLabel = [[UILabel alloc] init];
    _roleLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _roleLabel.font = [UIFont systemFontOfSize:11 weight:UIFontWeightMedium];
    _roleLabel.textColor = [UIColor secondaryLabelColor];
    [self.contentView addSubview:_roleLabel];
    
    _contentLabel = [[UILabel alloc] init];
    _contentLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _contentLabel.font = [UIFont systemFontOfSize:16];
    _contentLabel.numberOfLines = 0;
    
    _messageImageView = [[UIImageView alloc] init];
    _messageImageView.translatesAutoresizingMaskIntoConstraints = NO;
    _messageImageView.contentMode = UIViewContentModeScaleAspectFit;
    _messageImageView.layer.cornerRadius = 8;
    _messageImageView.clipsToBounds = YES;
    _messageImageView.hidden = YES;
    
    _bubbleStackView = [[UIStackView alloc] initWithArrangedSubviews:@[_contentLabel, _messageImageView]];
    _bubbleStackView.axis = UILayoutConstraintAxisVertical;
    _bubbleStackView.spacing = 8;
    _bubbleStackView.translatesAutoresizingMaskIntoConstraints = NO;
    [_bubbleView addSubview:_bubbleStackView];
    
    _loadingIndicator = [[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleMedium];
    _loadingIndicator.translatesAutoresizingMaskIntoConstraints = NO;
    _loadingIndicator.hidesWhenStopped = YES;
    [_bubbleView addSubview:_loadingIndicator];
    
    _bubbleLeading = [_bubbleView.leadingAnchor constraintEqualToAnchor:self.contentView.leadingAnchor constant:16];
    _bubbleTrailing = [_bubbleView.trailingAnchor constraintEqualToAnchor:self.contentView.trailingAnchor constant:-16];
    
    [NSLayoutConstraint activateConstraints:@[
        [_roleLabel.topAnchor constraintEqualToAnchor:self.contentView.topAnchor constant:8],
        [_roleLabel.leadingAnchor constraintEqualToAnchor:self.contentView.leadingAnchor constant:20],
        [_roleLabel.trailingAnchor constraintEqualToAnchor:self.contentView.trailingAnchor constant:-20],
        
        [_bubbleView.topAnchor constraintEqualToAnchor:_roleLabel.bottomAnchor constant:4],
        [_bubbleView.bottomAnchor constraintEqualToAnchor:self.contentView.bottomAnchor constant:-4],
        [_bubbleView.widthAnchor constraintLessThanOrEqualToAnchor:self.contentView.widthAnchor multiplier:0.8],
        
        [_bubbleStackView.topAnchor constraintEqualToAnchor:_bubbleView.topAnchor constant:10],
        [_bubbleStackView.leadingAnchor constraintEqualToAnchor:_bubbleView.leadingAnchor constant:14],
        [_bubbleStackView.trailingAnchor constraintEqualToAnchor:_bubbleView.trailingAnchor constant:-14],
        [_bubbleStackView.bottomAnchor constraintEqualToAnchor:_bubbleView.bottomAnchor constant:-10],
        
        [_messageImageView.widthAnchor constraintLessThanOrEqualToConstant:280],
        [_messageImageView.heightAnchor constraintLessThanOrEqualToConstant:300],
        
        [_loadingIndicator.centerYAnchor constraintEqualToAnchor:_bubbleView.centerYAnchor],
        [_loadingIndicator.trailingAnchor constraintEqualToAnchor:_bubbleView.trailingAnchor constant:-14]
    ]];
}

- (void)configureWithMessage:(Message *)message {
    self.contentLabel.text = message.content.length > 0 ? message.content : @" ";
    
    BOOL isUser = (message.role == MessageRoleUser);
    BOOL isToolCall = (message.role == MessageRoleToolCall);
    BOOL isToolResult = (message.role == MessageRoleToolResult);
    
    _bubbleLeading.active = NO;
    _bubbleTrailing.active = NO;
    
    if (isUser) {
        _bubbleTrailing.active = YES;
        _bubbleView.backgroundColor = [UIColor systemBlueColor];
        _contentLabel.textColor = [UIColor whiteColor];
        _roleLabel.text = NSLocalizedString(@"you", nil);
        _roleLabel.textAlignment = NSTextAlignmentRight;
    } else if (isToolCall) {
        _bubbleLeading.active = YES;
        _bubbleView.backgroundColor = [UIColor systemOrangeColor];
        _contentLabel.textColor = [UIColor whiteColor];
        _roleLabel.text = [NSString stringWithFormat:@"🔧 %@", message.toolName ?: NSLocalizedString(@"tool", nil)];
        _roleLabel.textAlignment = NSTextAlignmentLeft;
    } else if (isToolResult) {
        _bubbleLeading.active = YES;
        _bubbleView.backgroundColor = [UIColor systemGreenColor];
        _contentLabel.textColor = [UIColor whiteColor];
        _roleLabel.text = [NSString stringWithFormat:@"✓ %@", NSLocalizedString(@"result", nil)];
        _roleLabel.textAlignment = NSTextAlignmentLeft;
    } else {
        _bubbleLeading.active = YES;
        _bubbleView.backgroundColor = [UIColor secondarySystemBackgroundColor];
        _contentLabel.textColor = [UIColor labelColor];
        _roleLabel.text = message.modelName ?: NSLocalizedString(@"assistant", nil);
        _roleLabel.textAlignment = NSTextAlignmentLeft;
    }
    
    if (message.status == MessageStatusStreaming) {
        [_loadingIndicator startAnimating];
    } else {
        [_loadingIndicator stopAnimating];
    }
    
    if (message.imageBase64.length > 0) {
        NSData *imageData = [[NSData alloc] initWithBase64EncodedString:message.imageBase64 options:NSDataBase64DecodingIgnoreUnknownCharacters];
        UIImage *image = [UIImage imageWithData:imageData];
        if (image) {
            _messageImageView.image = image;
            _messageImageView.hidden = NO;
            return;
        }
    }
    _messageImageView.image = nil;
    _messageImageView.hidden = YES;
}

@end
