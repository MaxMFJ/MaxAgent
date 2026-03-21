#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

// MARK: - 枚举

typedef NS_ENUM(NSInteger, GroupChatStatusType) {
    GroupChatStatusActive,
    GroupChatStatusCompleted,
    GroupChatStatusFailed,
    GroupChatStatusCancelled
};

typedef NS_ENUM(NSInteger, ParticipantRoleType) {
    ParticipantRoleMain,
    ParticipantRoleDuck,
    ParticipantRoleSystem,
    ParticipantRoleMonitor
};

typedef NS_ENUM(NSInteger, GroupMessageTypeValue) {
    GroupMessageTypeText,
    GroupMessageTypeTaskAssign,
    GroupMessageTypeTaskProgress,
    GroupMessageTypeTaskComplete,
    GroupMessageTypeTaskFailed,
    GroupMessageTypeStatusUpdate,
    GroupMessageTypePlan,
    GroupMessageTypeConclusion,
    GroupMessageTypeMonitorReport
};

// MARK: - GroupParticipant

@interface GroupParticipant : NSObject
@property (nonatomic, copy, readonly) NSString *participantId;
@property (nonatomic, copy, readonly) NSString *name;
@property (nonatomic, assign, readonly) ParticipantRoleType role;
@property (nonatomic, copy, nullable, readonly) NSString *duckType;
@property (nonatomic, copy, readonly) NSString *emoji;
@property (nonatomic, assign, readonly) NSTimeInterval joinedAt;

+ (instancetype)participantWithDictionary:(NSDictionary *)dict;
- (NSDictionary *)toDictionary;
@end

// MARK: - GroupMessage

@interface GroupMessage : NSObject
@property (nonatomic, copy, readonly) NSString *msgId;
@property (nonatomic, copy, readonly) NSString *senderId;
@property (nonatomic, copy, readonly) NSString *senderName;
@property (nonatomic, assign, readonly) ParticipantRoleType senderRole;
@property (nonatomic, assign, readonly) GroupMessageTypeValue msgType;
@property (nonatomic, copy, readonly) NSString *content;
@property (nonatomic, copy, readonly) NSArray<NSString *> *mentions;
@property (nonatomic, copy, readonly) NSDictionary *metadata;
@property (nonatomic, assign, readonly) NSTimeInterval timestamp;

+ (instancetype)messageWithDictionary:(NSDictionary *)dict;
- (NSDictionary *)toDictionary;
@end

// MARK: - GroupTaskSummary

@interface GroupTaskSummary : NSObject
@property (nonatomic, assign) NSInteger total;
@property (nonatomic, assign) NSInteger completed;
@property (nonatomic, assign) NSInteger failed;
@property (nonatomic, assign) NSInteger running;
@property (nonatomic, assign) NSInteger pending;

+ (instancetype)summaryWithDictionary:(NSDictionary *)dict;
- (NSDictionary *)toDictionary;
@end

// MARK: - GroupChat

@interface GroupChat : NSObject
@property (nonatomic, copy, readonly) NSString *groupId;
@property (nonatomic, copy) NSString *title;
@property (nonatomic, copy, readonly) NSString *sessionId;
@property (nonatomic, copy, nullable, readonly) NSString *dagId;
@property (nonatomic, assign) GroupChatStatusType status;
@property (nonatomic, strong) NSMutableArray<GroupParticipant *> *participants;
@property (nonatomic, strong) NSMutableArray<GroupMessage *> *messages;
@property (nonatomic, strong) GroupTaskSummary *taskSummary;
@property (nonatomic, assign, readonly) NSTimeInterval createdAt;
@property (nonatomic, assign) NSTimeInterval completedAt;

+ (instancetype)groupChatWithDictionary:(NSDictionary *)dict;
- (void)addMessage:(GroupMessage *)message;
- (void)updateStatus:(GroupChatStatusType)status summary:(GroupTaskSummary *)summary;

+ (GroupChatStatusType)statusFromString:(NSString *)str;
+ (NSString *)stringFromStatus:(GroupChatStatusType)status;

/// 用于本地持久化/恢复（与后端 JSON 字段保持一致）
- (NSDictionary *)toDictionary;

@end

NS_ASSUME_NONNULL_END
