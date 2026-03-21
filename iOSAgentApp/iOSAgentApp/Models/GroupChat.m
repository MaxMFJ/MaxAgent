#import "GroupChat.h"

// MARK: - Helper

static NSString *_SafeString(id value) {
    if ([value isKindOfClass:[NSString class]]) return value;
    return @"";
}

/// 将对象递归清洗为可 JSON 序列化类型（NSString/NSNumber/NSArray/NSDictionary/NSNull）
static id _SanitizeJSONValue(id value) {
    if (!value || value == (id)kCFNull) return [NSNull null];
    if ([value isKindOfClass:[NSString class]] || [value isKindOfClass:[NSNumber class]]) return value;
    if ([value isKindOfClass:[NSArray class]]) {
        NSMutableArray *arr = [NSMutableArray array];
        for (id v in (NSArray *)value) { [arr addObject:_SanitizeJSONValue(v) ?: [NSNull null]]; }
        return arr;
    }
    if ([value isKindOfClass:[NSDictionary class]]) {
        NSMutableDictionary *dict = [NSMutableDictionary dictionary];
        [(NSDictionary *)value enumerateKeysAndObjectsUsingBlock:^(id  _Nonnull key, id  _Nonnull obj, BOOL * _Nonnull stop) {
            NSString *k = [key isKindOfClass:[NSString class]] ? key : [key description];
            dict[k] = _SanitizeJSONValue(obj) ?: [NSNull null];
        }];
        return dict;
    }
    // 兜底：转字符串避免 JSON 序列化崩溃
    return [[value description] copy];
}

static ParticipantRoleType _RoleFromString(NSString *str) {
    if ([str isEqualToString:@"duck"]) return ParticipantRoleDuck;
    if ([str isEqualToString:@"system"]) return ParticipantRoleSystem;
    if ([str isEqualToString:@"monitor"]) return ParticipantRoleMonitor;
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
    if ([str isEqualToString:@"monitor_report"]) return GroupMessageTypeMonitorReport;
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

- (NSDictionary *)toDictionary {
    NSMutableDictionary *d = [NSMutableDictionary dictionary];
    d[@"participant_id"] = self.participantId ?: @"";
    d[@"name"] = self.name ?: @"";
    switch (self.role) {
        case ParticipantRoleDuck: d[@"role"] = @"duck"; break;
        case ParticipantRoleSystem: d[@"role"] = @"system"; break;
        case ParticipantRoleMonitor: d[@"role"] = @"monitor"; break;
        case ParticipantRoleMain: default: d[@"role"] = @"main"; break;
    }
    if (self.duckType) d[@"duck_type"] = self.duckType;
    d[@"emoji"] = self.emoji ?: @"";
    d[@"joined_at"] = @(self.joinedAt);
    return d;
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

- (NSDictionary *)toDictionary {
    NSMutableDictionary *d = [NSMutableDictionary dictionary];
    d[@"msg_id"] = self.msgId ?: @"";
    d[@"sender_id"] = self.senderId ?: @"";
    d[@"sender_name"] = self.senderName ?: @"";
    switch (self.senderRole) {
        case ParticipantRoleDuck: d[@"sender_role"] = @"duck"; break;
        case ParticipantRoleSystem: d[@"sender_role"] = @"system"; break;
        case ParticipantRoleMonitor: d[@"sender_role"] = @"monitor"; break;
        case ParticipantRoleMain: default: d[@"sender_role"] = @"main"; break;
    }
    switch (self.msgType) {
        case GroupMessageTypeTaskAssign: d[@"msg_type"] = @"task_assign"; break;
        case GroupMessageTypeTaskProgress: d[@"msg_type"] = @"task_progress"; break;
        case GroupMessageTypeTaskComplete: d[@"msg_type"] = @"task_complete"; break;
        case GroupMessageTypeTaskFailed: d[@"msg_type"] = @"task_failed"; break;
        case GroupMessageTypeStatusUpdate: d[@"msg_type"] = @"status_update"; break;
        case GroupMessageTypePlan: d[@"msg_type"] = @"plan"; break;
        case GroupMessageTypeConclusion: d[@"msg_type"] = @"conclusion"; break;
        case GroupMessageTypeMonitorReport: d[@"msg_type"] = @"monitor_report"; break;
        case GroupMessageTypeText: default: d[@"msg_type"] = @"text"; break;
    }
    d[@"content"] = self.content ?: @"";
    d[@"mentions"] = self.mentions ?: @[];
    d[@"metadata"] = _SanitizeJSONValue(self.metadata ?: @{}) ?: @{};
    d[@"timestamp"] = @(self.timestamp);
    return d;
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

- (NSDictionary *)toDictionary {
    return @{
        @"total": @(self.total),
        @"completed": @(self.completed),
        @"failed": @(self.failed),
        @"running": @(self.running),
        @"pending": @(self.pending),
    };
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

- (NSDictionary *)toDictionary {
    NSMutableArray *parts = [NSMutableArray array];
    for (GroupParticipant *p in self.participants ?: @[]) {
        if ([p respondsToSelector:@selector(toDictionary)]) {
            [parts addObject:[p toDictionary]];
        }
    }

    NSMutableArray *msgs = [NSMutableArray array];
    for (GroupMessage *m in self.messages ?: @[]) {
        if ([m respondsToSelector:@selector(toDictionary)]) {
            [msgs addObject:[m toDictionary]];
        }
    }

    NSMutableDictionary *d = [NSMutableDictionary dictionary];
    d[@"group_id"] = self.groupId ?: @"";
    d[@"title"] = self.title ?: @"";
    d[@"session_id"] = self.sessionId ?: @"";
    if (self.dagId) d[@"dag_id"] = self.dagId;
    d[@"status"] = [GroupChat stringFromStatus:self.status] ?: @"active";
    d[@"participants"] = parts;
    d[@"messages"] = msgs;
    d[@"task_summary"] = [self.taskSummary toDictionary] ?: @{};
    d[@"created_at"] = @(self.createdAt);
    // iOS 端用 0 表示无 completed_at，持久化时保持一致
    if (self.completedAt > 0) d[@"completed_at"] = @(self.completedAt);
    return d;
}

@end
