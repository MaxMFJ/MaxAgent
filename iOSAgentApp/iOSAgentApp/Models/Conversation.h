#import <Foundation/Foundation.h>
#import "Message.h"

NS_ASSUME_NONNULL_BEGIN

@interface Conversation : NSObject <NSCoding, NSSecureCoding>

@property (nonatomic, copy, readonly) NSString *conversationId;
@property (nonatomic, copy) NSString *title;
@property (nonatomic, strong) NSMutableArray<Message *> *messages;
@property (nonatomic, strong) NSDate *createdAt;
@property (nonatomic, strong) NSDate *updatedAt;

- (instancetype)init;
- (instancetype)initWithId:(NSString *)conversationId;

@end

NS_ASSUME_NONNULL_END
