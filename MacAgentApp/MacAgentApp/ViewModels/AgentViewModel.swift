import SwiftUI
import Combine

@MainActor
class AgentViewModel: ObservableObject {
    // MARK: - Published Properties
    
    @Published var conversations: [Conversation] = []
    @Published var currentConversation: Conversation?
    @Published var inputText: String = ""
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
    
    // MARK: - Settings
    
    @AppStorage("provider") var provider: String = "deepseek"
    @AppStorage("apiKey") var apiKey: String = ""
    @AppStorage("baseUrl") var baseUrl: String = "https://api.deepseek.com"
    @AppStorage("model") var model: String = "deepseek-chat"
    @AppStorage("ollamaUrl") var ollamaUrl: String = "http://localhost:11434/v1"
    @AppStorage("ollamaModel") var ollamaModel: String = "deepseek-r1:8b"
    @AppStorage("lmStudioUrl") var lmStudioUrl: String = "http://localhost:1234/v1"
    @AppStorage("lmStudioModel") var lmStudioModel: String = ""
    /// New API 转发，默认使用 cc1 地址，配置说明见语雀文档
    @AppStorage("newApiKey") var newApiKey: String = ""
    @AppStorage("newApiBaseUrl") var newApiBaseUrl: String = "https://cc1.newapi.ai/v1"
    @AppStorage("newApiModel") var newApiModel: String = ""
    
    // 邮件 SMTP 配置（用于系统级发信，不依赖 Mail.app）
    @AppStorage("smtpServer") var smtpServer: String = "smtp.qq.com"
    @AppStorage("smtpPort") var smtpPort: String = "465"
    @AppStorage("smtpUser") var smtpUser: String = ""
    @AppStorage("smtpPassword") var smtpPassword: String = ""
    
    // GitHub Token（拉取开放技能源，提高 API 限额）
    @AppStorage("githubToken") var githubToken: String = ""
    @Published var githubConfigured: Bool = false
    
    // 待审批工具（签名校验未通过）
    @Published var pendingTools: [PendingTool] = []
    @Published var approvingToolName: String? = nil
    
    // 本地可用模型列表
    @Published var availableLocalModels: [String] = []
    @Published var isLoadingModels = false
    
    // MARK: - Private Properties
    
    private let backendService = BackendService()
    private var cancellables = Set<AnyCancellable>()
    private var currentSendTask: Task<Void, Never>?
    
    // MARK: - Initialization
    
    init() {
        // 一次性迁移：曾用旧默认地址的改为 cc1 默认地址
        if newApiBaseUrl == "http://localhost:3000/v1" {
            newApiBaseUrl = "https://cc1.newapi.ai/v1"
        }
        setupSubscriptions()
        Task { @MainActor in
            loadConversations()
            if currentConversation == nil {
                newConversation()
            }
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
                await self.resumeAutonomousTask(sessionId: conversation.id.uuidString, taskId: taskId)
            }
        }
        
        backendService.onChatResumeDetected = { [weak self] sessionId in
            guard let self = self else { return }
            Task { @MainActor in
                await self.resumeChatStream(sessionId: sessionId)
            }
        }
    }
    
    // MARK: - Connection
    
    func connect() {
        Task {
            await backendService.connect()
            await loadTools()
            await syncConfig()
            await loadGitHubConfig()
            loadSystemMessages()
        }
    }
    
    func disconnect() {
        backendService.disconnect()
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
        default:
            configApiKey = apiKey
            configBaseUrl = baseUrl
            configModel = model
        }
        
        do {
            try await backendService.updateConfig(
                provider: provider,
                apiKey: configApiKey,
                baseUrl: configBaseUrl,
                model: configModel
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
    
    func sendMessage() {
        guard !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        guard var conversation = currentConversation else { return }
        
        let userMessage = Message(role: .user, content: inputText)
        conversation.messages.append(userMessage)
        
        let assistantMessage = Message(role: .assistant, content: "", isStreaming: true)
        conversation.messages.append(assistantMessage)
        
        let messageText = inputText
        inputText = ""
        
        updateCurrentConversation(conversation)
        isLoading = true
        executionLogs = []
        
        let conversationId = conversation.id.uuidString
        
        currentSendTask = Task {
            defer {
                Task { @MainActor in
                    isLoading = false
                    currentSendTask = nil
                }
            }
            await sendMessageWithRetry(messageText, sessionId: conversationId, retryCount: 0)
        }
    }
    
    func stopTask() {
        guard isLoading, let conversation = currentConversation else { return }
        currentSendTask?.cancel()
        currentSendTask = nil
        isLoading = false
        
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
    
    private func sendMessageWithRetry(_ messageText: String, sessionId: String, retryCount: Int) async {
        do {
            var fullContent = ""
            
            for try await chunk in backendService.sendMessageStream(messageText, sessionId: sessionId) {
                switch chunk {
                case .content(let text):
                    fullContent += text
                    updateAssistantMessage(content: fullContent, isStreaming: true)
                    
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
                    
                case .taskStart, .modelSelected, .actionPlan, .actionExecuting, .actionResult, .reflectStart, .reflectResult, .taskComplete:
                    break
                }
            }
            
            if !fullContent.isEmpty {
                updateAssistantMessage(content: fullContent, isStreaming: false)
            }
            
        } catch is CancellationError {
            return
        } catch {
            if retryCount < 1 {
                errorMessage = "连接断开，正在重连..."
                updateAssistantMessage(content: "连接断开，正在重连...", isStreaming: true)
                
                await backendService.reconnect()
                
                if isConnected {
                    updateAssistantMessage(content: "已重连，正在恢复对话...", isStreaming: true)
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
    
    private func updateAssistantMessage(content: String, isStreaming: Bool, modelName: String? = nil, attachments: [MessageAttachment]? = nil, tokenUsage: TokenUsage? = nil) {
        guard var conversation = currentConversation else { return }
        
        if let lastIndex = conversation.messages.lastIndex(where: { $0.role == .assistant }) {
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
                // 去重：检查是否已存在相同的 attachment（通过 data 比较）
                for newAtt in newAttachments {
                    if !existing.contains(where: { $0.data == newAtt.data }) {
                        existing.append(newAtt)
                    }
                }
                conversation.messages[lastIndex].attachments = existing
            }
            updateCurrentConversation(conversation, shouldSave: !isStreaming)
        }
    }
    
    // MARK: - Autonomous Execution
    
    func sendAutonomousTask() {
        guard !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        guard var conversation = currentConversation else { return }
        
        let userMessage = Message(role: .user, content: "🤖 [自主任务] \(inputText)")
        conversation.messages.append(userMessage)
        
        let assistantMessage = Message(role: .assistant, content: "正在启动自主执行...", isStreaming: true)
        conversation.messages.append(assistantMessage)
        
        let task = inputText
        inputText = ""
        
        updateCurrentConversation(conversation)
        isLoading = true
        
        actionLogs = []
        currentIteration = 0
        
        let sessionId = conversation.id.uuidString
        
        currentSendTask = Task {
            defer {
                Task { @MainActor in
                    isLoading = false
                    currentSendTask = nil
                }
            }
            await executeAutonomousTask(task, sessionId: sessionId)
        }
    }
    
    private func executeAutonomousTask(_ task: String, sessionId: String) async {
        var statusContent = ""
        var completedActions = 0
        var failedActions = 0
        
        // Reset model selection state
        selectedModelType = nil
        selectedModelReason = nil
        taskAnalysisType = nil
        taskComplexity = 0
        executionLogs = []
        
        var retryCount = 0
        retryLoop: while true {
            do {
                for try await chunk in backendService.sendAutonomousTask(
                    task,
                    sessionId: sessionId
                ) {
                    switch chunk {
                case .modelSelected(let modelType, let reason, let taskType, let complexity):
                    selectedModelType = modelType
                    selectedModelReason = reason
                    taskAnalysisType = taskType
                    taskComplexity = complexity
                    
                    let modelIcon = modelType == "local" ? "🏠" : "☁️"
                    let modelName = modelType == "local" ? "本地模型" : "远程模型"
                    statusContent = "\(modelIcon) 选择模型: \(modelName)\n"
                    statusContent += "📊 任务类型: \(taskType) (复杂度: \(complexity)/10)\n"
                    statusContent += "💡 原因: \(reason)\n\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .taskStart(let taskId, _):
                    currentTaskId = taskId
                    taskProgress = TaskProgress(
                        id: taskId,
                        taskDescription: task,
                        status: .running,
                        currentIteration: 0,
                        totalActions: 0,
                        successfulActions: 0,
                        failedActions: 0,
                        startTime: Date()
                    )
                    statusContent += "🚀 任务开始执行...\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .actionPlan(let action, let iteration):
                    currentIteration = iteration
                    let actionType = action["action_type"] as? String ?? "unknown"
                    let reasoning = action["reasoning"] as? String ?? ""
                    
                    let logEntry = ActionLogEntry(
                        actionId: action["action_id"] as? String ?? UUID().uuidString,
                        actionType: actionType,
                        reasoning: reasoning,
                        status: .pending,
                        output: nil,
                        error: nil,
                        timestamp: Date(),
                        iteration: iteration
                    )
                    actionLogs.append(logEntry)
                    
                    statusContent += "\n📋 步骤 \(iteration): \(actionType)\n   → \(reasoning)\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .actionExecuting(let actionId, let actionType):
                    if let index = actionLogs.firstIndex(where: { $0.actionId == actionId }) {
                        actionLogs[index] = ActionLogEntry(
                            actionId: actionId,
                            actionType: actionLogs[index].actionType,
                            reasoning: actionLogs[index].reasoning,
                            status: .executing,
                            output: nil,
                            error: nil,
                            timestamp: actionLogs[index].timestamp,
                            iteration: actionLogs[index].iteration
                        )
                    }
                    statusContent += "   ⏳ 执行中: \(actionType)...\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .actionResult(let actionId, let success, let output, let error):
                    if let index = actionLogs.firstIndex(where: { $0.actionId == actionId }) {
                        actionLogs[index] = ActionLogEntry(
                            actionId: actionId,
                            actionType: actionLogs[index].actionType,
                            reasoning: actionLogs[index].reasoning,
                            status: success ? .success : .failed,
                            output: output,
                            error: error,
                            timestamp: actionLogs[index].timestamp,
                            iteration: actionLogs[index].iteration
                        )
                    }
                    
                    if success {
                        completedActions += 1
                        let outputPreview = output?.prefix(100) ?? ""
                        statusContent += "   ✅ 成功\(outputPreview.isEmpty ? "" : ": \(outputPreview)...")\n"
                        // 若 output 为截图结果 JSON，解析 screenshot_path 并在聊天中展示图片
                        var screenshotAttachment: MessageAttachment?
                        if let out = output?.data(using: .utf8),
                           let obj = try? JSONSerialization.jsonObject(with: out) as? [String: Any],
                           let path = obj["screenshot_path"] as? String ?? obj["path"] as? String,
                           !path.isEmpty {
                            screenshotAttachment = MessageAttachment.fromLocalPath(path)
                        }
                        if let att = screenshotAttachment {
                            statusContent += "\n📷 截图已生成\n"
                            updateAssistantMessage(content: statusContent, isStreaming: true, attachments: [att])
                        } else {
                            updateAssistantMessage(content: statusContent, isStreaming: true)
                        }
                    } else {
                        failedActions += 1
                        statusContent += "   ❌ 失败: \(error ?? "未知错误")\n"
                        updateAssistantMessage(content: statusContent, isStreaming: true)
                    }
                    
                    taskProgress?.totalActions = completedActions + failedActions
                    taskProgress?.successfulActions = completedActions
                    taskProgress?.failedActions = failedActions
                    
                case .reflectStart:
                    statusContent += "\n🔍 正在分析执行结果...\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .reflectResult(let reflection):
                    statusContent += "💡 反思结果:\n\(reflection)\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .taskComplete(_, let success, let summary, let totalActions):
                    taskProgress?.status = success ? .completed : .failed
                    taskProgress?.endTime = Date()
                    taskProgress?.summary = summary
                    
                    let statusIcon = success ? "✅" : "⚠️"
                    statusContent += "\n\(statusIcon) 任务完成\n"
                    statusContent += "📊 统计: \(totalActions) 个动作, \(completedActions) 成功, \(failedActions) 失败\n"
                    statusContent += "📝 总结: \(summary)\n"
                    // 任务已完成，先停止菊花；若后续还有反思结果会继续追加内容，但不再转圈
                    updateAssistantMessage(content: statusContent, isStreaming: false)
                    
                case .content(let text):
                    statusContent += text
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .done(let model, let tokenUsage):
                    updateAssistantMessage(content: statusContent, isStreaming: false, modelName: model, tokenUsage: tokenUsage)
                    
                case .error(let message):
                    statusContent += "\n❌ 错误: \(message)\n"
                    updateAssistantMessage(content: statusContent, isStreaming: false)
                    errorMessage = message
                    
                case .imageData(let base64, let mimeType, let path):
                    // 合并附件和内容更新为一次调用，避免竞态条件
                    let attachment = MessageAttachment.fromBase64(base64, mimeType: mimeType)
                    if let imagePath = path {
                        statusContent += "\n📷 截图已生成: \(imagePath)\n"
                    }
                    updateAssistantMessage(content: statusContent, isStreaming: true, attachments: [attachment])
                    
                case .localImage(let path):
                    let localAttachment = MessageAttachment.fromLocalPath(path)
                    statusContent += "\n📷 图片: \(path)\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true, attachments: [localAttachment])
                    
                case .toolCall(let name, _):
                    statusContent += "🔧 调用工具: \(name)\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .toolResult(let name, let success, let result):
                    let icon = success ? "✅" : "❌"
                    statusContent += "\(icon) \(name): \(result)\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .executionLog(let toolName, _, let level, let message):
                    executionLogs.append(ExecutionLogEntry(timestamp: Date(), level: level, message: message, toolName: toolName))
                    
                case .stopped:
                    statusContent += "\n\n[已终止]"
                    updateAssistantMessage(content: statusContent, isStreaming: false)
                }
        
                }
                break retryLoop
            } catch is CancellationError {
                statusContent += "\n\n[已终止]"
                updateAssistantMessage(content: statusContent, isStreaming: false)
                return
            } catch {
                if retryCount < 1 && isConnectionError(error) {
                    retryCount += 1
                    updateAssistantMessage(content: statusContent + "\n\n连接断开，正在重连...", isStreaming: true)
                    await backendService.reconnect()
                    if isConnected {
                        updateAssistantMessage(content: statusContent + "\n已重连，正在重新执行...", isStreaming: true)
                        continue retryLoop
                    }
                }
                errorMessage = "自主执行失败: \(error.localizedDescription)"
                updateAssistantMessage(
                    content: statusContent + "\n❌ 执行失败: \(error.localizedDescription)",
                    isStreaming: false
                )
                return
            }
        }
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
    
    // MARK: - Task Resume (断线重连恢复)
    
    private func resumeAutonomousTask(sessionId: String, taskId: String?) async {
        guard var conversation = currentConversation else { return }
        
        // 添加一条恢复消息
        let resumeMessage = Message(role: .assistant, content: "🔄 检测到任务正在运行，正在恢复...\n任务ID: \(taskId ?? "unknown")", isStreaming: true)
        conversation.messages.append(resumeMessage)
        updateCurrentConversation(conversation)
        
        isLoading = true
        
        var statusContent = "🔄 正在恢复任务...\n"
        var completedActions = 0
        var failedActions = 0
        var retryCount = 0
        retryLoop: while true {
            do {
                for try await chunk in backendService.resumeTask(sessionId: sessionId) {
                switch chunk {
                case .modelSelected(let modelType, let reason, let taskType, let complexity):
                    selectedModelType = modelType
                    selectedModelReason = reason
                    taskAnalysisType = taskType
                    taskComplexity = complexity
                    
                    let modelIcon = modelType == "local" ? "🏠" : "☁️"
                    let modelName = modelType == "local" ? "本地模型" : "远程模型"
                    statusContent += "\(modelIcon) 模型: \(modelName) | 任务类型: \(taskType) (复杂度: \(complexity)/10)\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .taskStart(let recoveredTaskId, let taskDesc):
                    currentTaskId = recoveredTaskId
                    taskProgress = TaskProgress(
                        id: recoveredTaskId,
                        taskDescription: taskDesc,
                        status: .running,
                        currentIteration: 0,
                        totalActions: 0,
                        successfulActions: 0,
                        failedActions: 0,
                        startTime: Date()
                    )
                    statusContent += "✅ 任务已恢复: \(taskDesc)\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .actionPlan(let action, let iteration):
                    currentIteration = iteration
                    let actionType = action["action_type"] as? String ?? "unknown"
                    let reasoning = action["reasoning"] as? String ?? ""
                    
                    let logEntry = ActionLogEntry(
                        actionId: action["action_id"] as? String ?? UUID().uuidString,
                        actionType: actionType,
                        reasoning: reasoning,
                        status: .pending,
                        output: nil,
                        error: nil,
                        timestamp: Date(),
                        iteration: iteration
                    )
                    actionLogs.append(logEntry)
                    
                    statusContent += "\n📋 步骤 \(iteration): \(actionType)\n   → \(reasoning)\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .actionExecuting(let actionId, let actionType):
                    if let index = actionLogs.firstIndex(where: { $0.actionId == actionId }) {
                        actionLogs[index] = ActionLogEntry(
                            actionId: actionId,
                            actionType: actionLogs[index].actionType,
                            reasoning: actionLogs[index].reasoning,
                            status: .executing,
                            output: nil,
                            error: nil,
                            timestamp: actionLogs[index].timestamp,
                            iteration: actionLogs[index].iteration
                        )
                    }
                    statusContent += "   ⏳ 执行中: \(actionType)...\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .actionResult(let actionId, let success, let output, let error):
                    if let index = actionLogs.firstIndex(where: { $0.actionId == actionId }) {
                        actionLogs[index] = ActionLogEntry(
                            actionId: actionId,
                            actionType: actionLogs[index].actionType,
                            reasoning: actionLogs[index].reasoning,
                            status: success ? .success : .failed,
                            output: output,
                            error: error,
                            timestamp: actionLogs[index].timestamp,
                            iteration: actionLogs[index].iteration
                        )
                    }
                    
                    if success {
                        completedActions += 1
                        let outputPreview = output?.prefix(100) ?? ""
                        statusContent += "   ✅ 成功\(outputPreview.isEmpty ? "" : ": \(outputPreview)...")\n"
                        // 若 output 为截图结果 JSON，解析 screenshot_path 并在聊天中展示图片
                        var screenshotAttachment: MessageAttachment?
                        if let out = output?.data(using: .utf8),
                           let obj = try? JSONSerialization.jsonObject(with: out) as? [String: Any],
                           let path = obj["screenshot_path"] as? String ?? obj["path"] as? String,
                           !path.isEmpty {
                            screenshotAttachment = MessageAttachment.fromLocalPath(path)
                        }
                        if let att = screenshotAttachment {
                            statusContent += "\n📷 截图已生成\n"
                            updateAssistantMessage(content: statusContent, isStreaming: true, attachments: [att])
                        } else {
                            updateAssistantMessage(content: statusContent, isStreaming: true)
                        }
                    } else {
                        failedActions += 1
                        statusContent += "   ❌ 失败: \(error ?? "未知错误")\n"
                        updateAssistantMessage(content: statusContent, isStreaming: true)
                    }
                    
                    taskProgress?.totalActions = completedActions + failedActions
                    taskProgress?.successfulActions = completedActions
                    taskProgress?.failedActions = failedActions
                    
                case .reflectStart:
                    statusContent += "\n🔍 正在分析执行结果...\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .reflectResult(let reflection):
                    statusContent += "💡 反思结果:\n\(reflection)\n"
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .taskComplete(_, let success, let summary, let totalActions):
                    taskProgress?.status = success ? .completed : .failed
                    taskProgress?.endTime = Date()
                    taskProgress?.summary = summary
                    
                    let statusIcon = success ? "✅" : "⚠️"
                    statusContent += "\n\(statusIcon) 任务完成\n"
                    statusContent += "📊 统计: \(totalActions) 个动作, \(completedActions) 成功, \(failedActions) 失败\n"
                    statusContent += "📝 总结: \(summary)\n"
                    // 任务已完成，先停止菊花；若后续还有反思结果会继续追加内容，但不再转圈
                    updateAssistantMessage(content: statusContent, isStreaming: false)
                    
                case .content(let text):
                    statusContent += text
                    updateAssistantMessage(content: statusContent, isStreaming: true)
                    
                case .done(let model, let tokenUsage):
                    updateAssistantMessage(content: statusContent, isStreaming: false, modelName: model, tokenUsage: tokenUsage)
                    
                case .error(let message):
                    statusContent += "\n❌ 错误: \(message)\n"
                    updateAssistantMessage(content: statusContent, isStreaming: false)
                    errorMessage = message
                    
                case .stopped:
                    statusContent += "\n\n[已终止]"
                    updateAssistantMessage(content: statusContent, isStreaming: false)
                    
                default:
                    break
                }
                }
                break retryLoop
            } catch {
                if retryCount < 1 && isConnectionError(error) {
                    retryCount += 1
                    updateAssistantMessage(content: statusContent + "\n连接断开，正在重连...", isStreaming: true)
                    await backendService.reconnect()
                    if isConnected {
                        updateAssistantMessage(content: statusContent + "\n已重连，正在恢复任务...", isStreaming: true)
                        continue retryLoop
                    }
                }
                errorMessage = "任务恢复失败: \(error.localizedDescription)"
                updateAssistantMessage(
                    content: statusContent + "\n❌ 恢复失败: \(error.localizedDescription)",
                    isStreaming: false
                )
                break
            }
        }
        
        isLoading = false
    }
    
    // MARK: - Chat Resume (断线重连恢复 chat 流)
    
    private func resumeChatStream(sessionId: String) async {
        guard var conversation = currentConversation else { return }
        
        let resumeMessage = Message(role: .assistant, content: "正在恢复对话...", isStreaming: true)
        conversation.messages.append(resumeMessage)
        updateCurrentConversation(conversation)
        
        isLoading = true
        var fullContent = ""
        
        do {
            for try await chunk in backendService.resumeChat(sessionId: sessionId) {
                switch chunk {
                case .content(let text):
                    fullContent += text
                    updateAssistantMessage(content: fullContent, isStreaming: true)
                    
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
    
    // MARK: - UI
    
    func toggleToolPanel() {
        showToolPanel.toggle()
    }
}
