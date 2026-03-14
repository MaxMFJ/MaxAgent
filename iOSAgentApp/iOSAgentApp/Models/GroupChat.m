#import "GroupChat.h"

// MARK: - Helper

static NSString *_SafeString(id value) {
    if ([value isKindOfClass:[NSString class]]) return value;
    return @"";
}

static ParticipantRoleType _RoleFromString(NSString *str) {
    if ([str isEqualToString:@"duck"]) return ParticipantRoleDuck;
    if ([str isEqualToString:@"system"]) return ParticipantRoleSystem;
    return ParticipantRoleMain;
}

static GroupMessageTypeValue _MsgTypeFromString(NSString *str) {
    if ([str isEqualToString:@"task_assign"]) return GroupMessageTypeTaskAssign;
    if ([str isEqualToString:@"task_progress"]) return GroupMessageTypeTaskProgress;
    if ([str isEqualToString:@"task_complete"]) return GroupMessageTypeTaskComplete;
    if ([str isEqualToString:@"task_failed"]) return GroupMessageTypeTaskFailed;
    if ([str isEqualToString:@"status_update"]) return GroupMessageTypeStatusUpdate;
    if ([str isEqualToString:@"plan"]) return GroupMessageTypePlan;
    if ([str isEqualToString:@"conclusion"]) return GroupMessageTypeConclusion;
    return GroupMessageTypeText;
}

// MARK: - GroupParticipant

@implementation GroupParticipant

+ (instancetype)participantWithDictionary:(NSDictionary *)dict {
    GroupParticipant *p = [[GroupParticipant alloc] init];
    if (p) {
        p->_participantId = _SafeString(dict[@"participant_id"]);
        p->_name = _SafeString(dict[@"name"]);
        p->_role = _RoleFromString(_SafeString(dict[@"role"]));
        p->_duckType = [dict[@"duck_type"] isKindOfClass:[NSString class]] ? dict[@"duck_type"] : nil;
        p->_emoji = _SafeString(dict[@"emoji"]);
        p->_joinedAt = [dict[@"joined_at"] doubleValue];
    }
    return p;
}

@end

// MARK: - GroupMessage

@implementation GroupMessage

+ (instancetype)messageWithDictionary:(NSDictionary *)dict {
    GroupMessage *m = [[GroupMessage alloc] init];
    if (m) {
        m->_msgId = _SafeString(dict[@"msg_id"]);
        m->_senderId = _SafeString(dict[@"sender_id"]);
        m->_senderName = _SafeString(dict[@"sender_name"]);
        m->_senderRole = _RoleFromString(_SafeString(dict[@"sender_role"]));
        m->_msgType = _MsgTypeFromString(_SafeString(dict[@"msg_type"]));
        m->_content = _SafeString(dict[@"content"]);
        m->_mentions = [dict[@"mentions"] isKindOfClass:[NSArray class]] ? dict[@"mentions"] : @[];
        m->_metadata = [dict[@"metadata"] isKindOfClass:[NSDictionary class]] ? dict[@"metadata"] : @{};
        m->_timestamp = [dict[@"timestamp"] doubleValue];
    }
    return m;
}

@end

// MARK: - GroupTaskSummary

@implementation GroupTaskSummary

+ (instancetype)summaryWithDictionary:(NSDictionary *)dict {
    GroupTaskSummary *s = [[GroupTaskSummary alloc] init];
    if (s) {
        s.total = [dict[@"total"] integerValue];
        s.completed = [dict[@"completed"] integerValue];
        s.failed = [dict[@"failed"] integerValue];
        s.running = [dict[@"running"] integerValue];
        s.pending = [dict[@"pending"] integerValue];
    }
    return s;
}

@end

// MARK: - GroupChat

@implementation GroupChat

+ (instancetype)groupChatWithDictionary:(NSDictionary *)dict {
    GroupChat *g = [[GroupChat alloc] init];
    if (g) {
        g->_groupId = _SafeString(dict[@"group_id"]);
        g.title = _SafeString(dict[@"title"]);
        g->_sessionId = _SafeString(dict[@"session_id"]);
        g->_dagId = [dict[@"dag_id"] isKindOfClass:[NSString class]] ? dict[@"dag_id"] : nil;
        g.status = [GroupChat statusFromString:_SafeString(dict[@"status"])];
        g->_createdAt = [dict[@"created_at"] doubleValue];
        g.completedAt = [dict[@"completed_at"] doubleValue];

        // participants
        NSMutableArray *parts = [NSMutableArray array];
        NSArray *pArr = dict[@"participants"];
        if ([pArr isKindOfClass:[NSArray class]]) {
            for (NSDictionary *pd in pArr) {
                [parts addObject:[GroupParticipant participantWithDictionary:pd]];
            }
        }
        g.participants = parts;

        // messages
        NSMutableArray *msgs = [NSMutableArray array];
        NSArray *mArr = dict[@"messages"];
        if ([mArr isKindOfClass:[NSArray class]]) {
            for (NSDictionary *md in mArr) {
                [msgs addObject:[GroupMessage messageWithDictionary:md]];
            }
        }
        g.messages = msgs;

        // task_summary
        NSDictionary *tsDict = dict[@"task_summary"];
        g.taskSummary = [tsDict isKindOfClass:[NSDictionary class]]
            ? [GroupTaskSummary summaryWithDictionary:tsDict]
            : [[GroupTaskSummary alloc] init];
    }
    return g;
}

- (void)addMessage:(GroupMessage *)message {
    [self.messages addObject:message];
}

- (void)updateStatus:(GroupChatStatusType)status summary:(GroupTaskSummary *)summary {
    self.status = status;
    self.taskSummary = summary;
}

+ (GroupChatStatusType)statusFromString:(NSString *)str {
    if ([str isEqualToString:@"completed"]) return GroupChatStatusCompleted;
    if ([str isEqualToString:@"failed"]) return GroupChatStatusFailed;
    if ([str isEqualToString:@"cancelled"]) return GroupChatStatusCancelled;
    return GroupChatStatusActive;
}

+ (NSString *)stringFromStatus:(GroupChatStatusType)status {
    switch (status) {
        case GroupChatStatusActive: return @"active";
        case GroupChatStatusCompleted: return @"completed";
        case GroupChatStatusFailed: return @"failed";
        case GroupChatStatusCancelled: return @"cancelled";
    }
}

@end
