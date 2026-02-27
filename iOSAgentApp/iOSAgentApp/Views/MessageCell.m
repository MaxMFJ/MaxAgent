#import "MessageCell.h"
#import "ThinkingContentParser.h"
#import "ThinkingBlockView.h"

@interface MessageCell () <ThinkingBlockViewDelegate>

@property (nonatomic, strong) UILabel *contentLabel;
@property (nonatomic, strong) UIStackView *contentStackView;  // 当有 thinking 时使用
@property (nonatomic, strong) UIView *contentContainerView;  // 包裹 contentLabel 或 contentStackView
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
    
    _contentStackView = [[UIStackView alloc] init];
    _contentStackView.axis = UILayoutConstraintAxisVertical;
    _contentStackView.spacing = 8;
    _contentStackView.translatesAutoresizingMaskIntoConstraints = NO;
    _contentStackView.hidden = YES;  // 默认隐藏，有 thinking 时显示
    
    _contentContainerView = [[UIView alloc] init];
    _contentContainerView.translatesAutoresizingMaskIntoConstraints = NO;
    [_contentContainerView addSubview:_contentLabel];
    [_contentContainerView addSubview:_contentStackView];
    [NSLayoutConstraint activateConstraints:@[
        [_contentLabel.topAnchor constraintEqualToAnchor:_contentContainerView.topAnchor],
        [_contentLabel.leadingAnchor constraintEqualToAnchor:_contentContainerView.leadingAnchor],
        [_contentLabel.trailingAnchor constraintEqualToAnchor:_contentContainerView.trailingAnchor],
        [_contentLabel.bottomAnchor constraintEqualToAnchor:_contentContainerView.bottomAnchor],
        [_contentStackView.topAnchor constraintEqualToAnchor:_contentContainerView.topAnchor],
        [_contentStackView.leadingAnchor constraintEqualToAnchor:_contentContainerView.leadingAnchor],
        [_contentStackView.trailingAnchor constraintEqualToAnchor:_contentContainerView.trailingAnchor],
        [_contentStackView.bottomAnchor constraintEqualToAnchor:_contentContainerView.bottomAnchor]
    ]];
    
    _messageImageView = [[UIImageView alloc] init];
    _messageImageView.translatesAutoresizingMaskIntoConstraints = NO;
    _messageImageView.contentMode = UIViewContentModeScaleAspectFit;
    _messageImageView.layer.cornerRadius = 8;
    _messageImageView.clipsToBounds = YES;
    _messageImageView.hidden = YES;
    _messageImageView.userInteractionEnabled = YES;
    
    UITapGestureRecognizer *imageTap = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(imageTapped)];
    [_messageImageView addGestureRecognizer:imageTap];
    
    _bubbleStackView = [[UIStackView alloc] initWithArrangedSubviews:@[_contentContainerView, _messageImageView]];
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
    NSArray *parts = [ThinkingContentParser parseContent:message.content];
    BOOL hasThinking = NO;
    for (NSDictionary *part in parts) {
        if ([part[@"type"] isEqualToString:@"thinking"]) {
            hasThinking = YES;
            break;
        }
    }
    
    if (!hasThinking) {
        _contentLabel.hidden = NO;
        _contentStackView.hidden = YES;
        _contentLabel.text = message.content.length > 0 ? message.content : @" ";
    } else {
        _contentLabel.hidden = YES;
        _contentStackView.hidden = NO;
        for (UIView *v in _contentStackView.arrangedSubviews) {
            [_contentStackView removeArrangedSubview:v];
            [v removeFromSuperview];
        }
        BOOL isStreaming = (message.status == MessageStatusStreaming);
        for (NSDictionary *part in parts) {
            NSString *type = part[@"type"];
            NSString *content = part[@"content"] ?: @"";
            if ([type isEqualToString:@"thinking"]) {
                ThinkingBlockView *tb = [[ThinkingBlockView alloc] initWithThinkingContent:content isStreaming:isStreaming];
                tb.delegate = (id<ThinkingBlockViewDelegate>)self;
                [_contentStackView addArrangedSubview:tb];
            } else if (content.length > 0) {
                UILabel *lbl = [[UILabel alloc] init];
                lbl.font = [UIFont systemFontOfSize:16];
                lbl.numberOfLines = 0;
                lbl.text = content;
                [_contentStackView addArrangedSubview:lbl];
            }
        }
    }
    
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
    
    // 同步 contentStackView 内文本标签的颜色
    for (UIView *v in _contentStackView.arrangedSubviews) {
        if ([v isKindOfClass:[UILabel class]]) {
            ((UILabel *)v).textColor = _contentLabel.textColor;
        }
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

- (void)imageTapped {
    if (_messageImageView.image && [self.delegate respondsToSelector:@selector(messageCell:didTapImage:)]) {
        [self.delegate messageCell:self didTapImage:_messageImageView.image];
    }
}

#pragma mark - ThinkingBlockViewDelegate

- (void)thinkingBlockViewDidToggle:(ThinkingBlockView *)view {
    if ([self.delegate respondsToSelector:@selector(messageCellDidToggleThinking:)]) {
        [self.delegate messageCellDidToggleThinking:self];
    }
}

@end
