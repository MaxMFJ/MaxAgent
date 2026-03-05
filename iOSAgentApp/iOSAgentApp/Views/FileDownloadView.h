#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@class FileDownloadView;

@protocol FileDownloadViewDelegate <NSObject>
@optional
/// 用户点击了预览/打开文件
- (void)fileDownloadView:(FileDownloadView *)view didRequestPreviewForPath:(NSString *)path;
@end

/// 文件下载卡片：在聊天消息中显示可下载的文件路径
/// 支持通过后端 /files/download API 下载到 iOS 设备
@interface FileDownloadView : UIView

@property (nonatomic, weak, nullable) id<FileDownloadViewDelegate> delegate;
@property (nonatomic, copy, readonly) NSString *filePath;

- (instancetype)initWithFilePath:(NSString *)filePath serverBaseURL:(NSString *)serverBaseURL;

/// 检测文本是否包含文件路径，返回检测到的路径数组
+ (NSArray<NSString *> *)detectFilePathsInText:(NSString *)text;

@end

NS_ASSUME_NONNULL_END
