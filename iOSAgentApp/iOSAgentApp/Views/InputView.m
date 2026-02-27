#import "InputView.h"

@interface InputView () <UITextViewDelegate>

@property (nonatomic, strong) UITextView *textView;
@property (nonatomic, strong) UIButton *sendButton;
@property (nonatomic, strong) UIButton *voiceButton;
@property (nonatomic, strong) UIButton *autonomousButton;
@property (nonatomic, strong) UILabel *placeholderLabel;
@property (nonatomic, strong) UIView *containerView;
@property (nonatomic, strong) NSLayoutConstraint *textViewHeightConstraint;

@end

@implementation InputView

- (instancetype)initWithFrame:(CGRect)frame {
    self = [super initWithFrame:frame];
    if (self) {
        [self setupUI];
        _enabled = YES;
        _loading = NO;
        _voiceInputActive = NO;
    }
    return self;
}

- (void)setupUI {
    self.backgroundColor = [UIColor systemBackgroundColor];
    
    UIView *separator = [[UIView alloc] init];
    separator.translatesAutoresizingMaskIntoConstraints = NO;
    separator.backgroundColor = [UIColor separatorColor];
    [self addSubview:separator];
    
    _voiceButton = [UIButton buttonWithType:UIButtonTypeSystem];
    _voiceButton.translatesAutoresizingMaskIntoConstraints = NO;
    [_voiceButton setImage:[UIImage systemImageNamed:@"mic.fill" withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:22 weight:UIFontWeightMedium]] forState:UIControlStateNormal];
    [_voiceButton setImage:[UIImage systemImageNamed:@"mic.fill" withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:22 weight:UIFontWeightMedium]] forState:UIControlStateSelected];
    _voiceButton.tintColor = [UIColor systemGrayColor];
    [_voiceButton addTarget:self action:@selector(voiceButtonTapped) forControlEvents:UIControlEventTouchUpInside];
    [self addSubview:_voiceButton];
    
    _autonomousButton = [UIButton buttonWithType:UIButtonTypeSystem];
    _autonomousButton.translatesAutoresizingMaskIntoConstraints = NO;
    [_autonomousButton setImage:[UIImage systemImageNamed:@"robot" withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:22 weight:UIFontWeightMedium]] forState:UIControlStateNormal];
    _autonomousButton.tintColor = [UIColor systemGrayColor];
    [_autonomousButton addTarget:self action:@selector(autonomousButtonTapped) forControlEvents:UIControlEventTouchUpInside];
    [self addSubview:_autonomousButton];
    
    _containerView = [[UIView alloc] init];
    _containerView.translatesAutoresizingMaskIntoConstraints = NO;
    _containerView.backgroundColor = [UIColor secondarySystemBackgroundColor];
    _containerView.layer.cornerRadius = 20;
    _containerView.clipsToBounds = YES;
    [self addSubview:_containerView];
    
    _textView = [[UITextView alloc] init];
    _textView.translatesAutoresizingMaskIntoConstraints = NO;
    _textView.font = [UIFont systemFontOfSize:16];
    _textView.backgroundColor = [UIColor clearColor];
    _textView.delegate = self;
    _textView.scrollEnabled = NO;
    [_containerView addSubview:_textView];
    
    _placeholderLabel = [[UILabel alloc] init];
    _placeholderLabel.translatesAutoresizingMaskIntoConstraints = NO;
    _placeholderLabel.text = NSLocalizedString(@"message_placeholder", nil);
    _placeholderLabel.font = [UIFont systemFontOfSize:16];
    _placeholderLabel.textColor = [UIColor placeholderTextColor];
    [_containerView addSubview:_placeholderLabel];
    
    _sendButton = [UIButton buttonWithType:UIButtonTypeSystem];
    _sendButton.translatesAutoresizingMaskIntoConstraints = NO;
    UIImage *sendImage = [UIImage systemImageNamed:@"arrow.up.circle.fill" withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:32 weight:UIFontWeightMedium]];
    [_sendButton setImage:sendImage forState:UIControlStateNormal];
    _sendButton.tintColor = [UIColor systemBlueColor];
    [_sendButton addTarget:self action:@selector(sendButtonTapped) forControlEvents:UIControlEventTouchUpInside];
    _sendButton.enabled = NO;
    [self addSubview:_sendButton];
    
    _textViewHeightConstraint = [_textView.heightAnchor constraintEqualToConstant:36];
    
    [NSLayoutConstraint activateConstraints:@[
        [separator.topAnchor constraintEqualToAnchor:self.topAnchor],
        [separator.leadingAnchor constraintEqualToAnchor:self.leadingAnchor],
        [separator.trailingAnchor constraintEqualToAnchor:self.trailingAnchor],
        [separator.heightAnchor constraintEqualToConstant:0.5],
        
        [_voiceButton.leadingAnchor constraintEqualToAnchor:self.leadingAnchor constant:12],
        [_voiceButton.centerYAnchor constraintEqualToAnchor:_containerView.centerYAnchor],
        [_voiceButton.widthAnchor constraintEqualToConstant:40],
        [_voiceButton.heightAnchor constraintEqualToConstant:40],
        
        [_containerView.topAnchor constraintEqualToAnchor:self.topAnchor constant:8],
        [_containerView.leadingAnchor constraintEqualToAnchor:_voiceButton.trailingAnchor constant:4],
        [_containerView.bottomAnchor constraintEqualToAnchor:self.safeAreaLayoutGuide.bottomAnchor constant:-8],
        
        [_autonomousButton.leadingAnchor constraintEqualToAnchor:_containerView.trailingAnchor constant:4],
        [_autonomousButton.centerYAnchor constraintEqualToAnchor:_containerView.centerYAnchor],
        [_autonomousButton.widthAnchor constraintEqualToConstant:40],
        [_autonomousButton.heightAnchor constraintEqualToConstant:40],
        
        [_sendButton.leadingAnchor constraintEqualToAnchor:_autonomousButton.trailingAnchor constant:4],
        [_sendButton.trailingAnchor constraintEqualToAnchor:self.trailingAnchor constant:-12],
        [_sendButton.bottomAnchor constraintEqualToAnchor:_containerView.bottomAnchor],
        [_sendButton.widthAnchor constraintEqualToConstant:40],
        [_sendButton.heightAnchor constraintEqualToConstant:40],
        
        [_textView.topAnchor constraintEqualToAnchor:_containerView.topAnchor constant:2],
        [_textView.leadingAnchor constraintEqualToAnchor:_containerView.leadingAnchor constant:12],
        [_textView.trailingAnchor constraintEqualToAnchor:_containerView.trailingAnchor constant:-12],
        [_textView.bottomAnchor constraintEqualToAnchor:_containerView.bottomAnchor constant:-2],
        _textViewHeightConstraint,
        
        [_placeholderLabel.leadingAnchor constraintEqualToAnchor:_textView.leadingAnchor constant:5],
        [_placeholderLabel.centerYAnchor constraintEqualToAnchor:_textView.centerYAnchor]
    ]];
}

- (void)voiceButtonTapped {
    if ([self.delegate respondsToSelector:@selector(inputViewDidRequestVoiceInput:)]) {
        [self.delegate inputViewDidRequestVoiceInput:self];
    }
}

- (void)autonomousButtonTapped {
    NSString *text = [self.textView.text stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    if (text.length > 0 && [self.delegate respondsToSelector:@selector(inputView:didRequestSendAsAutonomousTask:)]) {
        [self.delegate inputView:self didRequestSendAsAutonomousTask:text];
    }
}

- (void)sendButtonTapped {
    if (self.loading) {
        if ([self.delegate respondsToSelector:@selector(inputViewDidRequestStop:)]) {
            [self.delegate inputViewDidRequestStop:self];
        }
        return;
    }
    NSString *text = [self.textView.text stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    if (text.length > 0 && self.enabled) {
        if ([self.delegate respondsToSelector:@selector(inputView:didSendMessage:)]) {
            [self.delegate inputView:self didSendMessage:text];
        }
    }
}

- (void)clearText {
    self.textView.text = @"";
    [self textViewDidChange:self.textView];
}

- (void)setText:(NSString *)text {
    self.textView.text = text ?: @"";
    [self textViewDidChange:self.textView];
}

- (void)setEnabled:(BOOL)enabled {
    _enabled = enabled;
    self.textView.editable = enabled;
    [self updateSendButton];
    self.alpha = enabled ? 1.0 : 0.6;
}

- (void)setLoading:(BOOL)loading {
    _loading = loading;
    [self updateSendButton];
}

- (void)updateSendButton {
    if (self.loading) {
        self.sendButton.enabled = YES;
        [self.sendButton setImage:[UIImage systemImageNamed:@"stop.circle.fill" withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:32 weight:UIFontWeightMedium]] forState:UIControlStateNormal];
        self.sendButton.tintColor = [UIColor systemRedColor];
    } else {
        self.sendButton.enabled = self.enabled && self.textView.text.length > 0;
        [self.sendButton setImage:[UIImage systemImageNamed:@"arrow.up.circle.fill" withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:32 weight:UIFontWeightMedium]] forState:UIControlStateNormal];
        self.sendButton.tintColor = [UIColor systemBlueColor];
    }
    self.autonomousButton.enabled = self.enabled && self.textView.text.length > 0 && !self.loading;
}

- (void)setVoiceInputActive:(BOOL)voiceInputActive {
    _voiceInputActive = voiceInputActive;
    self.voiceButton.selected = voiceInputActive;
    self.voiceButton.tintColor = voiceInputActive ? [UIColor systemRedColor] : [UIColor systemGrayColor];
}

#pragma mark - UITextViewDelegate

- (void)textViewDidChange:(UITextView *)textView {
    self.placeholderLabel.hidden = textView.text.length > 0;
    [self updateSendButton];
    
    CGFloat maxHeight = 120;
    CGSize sizeThatFits = [textView sizeThatFits:CGSizeMake(textView.frame.size.width, CGFLOAT_MAX)];
    CGFloat newHeight = MIN(MAX(sizeThatFits.height, 36), maxHeight);
    
    if (self.textViewHeightConstraint.constant != newHeight) {
        self.textViewHeightConstraint.constant = newHeight;
        textView.scrollEnabled = newHeight >= maxHeight;
        [self layoutIfNeeded];
    }
}

@end
