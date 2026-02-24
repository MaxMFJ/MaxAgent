import Foundation

enum MessageRole: String, Codable {
    case user
    case assistant
    case system
    case tool
}

struct MessageAttachment: Codable, Equatable {
    let type: AttachmentType
    let data: String
    let mimeType: String?
    let fileName: String?
    
    enum AttachmentType: String, Codable {
        case base64Image = "base64_image"
        case localFile = "local_file"
        case url = "url"
    }
    
    init(type: AttachmentType, data: String, mimeType: String? = nil, fileName: String? = nil) {
        self.type = type
        self.data = data
        self.mimeType = mimeType
        self.fileName = fileName
    }
    
    static func fromBase64(_ base64: String, mimeType: String = "image/png") -> MessageAttachment {
        return MessageAttachment(type: .base64Image, data: base64, mimeType: mimeType)
    }
    
    static func fromLocalPath(_ path: String) -> MessageAttachment {
        return MessageAttachment(type: .localFile, data: path)
    }
    
    static func fromURL(_ url: String) -> MessageAttachment {
        return MessageAttachment(type: .url, data: url)
    }
}

struct TokenUsage: Codable, Equatable {
    var promptTokens: Int
    var completionTokens: Int
    var totalTokens: Int
    
    init(promptTokens: Int = 0, completionTokens: Int = 0, totalTokens: Int = 0) {
        self.promptTokens = promptTokens
        self.completionTokens = completionTokens
        self.totalTokens = totalTokens
    }
    
    mutating func add(_ other: TokenUsage) {
        self.promptTokens += other.promptTokens
        self.completionTokens += other.completionTokens
        self.totalTokens += other.totalTokens
    }
    
    var formatted: String {
        return "\(totalTokens) tokens"
    }
}

struct Message: Identifiable, Codable, Equatable {
    let id: UUID
    let role: MessageRole
    var content: String
    let timestamp: Date
    var toolCalls: [ToolCall]?
    var isStreaming: Bool
    var modelName: String?
    var attachments: [MessageAttachment]?
    var tokenUsage: TokenUsage?
    
    init(
        id: UUID = UUID(),
        role: MessageRole,
        content: String,
        timestamp: Date = Date(),
        toolCalls: [ToolCall]? = nil,
        isStreaming: Bool = false,
        modelName: String? = nil,
        attachments: [MessageAttachment]? = nil,
        tokenUsage: TokenUsage? = nil
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.timestamp = timestamp
        self.toolCalls = toolCalls
        self.isStreaming = isStreaming
        self.modelName = modelName
        self.attachments = attachments
        self.tokenUsage = tokenUsage
    }
    
    static func == (lhs: Message, rhs: Message) -> Bool {
        lhs.id == rhs.id &&
        lhs.content == rhs.content &&
        lhs.isStreaming == rhs.isStreaming &&
        lhs.attachments == rhs.attachments &&
        lhs.tokenUsage == rhs.tokenUsage
    }
}

struct ToolCall: Identifiable, Codable {
    let id: String
    let name: String
    let arguments: [String: AnyCodable]
    var result: ToolResult?
}

struct ToolResult: Codable {
    let success: Bool
    let output: String
}

struct AnyCodable: Codable {
    let value: Any
    
    init(_ value: Any) {
        self.value = value
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        
        if let string = try? container.decode(String.self) {
            value = string
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let bool = try? container.decode(Bool.self) {
            value = bool
        } else if let array = try? container.decode([AnyCodable].self) {
            value = array.map { $0.value }
        } else if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues { $0.value }
        } else {
            value = NSNull()
        }
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        
        switch value {
        case let string as String:
            try container.encode(string)
        case let int as Int:
            try container.encode(int)
        case let double as Double:
            try container.encode(double)
        case let bool as Bool:
            try container.encode(bool)
        case let array as [Any]:
            try container.encode(array.map { AnyCodable($0) })
        case let dict as [String: Any]:
            try container.encode(dict.mapValues { AnyCodable($0) })
        default:
            try container.encodeNil()
        }
    }
}

struct Conversation: Identifiable, Codable, Equatable {
    let id: UUID
    var title: String
    var messages: [Message]
    let createdAt: Date
    var updatedAt: Date
    
    init(
        id: UUID = UUID(),
        title: String = "新对话",
        messages: [Message] = [],
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.messages = messages
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
    
    static func == (lhs: Conversation, rhs: Conversation) -> Bool {
        lhs.id == rhs.id &&
        lhs.messages == rhs.messages &&
        lhs.updatedAt == rhs.updatedAt
    }
}

struct ToolDefinition: Codable, Identifiable {
    var id: String { name }
    let name: String
    let description: String
    let parameters: [String: AnyCodable]
}

struct BackendConfig: Codable {
    let provider: String
    let model: String
    let baseUrl: String?
    let hasApiKey: Bool
    
    enum CodingKeys: String, CodingKey {
        case provider
        case model
        case baseUrl = "base_url"
        case hasApiKey = "has_api_key"
    }
}

struct SmtpConfig: Codable {
    let smtpServer: String
    let smtpPort: Int
    let smtpUser: String
    let configured: Bool
    
    enum CodingKeys: String, CodingKey {
        case smtpServer = "smtp_server"
        case smtpPort = "smtp_port"
        case smtpUser = "smtp_user"
        case configured
    }
}

// MARK: - Autonomous Mode Models

struct ExecutionLogEntry: Identifiable {
    let id = UUID()
    let timestamp: Date
    let level: String
    let message: String
    let toolName: String
}

struct ActionLogEntry: Identifiable {
    let id = UUID()
    let actionId: String
    let actionType: String
    let reasoning: String
    let status: ActionStatus
    let output: String?
    let error: String?
    let timestamp: Date
    let iteration: Int
    
    enum ActionStatus: String {
        case pending = "pending"
        case executing = "executing"
        case success = "success"
        case failed = "failed"
    }
}

struct TaskProgress: Identifiable {
    let id: String
    let taskDescription: String
    var status: TaskStatus
    var currentIteration: Int
    var totalActions: Int
    var successfulActions: Int
    var failedActions: Int
    var startTime: Date
    var endTime: Date?
    var summary: String?
    
    enum TaskStatus: String {
        case running = "running"
        case completed = "completed"
        case failed = "failed"
    }
    
    var duration: TimeInterval {
        let end = endTime ?? Date()
        return end.timeIntervalSince(startTime)
    }
    
    var formattedDuration: String {
        let seconds = Int(duration)
        if seconds < 60 {
            return "\(seconds)s"
        } else if seconds < 3600 {
            return "\(seconds / 60)m \(seconds % 60)s"
        } else {
            return "\(seconds / 3600)h \(seconds % 3600 / 60)m"
        }
    }
}
