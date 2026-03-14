import Foundation

// MARK: - GroupChat 模型（多 Agent 协作群聊）

enum GroupChatStatus: String, Codable {
    case active
    case completed
    case failed
    case cancelled
}

enum ParticipantRole: String, Codable {
    case main
    case duck
    case system
}

enum GroupMessageType: String, Codable {
    case text
    case taskAssign = "task_assign"
    case taskProgress = "task_progress"
    case taskComplete = "task_complete"
    case taskFailed = "task_failed"
    case statusUpdate = "status_update"
    case plan
    case conclusion
}

struct GroupParticipant: Codable, Identifiable {
    let participantId: String
    let name: String
    let role: ParticipantRole
    let duckType: String?
    let emoji: String
    let joinedAt: Double

    var id: String { participantId }

    enum CodingKeys: String, CodingKey {
        case participantId = "participant_id"
        case name, role
        case duckType = "duck_type"
        case emoji
        case joinedAt = "joined_at"
    }
}

struct GroupMessage: Codable, Identifiable {
    let msgId: String
    let senderId: String
    let senderName: String
    let senderRole: ParticipantRole
    let msgType: GroupMessageType
    let content: String
    let mentions: [String]
    let metadata: [String: AnyCodable]
    let timestamp: Double

    var id: String { msgId }

    enum CodingKeys: String, CodingKey {
        case msgId = "msg_id"
        case senderId = "sender_id"
        case senderName = "sender_name"
        case senderRole = "sender_role"
        case msgType = "msg_type"
        case content, mentions, metadata, timestamp
    }
}

struct GroupTaskSummary: Codable {
    var total: Int?
    var completed: Int?
    var failed: Int?
    var running: Int?
    var pending: Int?
}

struct GroupChat: Codable, Identifiable {
    let groupId: String
    var title: String
    let sessionId: String
    let dagId: String?
    var status: GroupChatStatus
    var participants: [GroupParticipant]
    var messages: [GroupMessage]
    var taskSummary: GroupTaskSummary
    let createdAt: Double
    var completedAt: Double?

    var id: String { groupId }

    enum CodingKeys: String, CodingKey {
        case groupId = "group_id"
        case title
        case sessionId = "session_id"
        case dagId = "dag_id"
        case status, participants, messages
        case taskSummary = "task_summary"
        case createdAt = "created_at"
        case completedAt = "completed_at"
    }

    mutating func addMessage(_ message: GroupMessage) {
        messages.append(message)
    }

    mutating func updateStatus(_ newStatus: GroupChatStatus, summary: GroupTaskSummary) {
        status = newStatus
        taskSummary = summary
    }
}
