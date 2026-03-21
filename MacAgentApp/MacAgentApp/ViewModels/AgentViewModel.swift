import SwiftUI
import Combine

// MARK: - v3.4 Data Models

struct HitlRequest: Identifiable, Equatable {
    let id = UUID()
    let actionId: String
    let actionType: String
    let description: String
    let riskLevel: String

    var riskColor: Color {
        switch riskLevel {
        case "high": return .red
        case "medium": return .orange
        default: return .yellow
        }
    }
}

@MainActor
class AgentViewModel: ObservableObject {
    // MARK: - Published Properties
    
    @Published var conversations: [Conversation] = []
    @Published var currentConversation: Conversation?
    @Published var inputText: String = ""
    /// 用户拖拽到输入框的附件文件路径（发送后清空）
    @Published var attachedFilePaths: [String] = []
    @Published var isConnected: Bool = false
    @Published var isLoading: Bool = false
    @Published var showSettings: Bool = false
    @Published var showToolPanel: Bool = true
    @Published var columnVisibility: NavigationSplitViewVisibility = .all
    @Published var availableTools: [ToolDefinition] = []
    @Published var recentToolCalls: [ToolCall] = []
    @Published var errorMessage: String?
    
    // MARK: - System Notifications
    
    @Published var systemNotifications: [SystemNotification] = []
    @Published var unreadNotificationCount: Int = 0
    @Published var showSystemMessages: Bool = false
    /// 当前选中的 Tab（全部 / 系统错误 / 进化状态 / 任务完成 / 其他）
    @Published var selectedNotificationTab: SystemMessageTab = .all
    
    // MARK: - LLM Streaming (real-time neural output)

    @Published var llmStreamingText: String = ""
    @Published var isStreamingLLM: Bool = false

    // MARK: - Autonomous Task Properties

    @Published var currentTaskId: String?
    @Published var currentIteration: Int = 0
    @Published var actionLogs: [ActionLogEntry] = []
    @Published var executionLogs: [ExecutionLogEntry] = []
    @Published var taskProgress: TaskProgress?
    
    // Model Selection
    @Published var selectedModelType: String?
    @Published var selectedModelReason: String?
    @Published var taskAnalysisType: String?
    @Published var taskComplexity: Int = 0

    /// Chat 模式下 LLM 请求计数，用于生成唯一 actionId（避免第二次消息覆盖第一次）
    private var chatLlmRequestCounter: Int = 0

    // MARK: - Group Chat (多 Agent 协作群聊)
    
    @Published var groupChats: [GroupChat] = []
    @Published var activeGroupChat: GroupChat?

    /// 转发 monitor_event 到 MonitoringViewModel（多任务分桶）
    var onMonitorEventToMonitor: ((_ sourceSession: String, _ taskId: String, _ event: [String: Any]) -> Void)?

    // MARK: - Settings
    
    @AppStorage("provider") var provider: String = "deepseek"
    @AppStorage("apiKey") var apiKey: String = ""
    @AppStorage("baseUrl") var baseUrl: String = "https://api.deepseek.com"
    @AppStorage("model") var model: String = "deepseek-chat"
    @AppStorage("ollamaUrl") var ollamaUrl: String = "http://localhost:11434/v1"
    @AppStorage("ollamaModel") var ollamaModel: String = "deepseek-r1:8b"
    @AppStorage("lmStudioUrl") var lmStudioUrl: String = "http://localhost:1234/v1"
    @AppStorage("lmStudioModel") var lmStudioModel: String = ""
    /// LM Studio 端口（默认 1234），多实例时可改为 1235、1236 等；修改会同步到 lmStudioUrl
    var lmStudioPortBinding: Binding<String> {
        Binding(
            get: {
                guard let url = URL(string: self.lmStudioUrl), let p = url.port else { return "1234" }
                return String(p)
            },
            set: { newValue in
                self.lmStudioUrl = "http://localhost:\(newValue)/v1"
            }
        )
    }
    /// New API 转发，默认使用 cc1 地址，配置说明见语雀文档
    @AppStorage("newApiKey") var newApiKey: String = ""
    @AppStorage("newApiBaseUrl") var newApiBaseUrl: String = "https://cc1.newapi.ai/v1"
    @AppStorage("newApiModel") var newApiModel: String = ""
    
    /// ChatGPT (OpenAI)
    @AppStorage("openaiBaseUrl") var openaiBaseUrl: String = "https://api.openai.com/v1"
    @AppStorage("openaiModel") var openaiModel: String = "gpt-4o"
    @AppStorage("openaiApiKey") var openaiApiKey: String = ""
    /// Gemini
    @AppStorage("geminiBaseUrl") var geminiBaseUrl: String = ""
    @AppStorage("geminiModel") var geminiModel: String = ""
    @AppStorage("geminiApiKey") var geminiApiKey: String = ""
    /// Claude (Anthropic)
    @AppStorage("anthropicBaseUrl") var anthropicBaseUrl: String = ""
    @AppStorage("anthropicModel") var anthropicModel: String = ""
    @AppStorage("anthropicApiKey") var anthropicApiKey: String = ""
    /// 自定义模型（任意 OpenAI 兼容端点）
    @AppStorage("customApiKey") var customApiKey: String = ""
    @AppStorage("customBaseUrl") var customBaseUrl: String = ""
    @AppStorage("customModelName") var customModelName: String = ""
    
    // 邮件 SMTP 配置（用于系统级发信，不依赖 Mail.app）
    @AppStorage("smtpServer") var smtpServer: String = "smtp.qq.com"
    @AppStorage("smtpPort") var smtpPort: String = "465"
    @AppStorage("smtpUser") var smtpUser: String = ""
    @AppStorage("smtpPassword") var smtpPassword: String = ""
    
    // GitHub Token（拉取开放技能源，提高 API 限额）
    @AppStorage("githubToken") var githubToken: String = ""
    @Published var githubConfigured: Bool = false

    /// 是否使用 LangChain 进行对话（从后端 GET /config 加载）
    @Published var langchainCompat: Bool = true
    /// 后端是否已安装 LangChain 依赖（未安装时开关不可选，需先点「安装」）
    @Published var langchainInstalled: Bool = false
    /// 远程回退策略：当使用远程模型时调用的提供商（空=默认 DeepSeek，newapi/deepseek/openai 为用户显式选择）
    @AppStorage("remoteFallbackProvider") var remoteFallbackProvider: String = ""
    /// 已配置的云端提供商列表（从 GET /config 加载），供“远程回退策略”下拉展示
    @Published var cloudProvidersConfigured: [CloudProviderConfigured] = []
    /// 正在执行「安装」时的加载状态
    @Published var isInstallingLangChain: Bool = false
    /// 安装依赖失败时的错误信息（用于设置页弹窗）
    @Published var langchainInstallError: String?

    // 多自定义模型提供商列表
    @Published var customProviders: [CustomProviderModel] = []
    @Published var isLoadingCustomProviders: Bool = false
    
    // 待审批工具（签名校验未通过）
    @Published var pendingTools: [PendingTool] = []
    @Published var approvingToolName: String? = nil
    
    // MARK: - v3.4 Integration: HITL
    @Published var pendingHitlRequests: [HitlRequest] = []
    @Published var showHitlAlert: Bool = false
    
    // MARK: - v3.4 Integration: MCP
    @Published var mcpServers: [[String: Any]] = []
    @Published var mcpTools: [[String: Any]] = []
    @Published var isLoadingMCP: Bool = false
    @Published var mcpError: String?
    
    // MARK: - v3.4 Integration: Snapshots / Rollback
    @Published var snapshots: [[String: Any]] = []
    @Published var isLoadingSnapshots: Bool = false
    @Published var rollbackMessage: String?
    
    // MARK: - v3.4 Integration: Feature Flags
    @Published var featureFlags: [[String: Any]] = []
    @Published var isLoadingFeatureFlags: Bool = false
    
    // MARK: - v3.4 Integration: Audit Logs
    @Published var auditLogs: [[String: Any]] = []
    @Published var isLoadingAuditLogs: Bool = false
    
    // MARK: - v3.4 Integration: Context Visualization
    @Published var contextData: [String: Any] = [:]
    @Published var isLoadingContext: Bool = false

    // MARK: - Scheduled Tasks
    @Published var scheduledTasks: [[String: Any]] = []
    @Published var isLoadingScheduledTasks: Bool = false

    // MARK: - Circuit Breakers
    @Published var circuitBreakers: [[String: Any]] = []
    @Published var isLoadingCircuitBreakers: Bool = false

    // MARK: - Chow Duck
    @AppStorage("chowDuckEnabled") var chowDuckEnabled: Bool = false
    @Published var duckList: [[String: Any]] = []
    @Published var duckTemplates: [[String: Any]] = []
    @Published var duckEggs: [[String: Any]] = []
    @Published var duckStats: [String: Any] = [:]
    @Published var isLoadingDucks: Bool = false
    @Published var duckError: String?

    // MARK: - Egg / Duck Mode
    /// Shared Egg mode manager — exposes isDuckMode, config, assignedPort
    let eggModeManager = EggModeManager.shared
    /// True when this device is running as a sub-Duck (not main agent)
    var isDuckMode: Bool { eggModeManager.isDuckMode }
    /// The backend port to connect to (configurable via PortConfiguration)
    var backendPort: Int { eggModeManager.assignedPort }

    // MARK: - v3.4 Integration: Model Tier
    /// 用户偏好的模型层级：auto（自动）/ fast / strong / cheap
    @AppStorage("preferredModelTier") var preferredModelTier: String = "auto"
    
    // 本地可用模型列表
    @Published var availableLocalModels: [String] = []
    @Published var isLoadingModels = false
    
    // MARK: - TTS / STT
    
    @AppStorage("ttsEnabled") var ttsEnabled: Bool = false
    @AppStorage("sttSilenceSeconds") var sttSilenceSeconds: Double = 2.0
    @AppStorage("sttNoSpeechTimeoutSeconds") var sttNoSpeechTimeoutSeconds: Double = 12.0
    @Published var isVoiceInputActive: Bool = false
    let voiceInputService = VoiceInputService()
    
    // MARK: - Private Properties
    
    private let backendService = BackendService()
    private var cancellables = Set<AnyCancellable>()
    private var currentSendTask: Task<Void, Never>?
    /// 消息去重：已显示的消息 ID，避免重连时重复显示
    private var displayedMessageIds = Set<String>()
    /// 流式输出时节流：避免每个 chunk 都触发 @Published，减少列表闪烁（100-120ms 一次 UI 更新）
    private var lastStreamingUIPushTime: Date?
    private let streamingThrottleInterval: TimeInterval = 0.12
    /// 流式期间定期保存部分内容，断线/崩溃时保留本地数据

    /// 格式化自动步骤输出，便于阅读：保留换行、步骤分隔符换行、仅截断时加省略号
    private static func buildParamsSummary(actionType: String, params: [String: Any]) -> String? {
        let t = actionType.lowercased()
        if t.contains("run_shell") || t.contains("shell") {
            if let cmd = params["command"] as? String, !cmd.isEmpty {
                return cmd.count > 80 ? String(cmd.prefix(77)) + "…" : cmd
            }
        }
        if t.contains("read_file") || t.contains("write_file") || t.contains("delete_file") {
            if let path = params["path"] as? String, !path.isEmpty { return path }
        }
        if t.contains("call_tool") {
            if let name = params["tool_name"] as? String, !name.isEmpty {
                if let args = params["args"] as? [String: Any], let action = args["action"] as? String {
                    return "\(name) action=\(action)"
                }
                return name
            }
        }
        if t.contains("create_and_run") {
            if let code = params["code"] as? String, !code.isEmpty {
                return code.count > 60 ? String(code.prefix(57)) + "…" : code
            }
        }
        if let path = params["path"] as? String, !path.isEmpty { return path }
        if let cmd = params["command"] as? String, !cmd.isEmpty { return cmd }
        return nil
    }

    private func formatActionOutput(_ output: String?, maxChars: Int = 500) -> String {
        guard let out = output, !out.isEmpty else { return "" }
        let truncated = out.count > maxChars ? String(out.prefix(maxChars)) + "..." : out
        // 将 "→" 分隔的步骤换行显示（如 "1) xxx → 2) xxx"）
        var text = truncated.replacingOccurrences(of: " → ", with: "\n   ")
        text = text.replacingOccurrences(of: "→ ", with: "\n   ")
        // 多行内容每行缩进
        return text.replacingOccurrences(of: "\n", with: "\n   ")
    }
    private var lastStreamingSaveTime: Date?
    private let streamingSaveInterval: TimeInterval = 2.0
    /// 标记是否刚创建新 assistant 消息（用于触发滚动到底部）
    @Published var shouldScrollToBottom: Bool = false
    
    // MARK: - Initialization
    
    init() {
        // 一次性迁移：曾用旧默认地址的改为 cc1 默认地址
        if newApiBaseUrl == "http://localhost:3000/v1" {
            newApiBaseUrl = "https://cc1.newapi.ai/v1"
        }
        setupSubscriptions()
        setupVoiceInput()
        Task { @MainActor in
            loadConversations()
            if currentConversation == nil {
                newConversation()
            }
        }
    }

    /// Called at startup: if duck mode is detected, find available port, start duck backend,
    /// then point BackendService at the duck port.
    func applyDuckModeIfNeeded() async {
        guard eggModeManager.isDuckMode, let config = eggModeManager.config else { return }
        await eggModeManager.resolvePort()
        let port = eggModeManager.assignedPort
        // Start duck backend on the assigned port
        ProcessManager.shared.startDuckBackend(port: port, config: config)
        // Give it a moment to start, then update the port
        try? await Task.sleep(nanoseconds: 2_500_000_000)
        await backendService.updatePort(port)
    }
    
    private func setupVoiceInput() {
        voiceInputService.onShouldSubmit = { [weak self] text in
            guard let self = self else { return }
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty { return }
            self.isVoiceInputActive = false
            self.inputText = ""
            self.sendMessage(withText: trimmed)
        }
    }
    
    private func setupSubscriptions() {
        backendService.$isConnected
            .receive(on: DispatchQueue.main)
            .assign(to: &$isConnected)
        
        backendService.onSystemNotification = { [weak self] notification, unreadCount in
            guard let self = self else { return }
            if !self.systemNotifications.contains(where: { $0.id == notification.id }) {
                self.systemNotifications.insert(notification, at: 0)
            }
            self.unreadNotificationCount = unreadCount
        }
        
        backendService.onToolsUpdated = { [weak self] in
            guard let self = self else { return }
            Task { @MainActor in
                await self.loadTools()
                await self.loadPendingTools()
            }
        }
        
        backendService.onTaskDetected = { [weak self] hasRunningTask, taskId in
            guard let self = self, hasRunningTask, let conversation = self.currentConversation else { return }
            
            Task { @MainActor in
                // 先同步 session_id，确保后端知道当前 session
                let localSessionId = conversation.id.uuidString
                await self.backendService.syncSessionId(localSessionId)
                try? await Task.sleep(nanoseconds: 300_000_000)
                await self.resumeChatStream(sessionId: localSessionId)
            }
        }
        
        backendService.onChatResumeDetected = { [weak self] serverSessionId in
            guard let self = self else { return }
            Task { @MainActor in
                // 参考 iOS 端逻辑：使用本地会话 UUID 而非服务端默认 session_id
                // 服务端连接后默认 session 为 "default"，但 chat 任务注册在本地 UUID 下
                guard let conversation = self.currentConversation else { return }
                let localSessionId = conversation.id.uuidString
                
                if localSessionId != serverSessionId {
                    // 先同步 session_id 到后端，再恢复 chat 流
                    await self.backendService.syncSessionId(localSessionId)
                    try? await Task.sleep(nanoseconds: 300_000_000) // 0.3s 等待后端完成 session 切换
                }
                
                await self.resumeChatStream(sessionId: localSessionId)
            }
        }
        
        // 全局监控事件回调：接收来自任意客户端的任务执行事件
        backendService.onMonitorEvent = { [weak self] sourceSession, taskId, event in
            guard let self = self else { return }
            self.handleMonitorEvent(sourceSession: sourceSession, taskId: taskId, event: event)
        }

        // 子 Duck 任务完成：主 Agent 主动联系用户，将结果作为 assistant 消息展示
        backendService.onDuckTaskComplete = { [weak self] content, success, taskId, sessionId in
            guard let self = self else { return }
            Task { @MainActor in
                self.handleDuckTaskComplete(content: content, success: success, taskId: taskId, sessionId: sessionId)
            }
        }

        // MARK: Group Chat callbacks
        backendService.onGroupChatCreated = { [weak self] group in
            guard let self = self else { return }
            self.groupChats.insert(group, at: 0)
            self.activeGroupChat = group
        }
        backendService.onGroupMessage = { [weak self] groupId, message in
            guard let self = self else { return }
            if var g = self.groupChats.first(where: { $0.groupId == groupId }) {
                g.addMessage(message)
                if let idx = self.groupChats.firstIndex(where: { $0.groupId == groupId }) {
                    self.groupChats[idx] = g
                }
                if self.activeGroupChat?.groupId == groupId {
                    self.activeGroupChat = g
                }
            }
        }
        backendService.onGroupStatusUpdate = { [weak self] groupId, status, taskSummary in
            guard let self = self else { return }
            if let idx = self.groupChats.firstIndex(where: { $0.groupId == groupId }) {
                self.groupChats[idx].updateStatus(status, summary: taskSummary)
                if self.activeGroupChat?.groupId == groupId {
                    self.activeGroupChat = self.groupChats[idx]
                }
            }
        }
        backendService.onGroupChatDeleted = { [weak self] groupId in
            guard let self = self else { return }
            self.groupChats.removeAll { $0.groupId == groupId }
            if self.activeGroupChat?.groupId == groupId {
                self.activeGroupChat = nil
            }
        }
    }

    /// 用户主动删除群聊
    func deleteGroupChat(_ groupChat: GroupChat) {
        Task {
            try? await backendService.deleteGroupChat(groupId: groupChat.groupId)
            await MainActor.run {
                self.groupChats.removeAll { $0.groupId == groupChat.groupId }
                if self.activeGroupChat?.groupId == groupChat.groupId {
                    self.activeGroupChat = nil
                }
            }
        }
    }

    private func handleDuckTaskComplete(content: String, success: Bool, taskId: String, sessionId: String) {
        guard let conversation = currentConversation else { return }
        let localSessionId = conversation.id.uuidString
        guard sessionId == localSessionId else { return }
        let msg = Message(role: .assistant, content: content, modelName: "Duck")
        if let idx = conversations.firstIndex(where: { $0.id == conversation.id }) {
            conversations[idx].messages.append(msg)
            conversations[idx].updatedAt = Date()
        }
        currentConversation?.messages.append(msg)
        currentConversation?.updatedAt = Date()
        saveConversations()  // 持久化，避免重新打开 App 后 Duck 任务结果丢失
        // Duck 任务完成后即时刷新状态（Duck 应回到空闲状态）
        Task { await self.refreshDuckStatus() }
    }

    // MARK: - Connection
    
    func connect() {
        Task {
            // In duck mode: start duck backend and point to duck port before connecting
            await applyDuckModeIfNeeded()
            await backendService.connect()
            await loadTools()
            await loadCustomProviders()
            await syncConfig()
            await loadGitHubConfig()
            loadSystemMessages()
            // 恢复持久化的群聊（用户重启 App 后看到进行中的多 Agent 任务）
            await restoreGroupChats()
        }
    }
    
    func disconnect() {
        backendService.disconnect()
    }

    // MARK: - Group Chat Restore

    /// App 启动/重连时从后端拉取历史群聊，恢复进行中的多 Agent 任务显示
    private func restoreGroupChats() async {
        guard let conversation = currentConversation else { return }
        let sessionId = conversation.id.uuidString

        do {
            let briefs = try await backendService.fetchGroupChatBriefs(sessionId: sessionId)
            guard !briefs.isEmpty else { return }

            var restored: [GroupChat] = []
            for brief in briefs {
                guard let groupId = brief["group_id"] as? String,
                      let statusStr = brief["status"] as? String else { continue }

                // 仅恢复进行中的群聊；已完成/取消的24小时内也保留，让用户能看到结果
                let isActive = statusStr == "active"
                let isRecentlyDone: Bool = {
                    guard statusStr == "completed" || statusStr == "failed",
                          let completedAt = brief["completed_at"] as? Double else { return false }
                    return (Date().timeIntervalSince1970 - completedAt) < 86400 // 24h
                }()
                guard isActive || isRecentlyDone else { continue }

                // 拉取完整群聊（含消息）
                if let gc = try? await backendService.fetchGroupChatDetail(groupId: groupId) {
                    restored.append(gc)
                }
            }

            guard !restored.isEmpty else { return }

            await MainActor.run {
                for gc in restored {
                    // 避免重复添加
                    if !self.groupChats.contains(where: { $0.groupId == gc.groupId }) {
                        self.groupChats.append(gc)
                    }
                }
                // 若有进行中的群聊，自动设置为活跃
                if self.activeGroupChat == nil,
                   let activeGc = restored.first(where: { $0.status.rawValue == "active" }) {
                    self.activeGroupChat = activeGc
                }
            }
        } catch {
            // 群聊恢复失败不影响正常使用
        }
    }

    // MARK: - Configuration
    
    func syncConfig() async {
        var configApiKey: String
        var configBaseUrl: String
        var configModel: String
        
        switch provider {
        case "deepseek":
            configApiKey = apiKey
            configBaseUrl = baseUrl
            configModel = model
        case "ollama":
            configApiKey = "ollama"
            configBaseUrl = ollamaUrl
            configModel = ollamaModel
        case "lmstudio":
            configApiKey = "lm-studio"
            configBaseUrl = lmStudioUrl
            configModel = lmStudioModel
        case "newapi":
            configApiKey = newApiKey
            configBaseUrl = newApiBaseUrl
            configModel = newApiModel
        case "openai":
            configApiKey = openaiApiKey
            configBaseUrl = openaiBaseUrl
            configModel = openaiModel
        case "gemini":
            configApiKey = geminiApiKey
            configBaseUrl = geminiBaseUrl
            configModel = geminiModel
        case "anthropic":
            configApiKey = anthropicApiKey
            configBaseUrl = anthropicBaseUrl
            configModel = anthropicModel
        case "custom":
            configApiKey = customApiKey
            configBaseUrl = customBaseUrl
            configModel = customModelName
        default:
            // custom.{id} 格式：从 customProviders 列表找到对应项
            if provider.hasPrefix("custom.") {
                let pid = String(provider.dropFirst("custom.".count))
                if let slot = customProviders.first(where: { $0.id == pid }) {
                    configApiKey = slot.rawApiKey
                    configBaseUrl = slot.baseUrl
                    configModel = slot.model
                    // provider 就是 "custom.{id}"，直接传给后端
                } else {
                    configApiKey = apiKey
                    configBaseUrl = baseUrl
                    configModel = model
                }
            } else {
                configApiKey = apiKey
                configBaseUrl = baseUrl
                configModel = model
            }
        }
        
        do {
            try await backendService.updateConfig(
                provider: provider,
                apiKey: configApiKey,
                baseUrl: configBaseUrl,
                model: configModel,
                remoteFallbackProvider: remoteFallbackProvider
            )
        } catch {
            errorMessage = "配置同步失败: \(error.localizedDescription)"
        }
    }
    
    func syncSmtpConfig() async {
        do {
            try await backendService.updateSmtpConfig(
                smtpServer: smtpServer,
                smtpPort: Int(smtpPort) ?? 465,
                smtpUser: smtpUser,
                smtpPassword: smtpPassword.isEmpty ? nil : smtpPassword
            )
            errorMessage = nil
        } catch {
            errorMessage = "邮件配置同步失败: \(error.localizedDescription)"
        }
    }
    
    func loadSmtpConfig() async {
        do {
            let cfg = try await backendService.fetchSmtpConfig()
            smtpServer = cfg.smtpServer
            smtpPort = String(cfg.smtpPort)
            smtpUser = cfg.smtpUser
            // 密码不返回，保留本地已填写的
        } catch {
            // 后端未启动或未配置，保留本地值
        }
    }
    
    func loadGitHubConfig() async {
        do {
            let cfg = try await backendService.fetchGitHubConfig()
            githubConfigured = cfg.configured
        } catch {
            githubConfigured = false
        }
    }

    /// 从后端加载当前配置（含 LangChain、远程回退策略、已配置云端列表）
    func loadBackendConfig() async {
        do {
            let cfg = try await backendService.fetchConfig()
            langchainCompat = cfg.langchainCompat
            langchainInstalled = cfg.langchainInstalled
            remoteFallbackProvider = cfg.remoteFallbackProvider ?? ""
            cloudProvidersConfigured = cfg.cloudProvidersConfigured ?? []
            // 根据当前主提供商回填对应配置（后端不返回 api_key，保留本地已填）
            switch cfg.provider.lowercased() {
            case "openai":
                openaiBaseUrl = cfg.baseUrl ?? openaiBaseUrl
                openaiModel = cfg.model
            case "gemini":
                geminiBaseUrl = cfg.baseUrl ?? geminiBaseUrl
                geminiModel = cfg.model
            case "anthropic":
                anthropicBaseUrl = cfg.baseUrl ?? anthropicBaseUrl
                anthropicModel = cfg.model
            case "custom":
                customBaseUrl = cfg.baseUrl ?? customBaseUrl
                customModelName = cfg.model
            default:
                break
            }
        } catch {
            // 后端未连接时保留当前值
        }
    }

    // MARK: - 自定义模型提供商管理

    func loadCustomProviders() async {
        isLoadingCustomProviders = true
        defer { isLoadingCustomProviders = false }
        do {
            let providers = try await backendService.fetchCustomProviders()
            await MainActor.run { customProviders = providers }
        } catch {
            // 连接失败时保留本地列表
        }
    }

    func saveCustomProvider(_ item: CustomProviderModel) async {
        do {
            let saved = try await backendService.upsertCustomProvider(
                id: item.id.isEmpty ? nil : item.id,
                name: item.name,
                apiKey: item.rawApiKey,
                baseUrl: item.baseUrl,
                model: item.model
            )
            await MainActor.run {
                if let idx = customProviders.firstIndex(where: { $0.id == saved.id }) {
                    customProviders[idx] = saved
                } else {
                    customProviders.append(saved)
                }
            }
        } catch {
            errorMessage = "保存失败: \(error.localizedDescription)"
        }
    }

    func deleteCustomProvider(id: String) async {
        do {
            try await backendService.deleteCustomProvider(id: id)
            await MainActor.run {
                customProviders.removeAll { $0.id == id }
                // 若当前选择的就是被删除的提供商，切换回 deepseek
                if provider.hasPrefix("custom.") {
                    let pid = String(provider.dropFirst("custom.".count))
                    if pid == id { provider = "deepseek" }
                }
            }
        } catch {
            errorMessage = "删除失败: \(error.localizedDescription)"
        }
    }

    /// 仅保存 LangChain 开关状态（不执行安装，用于用户勾选/取消勾选时）
    func setLangChainCompat(_ enabled: Bool) async {        langchainInstallError = nil
        do {
            try await backendService.updateLangChainCompat(enabled: enabled)
            langchainCompat = enabled
        } catch {
            langchainCompat = !enabled
            errorMessage = "LangChain 开关保存失败: \(error.localizedDescription)"
        }
    }

    /// 用户点击「安装」：安装 LangChain 依赖；成功则开启开关并默认勾选，失败则弹窗提示
    func installLangChainAndEnable() async {
        langchainInstallError = nil
        isInstallingLangChain = true
        defer { isInstallingLangChain = false }
        let result = await backendService.installLangChainDependencies()
        if !result.success {
            langchainInstallError = result.message
            return
        }
        do {
            try await backendService.updateLangChainCompat(enabled: true)
            langchainCompat = true
            await loadBackendConfig()
        } catch {
            langchainInstallError = "安装成功但保存设置失败: \(error.localizedDescription)"
        }
    }

    func syncGitHubConfig() async {
        do {
            try await backendService.updateGitHubConfig(githubToken: githubToken.isEmpty ? nil : githubToken)
            await loadGitHubConfig()
            errorMessage = nil
        } catch {
            errorMessage = "GitHub 配置同步失败: \(error.localizedDescription)"
        }
    }
    
    func loadPendingTools() async {
        do {
            pendingTools = try await backendService.fetchPendingTools()
        } catch {
            pendingTools = []
        }
    }
    
    func approveTool(name: String) async {
        approvingToolName = name
        defer { approvingToolName = nil }
        do {
            try await backendService.approveTool(toolName: name)
            try await backendService.reloadTools()
            // 工具列表刷新由服务端广播 tools_updated、客户端 onToolsUpdated 统一处理，各端收到后刷新
            await loadPendingTools()
            await loadTools()
            errorMessage = nil
        } catch {
            errorMessage = "审批失败: \(error.localizedDescription)"
        }
    }
    
    func fetchLocalModels() async {
        isLoadingModels = true
        defer { isLoadingModels = false }
        
        var models: [String] = []
        
        // 根据当前 provider 获取模型列表
        let baseUrl: String
        switch provider {
        case "ollama":
            baseUrl = ollamaUrl.replacingOccurrences(of: "/v1", with: "")
        case "lmstudio":
            baseUrl = lmStudioUrl
        default:
            return
        }
        
        // 尝试获取模型列表
        guard let url = URL(string: "\(baseUrl)/models") else { return }
        
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let modelData = json["data"] as? [[String: Any]] ?? json["models"] as? [[String: Any]] {
                models = modelData.compactMap { $0["id"] as? String ?? $0["name"] as? String }
            }
        } catch {
            print("Failed to fetch models: \(error)")
        }
        
        await MainActor.run {
            availableLocalModels = models
        }
    }
    
    // MARK: - Tools
    
    func loadTools() async {
        do {
            let tools = try await backendService.fetchTools()
            availableTools = tools
        } catch {
            errorMessage = "加载工具失败: \(error.localizedDescription)"
        }
    }
    
    // MARK: - Conversations
    
    func newConversation() {
        let conversation = Conversation()
        conversations.insert(conversation, at: 0)
        currentConversation = conversation
        saveConversations()
    }
    
    func selectConversation(_ conversation: Conversation) {
        Task { @MainActor in
            activeGroupChat = nil
            currentConversation = conversation
        }
    }
    
    func deleteConversation(_ conversation: Conversation) {
        conversations.removeAll { $0.id == conversation.id }
        if currentConversation?.id == conversation.id {
            currentConversation = conversations.first
            if currentConversation == nil {
                newConversation()
            }
        }
        saveConversations()
    }
    
    private func loadConversations() {
        if let data = UserDefaults.standard.data(forKey: "conversations"),
           let decoded = try? JSONDecoder().decode([Conversation].self, from: data) {
            conversations = decoded
            currentConversation = conversations.first
        }
    }
    
    private func saveConversations() {
        if let encoded = try? JSONEncoder().encode(conversations) {
            UserDefaults.standard.set(encoded, forKey: "conversations")
        }
    }
    
    // MARK: - Messaging
    
    /// 发送消息。若传入 text 则使用该文本（如语音识别结果），否则使用 inputText；空字符串会被忽略。
    func sendMessage(withText text: String? = nil) {
        let content = (text?.trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 }
            ?? inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty else { return }
        guard var conversation = currentConversation else { return }
        
        let userMessage = Message(role: .user, content: content)
        conversation.messages.append(userMessage)
        
        let assistantMessage = Message(role: .assistant, content: "", isStreaming: true)
        conversation.messages.append(assistantMessage)
        
        let filePaths = attachedFilePaths
        inputText = ""
        attachedFilePaths = []
        updateCurrentConversation(conversation)
        isLoading = true
        executionLogs = []
        shouldScrollToBottom = true
        
        let conversationId = conversation.id.uuidString
        
        currentSendTask = Task {
            defer {
                Task { @MainActor in
                    isLoading = false
                    currentSendTask = nil
                }
            }
            await sendMessageWithRetry(content, sessionId: conversationId, retryCount: 0, filePaths: filePaths)
        }
    }
    
    func sendMessage() {
        sendMessage(withText: nil)
    }
    
    func stopTask() {
        guard isLoading, let conversation = currentConversation else { return }
        currentSendTask?.cancel()
        currentSendTask = nil
        isLoading = false
        TTSService.shared.stop()
        
        Task {
            await backendService.sendStopStream(sessionId: conversation.id.uuidString)
        }
        
        if let lastIndex = currentConversation?.messages.lastIndex(where: { $0.role == .assistant }),
           currentConversation?.messages[lastIndex].isStreaming == true {
            var conv = currentConversation!
            conv.messages[lastIndex].content += "\n\n[已终止]"
            conv.messages[lastIndex].isStreaming = false
            updateCurrentConversation(conv)
        }
    }
    
    func startVoiceInput() {
        guard !isLoading else { return }
        voiceInputService.silenceDuration = sttSilenceSeconds
        voiceInputService.noSpeechTimeout = sttNoSpeechTimeoutSeconds
        voiceInputService.requestAuthorization { [weak self] granted in
            guard granted, let self = self else { return }
            self.isVoiceInputActive = true
            self.voiceInputService.startRecording()
        }
    }
    
    func stopVoiceInput() {
        isVoiceInputActive = false
        voiceInputService.stopRecording()
    }
    
    /// 语音输入时手动提交当前识别结果（静音/超时也会自动提交）
    func commitVoiceInput() {
        let text = voiceInputService.commitCurrentText()
        isVoiceInputActive = false
        if !text.isEmpty {
            sendMessage(withText: text)
        }
    }
    
    private func sendMessageWithRetry(_ messageText: String, sessionId: String, retryCount: Int, filePaths: [String] = []) async {
        if ttsEnabled {
            TTSService.shared.resetStreamState()
        }
        do {
            var fullContent = ""
            llmStreamingText = ""
            isStreamingLLM = true
            executionLogs = []
            defer { isStreamingLLM = false }

            // 若当前有活跃群聊，将 group_id 传给后端，使主 Agent 知道已有群聊可续接
            let activeGid = activeGroupChat?.groupId
            for try await chunk in backendService.sendMessageStream(messageText, sessionId: sessionId, filePaths: filePaths, activeGroupId: activeGid) {
                switch chunk {
                case .content(let text):
                    fullContent += text
                    llmStreamingText = fullContent
                    updateAssistantMessage(content: fullContent, isStreaming: true)
                    if ttsEnabled {
                        TTSService.shared.appendAndSpeakStreamedContent(fullContent)
                    }
                    
                case .toolCall(let name, let args):
                    let toolCall = ToolCall(
                        id: UUID().uuidString,
                        name: name,
                        arguments: args.mapValues { AnyCodable($0) }
                    )
                    recentToolCalls.insert(toolCall, at: 0)
                    if recentToolCalls.count > 10 {
                        recentToolCalls.removeLast()
                    }
                    
                case .toolResult(let name, let success, let result):
                    if let index = recentToolCalls.firstIndex(where: { $0.name == name && $0.result == nil }) {
                        recentToolCalls[index].result = ToolResult(success: success, output: result)
                    }
                    
                case .executionLog(let toolName, _, let level, let message):
                    executionLogs.append(ExecutionLogEntry(timestamp: Date(), level: level, message: message, toolName: toolName))
                    
                case .done(let model, let tokenUsage):
                    updateAssistantMessage(content: fullContent, isStreaming: false, modelName: model, tokenUsage: tokenUsage)
                    if ttsEnabled {
                        TTSService.shared.speakRemainingBuffer()
                    }
                    
                case .stopped:
                    updateAssistantMessage(content: fullContent + "\n\n[已终止]", isStreaming: false)
                    
                case .error(let message):
                    errorMessage = message
                    updateAssistantMessage(content: "错误: \(message)", isStreaming: false)
                    
                case .imageData(let base64, let mimeType, let path):
                    // 合并附件和内容更新为一次调用，避免竞态条件
                    let attachment = MessageAttachment.fromBase64(base64, mimeType: mimeType)
                    if let imagePath = path {
                        fullContent += "\n📷 截图已保存: \(imagePath)\n"
                    }
                    updateAssistantMessage(content: fullContent, isStreaming: true, attachments: [attachment])
                    
                case .localImage(let path):
                    let attachment = MessageAttachment.fromLocalPath(path)
                    fullContent += "\n📷 图片: \(path)\n"
                    updateAssistantMessage(content: fullContent, isStreaming: true, attachments: [attachment])
                    
                case .taskStart(let taskId, let taskDesc):
                    currentTaskId = taskId
                    taskProgress = TaskProgress(
                        id: taskId,
                        taskDescription: taskDesc,
                        status: .running,
                        currentIteration: 0,
                        totalActions: 0,
                        successfulActions: 0,
                        failedActions: 0,
                        startTime: Date()
                    )
                    fullContent += "🚀 任务开始执行...\n"
                    updateAssistantMessage(content: fullContent, isStreaming: true)
                    
                case .modelSelected(let modelType, let reason, let taskType, let complexity):
                    selectedModelType = modelType
                    selectedModelReason = reason
                    taskAnalysisType = taskType
                    taskComplexity = complexity
                    let modelIcon = modelType == "local" ? "🏠" : "☁️"
                    let modelName = modelType == "local" ? "本地模型" : "远程模型"
                    fullContent += "\(modelIcon) 选择模型: \(modelName)\n📊 任务类型: \(taskType) (复杂度: \(complexity)/10)\n💡 原因: \(reason)\n\n"
                    updateAssistantMessage(content: fullContent, isStreaming: true)
                    
                case .actionPlan(let action, let iteration):
                    currentIteration = iteration
                    let actionType = action["action_type"] as? String ?? "unknown"
                    let reasoning = action["reasoning"] as? String ?? ""
                    let actionId = action["action_id"] as? String ?? UUID().uuidString
                    let params = action["params"] as? [String: Any] ?? [:]
                    let paramsSummary = Self.buildParamsSummary(actionType: actionType, params: params)
                    let logEntry = ActionLogEntry(actionId: actionId, actionType: actionType, reasoning: reasoning, status: .pending, output: nil, error: nil, timestamp: Date(), iteration: iteration, paramsSummary: paramsSummary)
                    actionLogs.append(logEntry)
                    if actionType == "call_tool" {
                        let toolName = (action["params"] as? [String: Any])?["tool_name"] as? String ?? "unknown"
                        let args = (action["params"] as? [String: Any])?["args"] as? [String: Any] ?? [:]
                        let toolCall = ToolCall(id: actionId, name: toolName, arguments: args.mapValues { AnyCodable($0) }, result: nil)
                        recentToolCalls.insert(toolCall, at: 0)
                        if recentToolCalls.count > 10 { recentToolCalls.removeLast() }
                    }
                    fullContent += "\n📋 步骤 \(iteration): \(actionType)\n   → \(reasoning)\n"
                    updateAssistantMessage(content: fullContent, isStreaming: true)
                    
                case .actionExecuting(let actionId, let actionType):
                    if let index = actionLogs.firstIndex(where: { $0.actionId == actionId }) {
                        let e = actionLogs[index]
                        actionLogs[index] = ActionLogEntry(actionId: actionId, actionType: e.actionType, reasoning: e.reasoning, status: .executing, output: nil, error: nil, timestamp: e.timestamp, iteration: e.iteration, paramsSummary: e.paramsSummary)
                    }
                    fullContent += "   ⏳ 执行中: \(actionType)...\n"
                    updateAssistantMessage(content: fullContent, isStreaming: true)
                    
                case .actionResult(let actionId, let success, let output, let error):
                    if let index = actionLogs.firstIndex(where: { $0.actionId == actionId }) {
                        let e = actionLogs[index]
                        actionLogs[index] = ActionLogEntry(actionId: actionId, actionType: e.actionType, reasoning: e.reasoning, status: success ? .success : .failed, output: output, error: error, timestamp: e.timestamp, iteration: e.iteration, paramsSummary: e.paramsSummary)
                    }
                    if success {
                        let outputPreview = formatActionOutput(output)
                        fullContent += "   ✅ 成功\(outputPreview.isEmpty ? "" : ":\n   \(outputPreview)")\n"
                        var screenshotAttachment: MessageAttachment?
                        if let out = output?.data(using: .utf8),
                           let obj = try? JSONSerialization.jsonObject(with: out) as? [String: Any],
                           let path = obj["screenshot_path"] as? String ?? obj["path"] as? String,
                           !path.isEmpty {
                            screenshotAttachment = MessageAttachment.fromLocalPath(path)
                        }
                        if let att = screenshotAttachment {
                            fullContent += "\n📷 截图已生成\n"
                            updateAssistantMessage(content: fullContent, isStreaming: true, attachments: [att])
                        } else {
                            updateAssistantMessage(content: fullContent, isStreaming: true)
                        }
                    } else {
                        fullContent += "   ❌ 失败: \(error ?? "未知错误")\n"
                        updateAssistantMessage(content: fullContent, isStreaming: true)
                    }
                    taskProgress?.totalActions = (taskProgress?.totalActions ?? 0) + 1
                    if success { taskProgress?.successfulActions = (taskProgress?.successfulActions ?? 0) + 1 }
                    else { taskProgress?.failedActions = (taskProgress?.failedActions ?? 0) + 1 }
                    
                case .reflectStart:
                    fullContent += "\n🔍 正在分析执行结果...\n"
                    updateAssistantMessage(content: fullContent, isStreaming: true)
                    
                case .reflectResult(let reflection):
                    fullContent += "💡 反思结果:\n\(reflection)\n"
                    updateAssistantMessage(content: fullContent, isStreaming: true)
                    
                case .taskComplete(_, let success, let summary, let totalActions):
                    taskProgress?.status = success ? .completed : .failed
                    taskProgress?.endTime = Date()
                    taskProgress?.summary = summary
                    let statusIcon = success ? "✅" : "⚠️"
                    fullContent += "\n\(statusIcon) \(success ? "任务完成" : "任务未完成")\n"
                    fullContent += "📊 统计: \(totalActions) 个动作\n"
                    if !summary.isEmpty { fullContent += "📝 总结: \(summary)\n" }
                    updateAssistantMessage(content: fullContent, isStreaming: false)

                case .llmRequestStart(let provider, let model, let iteration):
                    let llmId = "llm_chat_\(chatLlmRequestCounter)"
                    chatLlmRequestCounter += 1
                    let logEntry = ActionLogEntry(
                        actionId: llmId,
                        actionType: "llm_request",
                        reasoning: "请求 \(provider)/\(model)",
                        status: .executing,
                        output: nil,
                        error: nil,
                        timestamp: Date(),
                        iteration: iteration
                    )
                    actionLogs = actionLogs + [logEntry]

                case .llmRequestEnd(_, _, let iteration, let latencyMs, let usage, let responsePreview, let error):
                    let llmId = "llm_chat_\(max(0, chatLlmRequestCounter - 1))"
                    if let index = actionLogs.lastIndex(where: { $0.actionId == llmId }) {
                        let pt = usage["prompt_tokens"] as? Int ?? 0
                        let ct = usage["completion_tokens"] as? Int ?? 0
                        var out = "延迟: \(latencyMs)ms | 输入: \(pt) tokens | 输出: \(ct) tokens"
                        if let err = error, !err.isEmpty {
                            out += " | 错误: \(err)"
                        } else if let preview = responsePreview, !preview.isEmpty {
                            out += "\n预览: \(preview)"
                        }
                        let updated = ActionLogEntry(
                            actionId: llmId,
                            actionType: "llm_request",
                            reasoning: actionLogs[index].reasoning,
                            status: error != nil ? .failed : .success,
                            output: out,
                            error: error,
                            timestamp: actionLogs[index].timestamp,
                            iteration: iteration
                        )
                        var newLogs = actionLogs
                        newLogs[index] = updated
                        actionLogs = newLogs
                    }

                case .retry:
                    break
                    
                case .chatResumeResult:
                    // 仅用于 resumeChatStream，此处忽略
                    break
                    
                case .phaseVerify(let iteration, let phase, let note):
                    let phaseIcon: String
                    switch phase {
                    case "gather": phaseIcon = "🔍"
                    case "act": phaseIcon = "⚡"
                    case "verify": phaseIcon = "✔️"
                    default: phaseIcon = "🔄"
                    }
                    fullContent += "\(phaseIcon) [Verify #\(iteration)] \(note)\n"
                    updateAssistantMessage(content: fullContent, isStreaming: true)
                    
                case .hitlRequest(let actionId, let actionType, let description, let riskLevel):
                    let request = HitlRequest(actionId: actionId, actionType: actionType, description: description, riskLevel: riskLevel)
                    pendingHitlRequests.append(request)
                    fullContent += "\n⚠️ [等待审批] \(actionType): \(description)\n"
                    updateAssistantMessage(content: fullContent, isStreaming: true)
                }
            }
            
            if !fullContent.isEmpty {
                updateAssistantMessage(content: fullContent, isStreaming: false)
            }
            
        } catch is CancellationError {
            return
        } catch {
            if retryCount < 1 {
                // 不断线覆盖已有部分回复，用 errorMessage 展示重连状态，保留本地数据
                errorMessage = "连接断开，正在重连..."
                
                await backendService.reconnect()
                
                if isConnected {
                    // 重连后同步本地 session_id 到后端（参考 iOS 端逻辑）
                    await backendService.syncSessionId(sessionId)
                    try? await Task.sleep(nanoseconds: 300_000_000) // 0.3s 等待后端完成 session 切换
                    errorMessage = "已重连，正在恢复对话..."
                    await resumeChatStream(sessionId: sessionId)
                } else {
                    errorMessage = "重连失败，请检查后端服务是否运行"
                    updateAssistantMessage(content: "重连失败，请检查后端服务是否运行", isStreaming: false)
                }
            } else {
                errorMessage = "发送消息失败: \(error.localizedDescription)"
                updateAssistantMessage(content: "抱歉，发生了错误：\(error.localizedDescription)", isStreaming: false)
            }
        }
    }
    
    /// 判断是否为连接类错误（断线、被对端关闭等），用于触发重连重试
    private func isConnectionError(_ error: Error) -> Bool {
        let desc = error.localizedDescription.lowercased()
        if desc.contains("connection reset") || desc.contains("connection refused") ||
           desc.contains("network connection lost") || desc.contains("not connected") ||
           desc.contains("connection closed") || desc.contains("broken pipe") {
            return true
        }
        if let urlError = error as? URLError {
            switch urlError.code {
            case .networkConnectionLost, .notConnectedToInternet,
                 .cannotConnectToHost, .timedOut, .internationalRoamingOff:
                return true
            default:
                break
            }
        }
        return false
    }
    
    /// 结束上一条助手消息的 isStreaming（如“已重连，正在恢复对话...”），避免重连后无会话时两个气泡都显示“正在思考”
    private func endPreviousResumeMessageStreaming() {
        guard var conversation = currentConversation else { return }
        let assistantIndices = conversation.messages.indices.filter { conversation.messages[$0].role == .assistant }
        guard assistantIndices.count >= 2 else { return }
        let prevIndex = assistantIndices[assistantIndices.count - 2]
        if conversation.messages[prevIndex].isStreaming {
            conversation.messages[prevIndex].isStreaming = false
            updateCurrentConversation(conversation, shouldSave: true)
        }
    }
    
    /// 处理 resume_chat 失败（服务端无记录，如后台重启）：移除临时恢复消息，保留已有部分回复，用简短提示收尾
    private func handleResumeFailure() {
        guard var conversation = currentConversation else { return }
        let assistantIndices = conversation.messages.indices.filter { conversation.messages[$0].role == .assistant }
        guard let lastIdx = assistantIndices.last else { return }
        
        let resumePlaceholders = ["正在恢复对话...", "已重连，正在恢复对话...", "连接断开，正在重连..."]
        let lastContent = conversation.messages[lastIdx].content
        let hint = "\n\n[回复已中断，可继续发送新消息]"
        
        if resumePlaceholders.contains(lastContent) {
            conversation.messages.remove(at: lastIdx)
            if assistantIndices.count >= 2 {
                let prevIdx = assistantIndices[assistantIndices.count - 2]
                let prevContent = conversation.messages[prevIdx].content
                if resumePlaceholders.contains(prevContent) {
                    conversation.messages[prevIdx].content = "[回复已中断，可继续发送新消息]"
                } else {
                    // 保留已有部分回复，追加简短提示
                    conversation.messages[prevIdx].content = prevContent + hint
                }
                conversation.messages[prevIdx].isStreaming = false
            } else {
                conversation.messages.append(Message(role: .assistant, content: "[回复已中断，可继续发送新消息]", isStreaming: false))
            }
        } else {
            conversation.messages[lastIdx].content = lastContent + hint
            conversation.messages[lastIdx].isStreaming = false
        }
        
        updateCurrentConversation(conversation, shouldSave: true)
        errorMessage = "该对话在服务端无记录（可能服务已重启），无法恢复。您可以继续发送新消息。"
    }
    
    private func updateAssistantMessage(content: String, isStreaming: Bool, modelName: String? = nil, attachments: [MessageAttachment]? = nil, tokenUsage: TokenUsage? = nil) {
        guard var conversation = currentConversation else { return }
        guard let lastIndex = conversation.messages.lastIndex(where: { $0.role == .assistant }) else { return }
        
        conversation.messages[lastIndex].content = content
        conversation.messages[lastIndex].isStreaming = isStreaming
        if let model = modelName {
            conversation.messages[lastIndex].modelName = model
        }
        if let usage = tokenUsage {
            conversation.messages[lastIndex].tokenUsage = usage
        }
        if let newAttachments = attachments {
            var existing = conversation.messages[lastIndex].attachments ?? []
            for newAtt in newAttachments {
                if !existing.contains(where: { $0.data == newAtt.data }) {
                    existing.append(newAtt)
                }
            }
            conversation.messages[lastIndex].attachments = existing
        }
        
        if !isStreaming {
            lastStreamingUIPushTime = nil
            lastStreamingSaveTime = nil
            updateCurrentConversation(conversation, shouldSave: true)
            return
        }
        // 流式时节流：减少 @Published 触发频率；但有附件更新时必须立即推送，否则截图不显示
        let hasAttachmentUpdate = attachments != nil && !(attachments?.isEmpty ?? true)
        let now = Date()
        if !hasAttachmentUpdate, let t = lastStreamingUIPushTime, now.timeIntervalSince(t) < streamingThrottleInterval {
            return
        }
        lastStreamingUIPushTime = now
        // 流式期间定期保存，断线/崩溃时保留部分回复
        let shouldSave = (lastStreamingSaveTime == nil || now.timeIntervalSince(lastStreamingSaveTime!) >= streamingSaveInterval)
        if shouldSave { lastStreamingSaveTime = now }
        updateCurrentConversation(conversation, shouldSave: shouldSave)
    }
    
    func clearActionLogs() {
        actionLogs = []
        executionLogs = []
        taskProgress = nil
        currentTaskId = nil
        currentIteration = 0
    }
    
    func clearExecutionLogs() {
        executionLogs = []
    }

    // MARK: - v3.4: MCP
    func loadMCPServers() async {
        isLoadingMCP = true
        mcpError = nil
        defer { isLoadingMCP = false }
        do {
            mcpServers = try await backendService.fetchMCPServers()
            mcpTools = try await backendService.fetchMCPTools()
        } catch {
            mcpError = error.localizedDescription
        }
    }

    func addMCPServer(name: String, transport: String, command: [String]?, url: String?) async {
        mcpError = nil
        do {
            try await backendService.addMCPServer(name: name, transport: transport, command: command, cmdUrl: url)
            await loadMCPServers()
        } catch {
            mcpError = "添加 MCP 服务失败: \(error.localizedDescription)"
        }
    }

    func deleteMCPServer(name: String) async {
        mcpError = nil
        do {
            try await backendService.deleteMCPServer(name: name)
            await loadMCPServers()
        } catch {
            mcpError = "删除失败: \(error.localizedDescription)"
        }
    }

    // MARK: - v3.4: Snapshots / Rollback
    func loadSnapshots(taskId: String? = nil) async {
        isLoadingSnapshots = true
        defer { isLoadingSnapshots = false }
        do {
            snapshots = try await backendService.fetchSnapshots(taskId: taskId)
        } catch {
            // 静默失败
        }
    }

    func rollback(snapshotId: String) async {
        rollbackMessage = nil
        do {
            let msg = try await backendService.rollbackSnapshot(snapshotId: snapshotId)
            rollbackMessage = "✅ \(msg)"
            await loadSnapshots()
        } catch {
            rollbackMessage = "❌ 回滚失败: \(error.localizedDescription)"
        }
    }

    // MARK: - v3.4: HITL
    func hitlConfirm(_ request: HitlRequest) async {
        pendingHitlRequests.removeAll { $0.id == request.id }
        do {
            try await backendService.hitlConfirm(actionId: request.actionId)
        } catch {
            errorMessage = "审批确认失败: \(error.localizedDescription)"
        }
    }

    func hitlReject(_ request: HitlRequest) async {
        pendingHitlRequests.removeAll { $0.id == request.id }
        do {
            try await backendService.hitlReject(actionId: request.actionId)
        } catch {
            errorMessage = "审批拒绝失败: \(error.localizedDescription)"
        }
    }

    // MARK: - v3.4: Feature Flags
    func loadFeatureFlags() async {
        isLoadingFeatureFlags = true
        defer { isLoadingFeatureFlags = false }
        do {
            featureFlags = try await backendService.fetchFeatureFlags()
        } catch {
            // 静默失败
        }
    }

    func setFeatureFlag(name: String, value: Any) async {
        do {
            try await backendService.updateFeatureFlag(name: name, value: value)
            await loadFeatureFlags()
        } catch {
            errorMessage = "FeatureFlag 更新失败: \(error.localizedDescription)"
        }
    }

    // MARK: - v3.4: Audit Logs
    func loadAuditLogs(limit: Int = 50, logType: String? = nil) async {
        isLoadingAuditLogs = true
        defer { isLoadingAuditLogs = false }
        do {
            auditLogs = try await backendService.fetchAuditLogs(limit: limit, logType: logType)
        } catch {
            // 静默失败
        }
    }

    // MARK: - v3.4: Context Visualization
    func loadContext() async {
        isLoadingContext = true
        defer { isLoadingContext = false }
        do {
            contextData = try await backendService.fetchContext()
        } catch {
            // 静默失败
        }
    }

    
    // MARK: - Chat Resume (断线重连恢复 chat 流)
    
    private func resumeChatStream(sessionId: String) async {
        guard var conversation = currentConversation else { return }
        
        // 参考 iOS 端：先结束之前 assistant 消息的 streaming 状态，避免多个气泡同时旋转
        endPreviousResumeMessageStreaming()
        // 重新读取 conversation（endPreviousResumeMessageStreaming 可能已更新）
        guard var conv = currentConversation else { return }
        conversation = conv
        
        // 仅当确实有未完成的 streaming 消息时才添加恢复占位消息
        let lastAssistant = conversation.messages.last(where: { $0.role == .assistant })
        let hasActiveStreaming = lastAssistant?.isStreaming == true
        
        if hasActiveStreaming {
            // 上一条消息本身就在 streaming，标记结束并追加恢复消息
            if let idx = conversation.messages.lastIndex(where: { $0.role == .assistant }) {
                conversation.messages[idx].isStreaming = false
                updateCurrentConversation(conversation, shouldSave: false)
                // 需要重新读取
                guard let c = currentConversation else { return }
                conversation = c
            }
        }
        
        let resumeMessage = Message(role: .assistant, content: "正在恢复对话...", isStreaming: true)
        conversation.messages.append(resumeMessage)
        updateCurrentConversation(conversation)
        
        isLoading = true
        var fullContent = ""
        var shouldSkipContent = false  // 用于去重：跳过已显示过的消息
        if ttsEnabled { TTSService.shared.resetStreamState() }
        
        do {
            for try await chunk in backendService.resumeChat(sessionId: sessionId) {
                switch chunk {
                case .chatResumeResult(let found, _, _, let messageId):
                    // 检查是否已显示过此消息
                    if let msgId = messageId, displayedMessageIds.contains(msgId) {
                        print("[Chat] Message \(msgId) already displayed, skipping resume")
                        shouldSkipContent = true
                        // 删除"正在恢复对话..."消息
                        if var conv = currentConversation,
                           let lastIdx = conv.messages.indices.last,
                           conv.messages[lastIdx].content == "正在恢复对话..." {
                            conv.messages.remove(at: lastIdx)
                            updateCurrentConversation(conv, shouldSave: false)
                        }
                        isLoading = false
                        return
                    }
                    // 记录消息 ID
                    if let msgId = messageId, found {
                        displayedMessageIds.insert(msgId)
                    }
                    continue
                    
                case .content(let text):
                    guard !shouldSkipContent else { continue }
                    fullContent += text
                    updateAssistantMessage(content: fullContent, isStreaming: true)
                    if ttsEnabled { TTSService.shared.appendAndSpeakStreamedContent(fullContent) }
                    
                case .toolCall(let name, let args):
                    let toolCall = ToolCall(
                        id: UUID().uuidString,
                        name: name,
                        arguments: args.mapValues { AnyCodable($0) }
                    )
                    recentToolCalls.insert(toolCall, at: 0)
                    if recentToolCalls.count > 10 {
                        recentToolCalls.removeLast()
                    }
                    
                case .toolResult(let name, let success, let result):
                    if let index = recentToolCalls.firstIndex(where: { $0.name == name && $0.result == nil }) {
                        recentToolCalls[index].result = ToolResult(success: success, output: result)
                    }
                    
                case .executionLog(let toolName, _, let level, let message):
                    executionLogs.append(ExecutionLogEntry(timestamp: Date(), level: level, message: message, toolName: toolName))

                case .llmRequestStart(let provider, let model, let iteration):
                    let llmId = "llm_chat_\(chatLlmRequestCounter)"
                    chatLlmRequestCounter += 1
                    let logEntry = ActionLogEntry(
                        actionId: llmId,
                        actionType: "llm_request",
                        reasoning: "请求 \(provider)/\(model)",
                        status: .executing,
                        output: nil,
                        error: nil,
                        timestamp: Date(),
                        iteration: iteration
                    )
                    actionLogs = actionLogs + [logEntry]

                case .llmRequestEnd(_, _, let iteration, let latencyMs, let usage, let responsePreview, let error):
                    let llmId = "llm_chat_\(max(0, chatLlmRequestCounter - 1))"
                    if let index = actionLogs.lastIndex(where: { $0.actionId == llmId }) {
                        let pt = usage["prompt_tokens"] as? Int ?? 0
                        let ct = usage["completion_tokens"] as? Int ?? 0
                        var out = "延迟: \(latencyMs)ms | 输入: \(pt) tokens | 输出: \(ct) tokens"
                        if let err = error, !err.isEmpty {
                            out += " | 错误: \(err)"
                        } else if let preview = responsePreview, !preview.isEmpty {
                            out += "\n预览: \(preview)"
                        }
                        let updated = ActionLogEntry(
                            actionId: llmId,
                            actionType: "llm_request",
                            reasoning: actionLogs[index].reasoning,
                            status: error != nil ? .failed : .success,
                            output: out,
                            error: error,
                            timestamp: actionLogs[index].timestamp,
                            iteration: iteration
                        )
                        var newLogs = actionLogs
                        newLogs[index] = updated
                        actionLogs = newLogs
                    }
                    
                case .imageData(let base64, let mimeType, let path):
                    let attachment = MessageAttachment.fromBase64(base64, mimeType: mimeType)
                    if let imagePath = path {
                        fullContent += "\n截图已保存: \(imagePath)\n"
                    }
                    updateAssistantMessage(content: fullContent, isStreaming: true, attachments: [attachment])
                    
                case .localImage(let path):
                    let attachment = MessageAttachment.fromLocalPath(path)
                    fullContent += "\n图片: \(path)\n"
                    updateAssistantMessage(content: fullContent, isStreaming: true, attachments: [attachment])
                    
                case .done(let model, let tokenUsage):
                    updateAssistantMessage(content: fullContent, isStreaming: false, modelName: model, tokenUsage: tokenUsage)
                    if ttsEnabled { TTSService.shared.speakRemainingBuffer() }
                    
                case .stopped:
                    updateAssistantMessage(content: fullContent + "\n\n[已终止]", isStreaming: false)
                    
                case .error(let message):
                    errorMessage = message
                    updateAssistantMessage(content: "错误: \(message)", isStreaming: false)
                    
                default:
                    break
                }
            }
            
            if !fullContent.isEmpty {
                updateAssistantMessage(content: fullContent, isStreaming: false)
            } else {
                // 服务端无该会话记录（例如后台重启），无法恢复流式输出
                // 不将长错误文案写入对话历史，改用简短提示 + errorMessage（toast 展示）
                handleResumeFailure()
            }
            
        } catch {
            errorMessage = "Chat 恢复失败: \(error.localizedDescription)"
            updateAssistantMessage(
                content: fullContent.isEmpty ? "恢复失败: \(error.localizedDescription)" : fullContent,
                isStreaming: false
            )
        }
        
        isLoading = false
    }
    
    private func updateCurrentConversation(_ conversation: Conversation, shouldSave: Bool = true) {
        // 同步更新以避免竞态条件
        var updatedConversation = conversation
        updatedConversation.updatedAt = Date()
        
        if updatedConversation.messages.count == 2 {
            let firstUserMessage = updatedConversation.messages.first { $0.role == .user }
            if let content = firstUserMessage?.content {
                updatedConversation.title = String(content.prefix(30))
            }
        }
        
        self.currentConversation = updatedConversation
        
        if let index = self.conversations.firstIndex(where: { $0.id == updatedConversation.id }) {
            self.conversations[index] = updatedConversation
        }
        
        // 只在流结束时保存，避免频繁写入
        if shouldSave {
            self.saveConversations()
        }
    }
    
    // MARK: - Message Editing
    
    func editMessage(_ message: Message) {
        guard var conversation = currentConversation else { return }
        guard let messageIndex = conversation.messages.firstIndex(where: { $0.id == message.id }) else { return }
        
        // 将消息内容复制到输入框
        inputText = message.content
        
        // 删除该消息及其之后的所有消息
        conversation.messages.removeSubrange(messageIndex...)
        
        updateCurrentConversation(conversation)
    }
    
    func deleteMessage(_ message: Message) {
        guard var conversation = currentConversation else { return }
        guard let messageIndex = conversation.messages.firstIndex(where: { $0.id == message.id }) else { return }
        
        // 如果是用户消息，同时删除紧跟的助手回复
        if message.role == .user {
            let nextIndex = messageIndex + 1
            if nextIndex < conversation.messages.count && conversation.messages[nextIndex].role == .assistant {
                conversation.messages.remove(at: nextIndex)
            }
        }
        
        conversation.messages.remove(at: messageIndex)
        updateCurrentConversation(conversation)
    }
    
    // MARK: - System Notifications
    
    func loadSystemMessages(category: NotificationCategory? = nil) {
        Task {
            do {
                let cat = category?.rawValue
                let (messages, unreadCount) = try await backendService.fetchSystemMessages(category: cat)
                self.systemNotifications = messages
                self.unreadNotificationCount = unreadCount
            } catch {
                // 静默失败，不阻塞主流程
            }
        }
    }
    
    /// 当前 Tab 下展示的通知列表（按选中的分类筛选）
    var filteredSystemNotifications: [SystemNotification] {
        guard let cat = selectedNotificationTab.category else { return systemNotifications }
        return systemNotifications.filter { $0.category == cat }
    }
    
    func markNotificationRead(_ notification: SystemNotification) {
        Task {
            do {
                let unreadCount = try await backendService.markSystemMessageRead(notification.id)
                if let idx = self.systemNotifications.firstIndex(where: { $0.id == notification.id }) {
                    self.systemNotifications[idx].read = true
                }
                self.unreadNotificationCount = unreadCount
            } catch {
                // 静默失败
            }
        }
    }
    
    func markAllNotificationsRead() {
        Task {
            do {
                try await backendService.markAllSystemMessagesRead()
                for i in self.systemNotifications.indices {
                    self.systemNotifications[i].read = true
                }
                self.unreadNotificationCount = 0
            } catch {
                // 静默失败
            }
        }
    }
    
    func clearNotifications() {
        Task {
            do {
                try await backendService.clearSystemMessages()
                self.systemNotifications = []
                self.unreadNotificationCount = 0
            } catch {
                // 静默失败
            }
        }
    }

    @Published var clearCacheMessage: String?
    @Published var isClearingCache = false

    /// 清理缓存：清除 traces、任务检查点、chat 会话数据等，保留配置文件
    func clearCache() {
        guard !isClearingCache else { return }
        isClearingCache = true
        clearCacheMessage = nil
        Task {
            do {
                let (deleted, message) = try await backendService.clearCache()
                await MainActor.run {
                    clearCacheMessage = "✅ \(message)"
                    isClearingCache = false
                }
                // 3 秒后清除提示
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                await MainActor.run { clearCacheMessage = nil }
            } catch {
                await MainActor.run {
                    clearCacheMessage = "❌ 清理失败: \(error.localizedDescription)"
                    isClearingCache = false
                }
            }
        }
    }
    
    // MARK: - UI
    
    func toggleToolPanel() {
        showToolPanel.toggle()
    }
    
    // MARK: - Global Monitor Events
    
    /// 处理来自任意客户端的全局监控事件
    private func handleMonitorEvent(sourceSession: String, taskId: String, event: [String: Any]) {
        onMonitorEventToMonitor?(sourceSession, taskId, event)

        guard let eventType = event["type"] as? String else { return }
        
        print("[Monitor] Received event: type=\(eventType), taskId=\(taskId), session=\(sourceSession)")
        
        switch eventType {
        case "task_start":
            let taskDesc = event["task"] as? String ?? ""
            taskProgress = TaskProgress(
                id: taskId,
                taskDescription: taskDesc,
                status: .running,
                currentIteration: 0,
                totalActions: 0,
                successfulActions: 0,
                failedActions: 0,
                startTime: Date()
            )
            
        case "llm_request_start":
            isStreamingLLM = true
            let provider = event["provider"] as? String ?? "unknown"
            let model = event["model"] as? String ?? ""
            let iteration = event["iteration"] as? Int ?? 0
            let llmId = "llm_\(iteration)_\(taskId)"
            let logEntry = ActionLogEntry(
                actionId: llmId,
                actionType: "llm_request",
                reasoning: "请求 \(provider)/\(model)",
                status: .executing,
                output: nil,
                error: nil,
                timestamp: Date(),
                iteration: iteration
            )
            actionLogs = actionLogs + [logEntry]
            
        case "llm_request_end":
            isStreamingLLM = false
            let iteration = event["iteration"] as? Int ?? 0
            let latencyMs = event["latency_ms"] as? Int ?? 0
            let usage = event["usage"] as? [String: Any] ?? [:]
            let error = event["error"] as? String
            let llmId = "llm_\(iteration)_\(taskId)"
            if let index = actionLogs.firstIndex(where: { $0.actionId == llmId }) {
                let pt = usage["prompt_tokens"] as? Int ?? 0
                let ct = usage["completion_tokens"] as? Int ?? 0
                var out = "延迟: \(latencyMs)ms | 输入: \(pt) tokens | 输出: \(ct) tokens"
                if let err = error, !err.isEmpty {
                    out += " | 错误: \(err)"
                }
                let updated = ActionLogEntry(
                    actionId: llmId,
                    actionType: "llm_request",
                    reasoning: actionLogs[index].reasoning,
                    status: error != nil ? .failed : .success,
                    output: out,
                    error: error,
                    timestamp: actionLogs[index].timestamp,
                    iteration: iteration
                )
                var newLogs = actionLogs
                newLogs[index] = updated
                actionLogs = newLogs
            }
            
        case "action_plan":
            let action = event["action"] as? [String: Any] ?? [:]
            let iteration = event["iteration"] as? Int ?? 0
            currentIteration = iteration
            let actionType = action["action_type"] as? String ?? "unknown"
            let reasoning = action["reasoning"] as? String ?? ""
            let actionId = action["action_id"] as? String ?? UUID().uuidString
            let params = action["params"] as? [String: Any] ?? [:]
            let paramsSummary = Self.buildParamsSummary(actionType: actionType, params: params)

            let logEntry = ActionLogEntry(
                actionId: actionId,
                actionType: actionType,
                reasoning: reasoning,
                status: .pending,
                output: nil,
                error: nil,
                timestamp: Date(),
                iteration: iteration,
                paramsSummary: paramsSummary
            )
            actionLogs.append(logEntry)

        case "action_executing":
            let actionId = event["action_id"] as? String ?? ""
            if let index = actionLogs.firstIndex(where: { $0.actionId == actionId }) {
                let e = actionLogs[index]
                actionLogs[index] = ActionLogEntry(
                    actionId: actionId,
                    actionType: e.actionType,
                    reasoning: e.reasoning,
                    status: .executing,
                    output: nil,
                    error: nil,
                    timestamp: e.timestamp,
                    iteration: e.iteration,
                    paramsSummary: e.paramsSummary
                )
            }

        case "action_result":
            let actionId = event["action_id"] as? String ?? ""
            let success = event["success"] as? Bool ?? false
            let output = event["output"] as? String
            let error = event["error"] as? String
            
            var actionType = "unknown"
            if let index = actionLogs.firstIndex(where: { $0.actionId == actionId }) {
                let e = actionLogs[index]
                actionType = e.actionType
                actionLogs[index] = ActionLogEntry(
                    actionId: actionId,
                    actionType: actionType,
                    reasoning: e.reasoning,
                    status: success ? .success : .failed,
                    output: output,
                    error: error,
                    timestamp: e.timestamp,
                    iteration: e.iteration,
                    paramsSummary: e.paramsSummary
                )
            }

            // 更新任务进度
            if success {
                taskProgress?.successfulActions = (taskProgress?.successfulActions ?? 0) + 1
            } else {
                taskProgress?.failedActions = (taskProgress?.failedActions ?? 0) + 1
            }
            taskProgress?.totalActions = (taskProgress?.successfulActions ?? 0) + (taskProgress?.failedActions ?? 0)
            
            // 写入 executionLogs（非 llm_request 类型）
            if actionType != "llm_request" {
                let outStr = output ?? error ?? ""
                let level = success ? "info" : "error"
                let msg = success ? (outStr.isEmpty ? "成功" : String(outStr.prefix(500))) : (error ?? "失败")
                executionLogs.append(ExecutionLogEntry(timestamp: Date(), level: level, message: msg, toolName: actionType))
            }
            
        case "task_complete":
            let success = event["success"] as? Bool ?? false
            let summary = event["summary"] as? String ?? ""
            taskProgress?.status = success ? .completed : .failed
            taskProgress?.endTime = Date()
            taskProgress?.summary = summary
            isStreamingLLM = false
            
        case "task_stopped", "error":
            taskProgress?.status = .failed
            taskProgress?.endTime = Date()
            isStreamingLLM = false
            
        default:
            break
        }
    }

    // MARK: - Chow Duck

    func loadDuckData() async {
        isLoadingDucks = true
        defer { isLoadingDucks = false }
        do {
            async let listResult = backendService.fetchDuckList()
            async let templatesResult = backendService.fetchDuckTemplates()
            async let eggsResult = backendService.fetchEggs()
            async let statsResult = backendService.fetchDuckStats()
            duckList = try await listResult
            duckTemplates = try await templatesResult
            duckEggs = try await eggsResult
            duckStats = try await statsResult
            duckError = nil
        } catch {
            duckError = "加载 Duck 数据失败: \(error.localizedDescription)"
        }
    }

    /// 轻量刷新：仅更新 duckList，供顶部状态栏定期轮询使用
    func refreshDuckStatus() async {
        guard chowDuckEnabled else { return }
        do {
            duckList = try await backendService.fetchDuckList()
        } catch {
            // 静默失败，不影响主界面
        }
    }

    func createLocalDuck(name: String, duckType: String, skills: [String]) async {
        do {
            _ = try await backendService.createLocalDuck(name: name, duckType: duckType, skills: skills)
            await loadDuckData()
        } catch {
            duckError = "创建本地 Duck 失败: \(error.localizedDescription)"
        }
    }

    func destroyLocalDuck(duckId: String) async {
        do {
            try await backendService.destroyLocalDuck(duckId: duckId)
            await loadDuckData()
        } catch {
            duckError = "销毁本地 Duck 失败: \(error.localizedDescription)"
        }
    }

    func startLocalDuck(duckId: String) async {
        do {
            _ = try await backendService.startLocalDuck(duckId: duckId)
            await loadDuckData()
        } catch {
            duckError = "启动本地 Duck 失败: \(error.localizedDescription)"
        }
    }

    /// 获取主 Agent 已配置的在线 LLM 列表，供子 Duck 配置时一键导入
    func fetchMainAgentLLMProviders() async -> [[String: Any]] {
        do {
            return try await backendService.fetchMainAgentLLMProviders()
        } catch {
            return []
        }
    }

    /// 更新分身 LLM 配置（引用主配置中的 provider，运行时动态解析）
    func updateDuckLLMConfig(duckId: String, apiKey: String, baseUrl: String, model: String, providerRef: String = "") async {
        do {
            _ = try await backendService.updateDuckLLMConfig(duckId: duckId, apiKey: apiKey, baseUrl: baseUrl, model: model, providerRef: providerRef)
            await loadDuckData()
        } catch {
            duckError = "更新分身 LLM 配置失败: \(error.localizedDescription)"
        }
    }

    func removeDuck(duckId: String) async {
        do {
            try await backendService.removeDuck(duckId: duckId)
            await loadDuckData()
        } catch {
            duckError = "移除 Duck 失败: \(error.localizedDescription)"
        }
    }

    func createEgg(duckType: String, name: String?) async -> [String: Any]? {
        do {
            let result = try await backendService.createEgg(duckType: duckType, name: name)
            await loadDuckData()
            return result
        } catch {
            duckError = "生成 Egg 失败: \(error.localizedDescription)"
            return nil
        }
    }

    func deleteEgg(eggId: String) async {
        do {
            try await backendService.deleteEgg(eggId: eggId)
            await loadDuckData()
        } catch {
            duckError = "删除 Egg 失败: \(error.localizedDescription)"
        }
    }

    func eggDownloadURL(eggId: String) -> URL? {
        backendService.eggDownloadURL(eggId: eggId)
    }

    // MARK: - Scheduled Tasks

    func loadScheduledTasks() async {
        isLoadingScheduledTasks = true
        defer { isLoadingScheduledTasks = false }
        do {
            scheduledTasks = try await backendService.fetchScheduledTasks()
        } catch {
            // 静默失败
        }
    }

    func createScheduledTask(description: String, triggerType: String, triggerConfig: [String: Any], sessionId: String = "") async {
        do {
            _ = try await backendService.createScheduledTask(
                description: description,
                triggerType: triggerType,
                triggerConfig: triggerConfig,
                sessionId: sessionId
            )
            await loadScheduledTasks()
        } catch {
            errorMessage = "创建定时任务失败: \(error.localizedDescription)"
        }
    }

    func pauseScheduledTask(taskId: String) async {
        do {
            try await backendService.pauseScheduledTask(taskId: taskId)
            await loadScheduledTasks()
        } catch {
            errorMessage = "暂停定时任务失败: \(error.localizedDescription)"
        }
    }

    func resumeScheduledTask(taskId: String) async {
        do {
            try await backendService.resumeScheduledTask(taskId: taskId)
            await loadScheduledTasks()
        } catch {
            errorMessage = "恢复定时任务失败: \(error.localizedDescription)"
        }
    }

    func deleteScheduledTask(taskId: String) async {
        do {
            try await backendService.deleteScheduledTask(taskId: taskId)
            await loadScheduledTasks()
        } catch {
            errorMessage = "删除定时任务失败: \(error.localizedDescription)"
        }
    }

    // MARK: - Circuit Breakers

    func loadCircuitBreakers() async {
        isLoadingCircuitBreakers = true
        defer { isLoadingCircuitBreakers = false }
        do {
            circuitBreakers = try await backendService.fetchCircuitBreakers()
        } catch {
            // 静默失败
        }
    }

}
