#import "ImageZoomViewController.h"

@interface ImageZoomViewController () <UIScrollViewDelegate>

@property (nonatomic, strong) UIImage *image;
@property (nonatomic, strong) UIScrollView *scrollView;
@property (nonatomic, strong) UIImageView *imageView;
@property (nonatomic, strong) UIButton *closeButton;

@end

@implementation ImageZoomViewController

- (instancetype)initWithImage:(UIImage *)image {
    self = [super initWithNibName:nil bundle:nil];
    if (self) {
        _image = image;
        self.modalPresentationStyle = 0;  // UIModalPresentationStyleFullScreen
        self.modalTransitionStyle = UIModalTransitionStyleCrossDissolve;
    }
    return self;
}

- (void)viewDidLoad {
    [super viewDidLoad];
    
    self.view.backgroundColor = [UIColor blackColor];
    
    _scrollView = [[UIScrollView alloc] init];
    _scrollView.translatesAutoresizingMaskIntoConstraints = NO;
    _scrollView.delegate = self;
    _scrollView.minimumZoomScale = 1.0;
    _scrollView.maximumZoomScale = 4.0;
    _scrollView.showsHorizontalScrollIndicator = NO;
    _scrollView.showsVerticalScrollIndicator = NO;
    _scrollView.backgroundColor = [UIColor blackColor];
    [self.view addSubview:_scrollView];
    
    _imageView = [[UIImageView alloc] initWithImage:_image];
    _imageView.contentMode = UIViewContentModeScaleAspectFit;
    _imageView.userInteractionEnabled = YES;
    [_scrollView addSubview:_imageView];
    
    UITapGestureRecognizer *doubleTap = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(handleDoubleTap:)];
    doubleTap.numberOfTapsRequired = 2;
    [_imageView addGestureRecognizer:doubleTap];
    
    UITapGestureRecognizer *singleTap = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(handleSingleTap:)];
    singleTap.numberOfTapsRequired = 1;
    [singleTap requireGestureRecognizerToFail:doubleTap];
    [self.view addGestureRecognizer:singleTap];
    
    _closeButton = [UIButton buttonWithType:UIButtonTypeSystem];
    _closeButton.translatesAutoresizingMaskIntoConstraints = NO;
    [_closeButton setImage:[UIImage systemImageNamed:@"xmark.circle.fill"] forState:UIControlStateNormal];
    _closeButton.tintColor = [UIColor whiteColor];
    _closeButton.contentVerticalAlignment = UIControlContentVerticalAlignmentCenter;
    _closeButton.contentHorizontalAlignment = UIControlContentHorizontalAlignmentCenter;
    [_closeButton addTarget:self action:@selector(closeTapped) forControlEvents:UIControlEventTouchUpInside];
    [self.view addSubview:_closeButton];
    
    [NSLayoutConstraint activateConstraints:@[
        [_scrollView.topAnchor constraintEqualToAnchor:self.view.topAnchor],
        [_scrollView.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [_scrollView.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [_scrollView.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor],
        
        [_closeButton.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor constant:8],
        [_closeButton.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor constant:-16],
        [_closeButton.widthAnchor constraintEqualToConstant:44],
        [_closeButton.heightAnchor constraintEqualToConstant:44]
    ]];
}

- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    [self updateImageSize];
}

- (void)updateImageSize {
    if (!_image) return;
    
    CGSize scrollSize = _scrollView.bounds.size;
    CGSize imageSize = _image.size;
    
    CGFloat widthRatio = scrollSize.width / imageSize.width;
    CGFloat heightRatio = scrollSize.height / imageSize.height;
    CGFloat scale = MIN(widthRatio, heightRatio);
    
    CGSize fitSize = CGSizeMake(imageSize.width * scale, imageSize.height * scale);
    
    _imageView.frame = CGRectMake(
        (scrollSize.width - fitSize.width) / 2,
        (scrollSize.height - fitSize.height) / 2,
        fitSize.width,
        fitSize.height
    );
    
    _scrollView.contentSize = fitSize;
}

#pragma mark - UIScrollViewDelegate

- (UIView *)viewForZoomingInScrollView:(UIScrollView *)scrollView {
    return _imageView;
}

- (void)scrollViewDidZoom:(UIScrollView *)scrollView {
    CGRect frame = _imageView.frame;
    CGSize scrollSize = scrollView.bounds.size;
    
    if (frame.size.width < scrollSize.width) {
        frame.origin.x = (scrollSize.width - frame.size.width) / 2;
    } else {
        frame.origin.x = 0;
    }
    
    if (frame.size.height < scrollSize.height) {
        frame.origin.y = (scrollSize.height - frame.size.height) / 2;
    } else {
        frame.origin.y = 0;
    }
    
    _imageView.frame = frame;
}

#pragma mark - Actions

- (void)handleSingleTap:(UITapGestureRecognizer *)recognizer {
    [self dismissViewControllerAnimated:YES completion:nil];
}

- (void)handleDoubleTap:(UITapGestureRecognizer *)recognizer {
    if (_scrollView.zoomScale > 1.0) {
        [_scrollView setZoomScale:1.0 animated:YES];
    } else {
        [_scrollView setZoomScale:2.0 animated:YES];
    }
}

- (void)closeTapped {
    [self dismissViewControllerAnimated:YES completion:nil];
}

@end
