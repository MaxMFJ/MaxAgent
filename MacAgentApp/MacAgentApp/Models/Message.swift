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

/// 气泡展示类型，用于可扩展的多种气泡内容（文本/Markdown、工具调用、卡片等）
enum MessageDisplayKind: Equatable {
    case standard
    case toolCall  // 后续可扩展：展示工具调用列表、结果等
    // 可继续扩展：.card, .codeOnly 等
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
    
    /// 由内容/附件/工具调用推导展示类型，便于气泡内按类型渲染不同 UI
    var displayKind: MessageDisplayKind {
        if let calls = toolCalls, !calls.isEmpty { return .toolCall }
        return .standard
    }
    
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
    let category: String?
    let source: String?  // "system" or "generated"
    
    var isGenerated: Bool {
        source == "generated"
    }
    
    enum CodingKeys: String, CodingKey {
        case name, description, parameters, category, source
    }
    
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = try c.decode(String.self, forKey: .name)
        description = try c.decode(String.self, forKey: .description)
        parameters = try c.decodeIfPresent([String: AnyCodable].self, forKey: .parameters) ?? [:]
        category = try c.decodeIfPresent(String.self, forKey: .category)
        source = try c.decodeIfPresent(String.self, forKey: .source)
    }
}

/// 后端返回的已配置云端提供商，供“远程回退策略”下拉展示
struct CloudProviderConfigured: Codable {
    let provider: String
    let baseUrl: String?
    let model: String
    let hasApiKey: Bool

    enum CodingKeys: String, CodingKey {
        case provider
        case baseUrl = "base_url"
        case model
        case hasApiKey = "has_api_key"
    }
}

struct BackendConfig: Codable {
    let provider: String
    let model: String
    let baseUrl: String?
    let hasApiKey: Bool
    /// 是否启用 LangChain 兼容（对话）
    let langchainCompat: Bool
    /// 后端是否已安装 LangChain 依赖（未安装时开关不可选，需先点「安装」）
    let langchainInstalled: Bool
    /// 用户显式选择的远程回退提供商（newapi/deepseek/openai），空则用默认 DeepSeek
    let remoteFallbackProvider: String?
    /// 已配置的云端提供商列表，用于“远程回退策略”下拉
    let cloudProvidersConfigured: [CloudProviderConfigured]?

    enum CodingKeys: String, CodingKey {
        case provider
        case model
        case baseUrl = "base_url"
        case hasApiKey = "has_api_key"
        case langchainCompat = "langchain_compat"
        case langchainInstalled = "langchain_installed"
        case remoteFallbackProvider = "remote_fallback_provider"
        case cloudProvidersConfigured = "cloud_providers_configured"
    }

    init(provider: String, model: String, baseUrl: String?, hasApiKey: Bool, langchainCompat: Bool = true, langchainInstalled: Bool = false, remoteFallbackProvider: String? = nil, cloudProvidersConfigured: [CloudProviderConfigured]? = nil) {
        self.provider = provider
        self.model = model
        self.baseUrl = baseUrl
        self.hasApiKey = hasApiKey
        self.langchainCompat = langchainCompat
        self.langchainInstalled = langchainInstalled
        self.remoteFallbackProvider = remoteFallbackProvider
        self.cloudProvidersConfigured = cloudProvidersConfigured
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        provider = try c.decode(String.self, forKey: .provider)
        model = try c.decode(String.self, forKey: .model)
        baseUrl = try c.decodeIfPresent(String.self, forKey: .baseUrl)
        hasApiKey = try c.decode(Bool.self, forKey: .hasApiKey)
        langchainCompat = try c.decodeIfPresent(Bool.self, forKey: .langchainCompat) ?? true
        langchainInstalled = try c.decodeIfPresent(Bool.self, forKey: .langchainInstalled) ?? false
        remoteFallbackProvider = try c.decodeIfPresent(String.self, forKey: .remoteFallbackProvider)
        cloudProvidersConfigured = try c.decodeIfPresent([CloudProviderConfigured].self, forKey: .cloudProvidersConfigured)
    }
}

// MARK: - 自定义模型提供商

/// 单个用户自定义模型（服务端 custom_providers 列表中的一项）
struct CustomProviderModel: Identifiable, Codable, Equatable {
    var id: String          // 唯一标识符（UUID 短串）
    var name: String        // 厂商/别名，例如 "智谱 GLM"
    var baseUrl: String
    var model: String
    var hasApiKey: Bool     // 服务端脱敏标志；本地编辑时存 rawApiKey

    /// 本地编辑专用：填写或修改时暂存明文 API Key
    var rawApiKey: String = ""

    enum CodingKeys: String, CodingKey {
        case id, name, model
        case baseUrl = "base_url"
        case hasApiKey = "has_api_key"
    }
}

struct CustomProvidersResponse: Codable {
    let providers: [CustomProviderModel]
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

struct GithubConfig: Codable {
    let configured: Bool
}

struct PendingTool: Codable, Identifiable {
    var id: String { toolName }
    let toolName: String
    let filename: String
    
    enum CodingKeys: String, CodingKey {
        case toolName = "tool_name"
        case filename
    }
}

struct PendingToolsResponse: Codable {
    let pending: [PendingTool]
}

// MARK: - Execution Models

struct ExecutionLogEntry: Identifiable {
    let id = UUID()
    let timestamp: Date
    let level: String
    let message: String
    let toolName: String
}

struct ActionLogEntry: Identifiable {
    let id: UUID
    let actionId: String
    let actionType: String
    let reasoning: String
    let status: ActionStatus
    let output: String?
    let error: String?
    let timestamp: Date
    let iteration: Int
    /// 参数摘要（如命令、路径），来自 action_plan 的 params
    let paramsSummary: String?

    init(actionId: String, actionType: String, reasoning: String, status: ActionStatus, output: String?, error: String?, timestamp: Date, iteration: Int, paramsSummary: String? = nil) {
        self.id = UUID()
        self.actionId = actionId
        self.actionType = actionType
        self.reasoning = reasoning
        self.status = status
        self.output = output
        self.error = error
        self.timestamp = timestamp
        self.iteration = iteration
        self.paramsSummary = paramsSummary
    }

    enum ActionStatus: String {
        case pending = "pending"
        case executing = "executing"
        case success = "success"
        case failed = "failed"
    }
}

// MARK: - System Notification Models

/// 通知分类，对应系统消息 Tab 栏
enum NotificationCategory: String, Codable, CaseIterable {
    case systemError = "system_error"  // 系统错误
    case evolution = "evolution"       // 进化/升级状态
    case task = "task"                 // 任务完成
    case info = "info"                 // 其他
    
    var tabTitle: String {
        switch self {
        case .systemError: return "系统错误"
        case .evolution: return "进化状态"
        case .task: return "任务完成"
        case .info: return "其他"
        }
    }
    
    var icon: String {
        switch self {
        case .systemError: return "exclamationmark.octagon"
        case .evolution: return "arrow.triangle.2.circlepath"
        case .task: return "checkmark.circle"
        case .info: return "info.circle"
        }
    }
}

/// 系统消息 Tab 选项（用于 UI 分段选择）
enum SystemMessageTab: String, CaseIterable {
    case all = "all"
    case systemError = "system_error"
    case evolution = "evolution"
    case task = "task"
    case info = "info"
    
    var category: NotificationCategory? {
        switch self {
        case .all: return nil
        case .systemError: return .systemError
        case .evolution: return .evolution
        case .task: return .task
        case .info: return .info
        }
    }
    
    var tabTitle: String {
        switch self {
        case .all: return "全部"
        case .systemError: return "系统错误"
        case .evolution: return "进化状态"
        case .task: return "任务完成"
        case .info: return "其他"
        }
    }
}

enum NotificationLevel: String, Codable {
    case info
    case warning
    case error
    
    var icon: String {
        switch self {
        case .info: return "info.circle.fill"
        case .warning: return "exclamationmark.triangle.fill"
        case .error: return "xmark.octagon.fill"
        }
    }
    
    var color: String {
        switch self {
        case .info: return "blue"
        case .warning: return "orange"
        case .error: return "red"
        }
    }
}

struct SystemNotification: Identifiable, Codable, Equatable {
    let id: String
    let level: NotificationLevel
    let title: String
    let content: String
    let source: String
    let category: NotificationCategory
    let timestamp: String
    var read: Bool
    
    init(id: String, level: NotificationLevel, title: String, content: String, source: String, category: NotificationCategory, timestamp: String, read: Bool) {
        self.id = id
        self.level = level
        self.title = title
        self.content = content
        self.source = source
        self.category = category
        self.timestamp = timestamp
        self.read = read
    }
    
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        level = try c.decode(NotificationLevel.self, forKey: .level)
        title = try c.decode(String.self, forKey: .title)
        content = try c.decode(String.self, forKey: .content)
        source = try c.decode(String.self, forKey: .source)
        category = (try? c.decode(NotificationCategory.self, forKey: .category)) ?? .info
        timestamp = try c.decode(String.self, forKey: .timestamp)
        read = try c.decode(Bool.self, forKey: .read)
    }
    
    enum CodingKeys: String, CodingKey {
        case id, level, title, content, source, category, timestamp, read
    }
    
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        try c.encode(level, forKey: .level)
        try c.encode(title, forKey: .title)
        try c.encode(content, forKey: .content)
        try c.encode(source, forKey: .source)
        try c.encode(category, forKey: .category)
        try c.encode(timestamp, forKey: .timestamp)
        try c.encode(read, forKey: .read)
    }
    
    var date: Date {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = formatter.date(from: timestamp) { return d }
        formatter.formatOptions = [.withInternetDateTime]
        if let d = formatter.date(from: timestamp) { return d }
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        if let d = df.date(from: timestamp) { return d }
        df.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return df.date(from: timestamp) ?? Date()
    }
    
    var relativeTime: String {
        let interval = Date().timeIntervalSince(date)
        if interval < 60 { return "刚刚" }
        if interval < 3600 { return "\(Int(interval / 60)) 分钟前" }
        if interval < 86400 { return "\(Int(interval / 3600)) 小时前" }
        return "\(Int(interval / 86400)) 天前"
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
