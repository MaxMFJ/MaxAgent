import Foundation

enum StreamChunk {
    case content(String)
    case toolCall(name: String, args: [String: Any])
    case toolResult(name: String, success: Bool, result: String)
    case executionLog(toolName: String, actionId: String, level: String, message: String)
    case done(model: String?, tokenUsage: TokenUsage?)
    case error(String)
    case stopped
    
    case imageData(base64: String, mimeType: String, path: String?)
    case localImage(path: String)
    
    // Chat resume
    case chatResumeResult(found: Bool, taskId: String?, status: String?, messageId: String?)
    
    // Autonomous mode chunks
    case taskStart(taskId: String, task: String)
    case modelSelected(modelType: String, reason: String, taskType: String, complexity: Int)
    case actionPlan(action: [String: Any], iteration: Int)
    case actionExecuting(actionId: String, actionType: String)
    case actionResult(actionId: String, success: Bool, output: String?, error: String?)
    case llmRequestStart(provider: String, model: String, iteration: Int)
    case llmRequestEnd(provider: String, model: String, iteration: Int, latencyMs: Int, usage: [String: Any], responsePreview: String?, error: String?)
    case reflectStart
    case reflectResult(reflection: String)
    case taskComplete(taskId: String, success: Bool, summary: String, totalActions: Int)
    /// 解析重试提示（非错误，任务继续）
    case retry(message: String)
    /// v3.4: Gather→Act→Verify 阶段验证结果
    case phaseVerify(iteration: Int, phase: String, note: String)
    /// v3.4: HITL 人工审批请求
    case hitlRequest(actionId: String, actionType: String, description: String, riskLevel: String)
}

@MainActor
class BackendService: ObservableObject {
    private var port: Int = Int(PortConfiguration.defaultBackendPort)
    // Stored so that nonisolated functions can read them safely.
    nonisolated(unsafe) private var baseURL: String = "http://127.0.0.1:\(PortConfiguration.defaultBackendPort)"
    nonisolated(unsafe) private var wsURL: String = "ws://127.0.0.1:\(PortConfiguration.defaultBackendPort)/ws"
    private var webSocketTask: URLSessionWebSocketTask?
    private var urlSession: URLSession
    private var pingTask: Task<Void, Never>?
    /// 空闲时持续收包，用于响应服务端 ping、处理 system_notification/tools_updated，断线时触发重连
    private var idleReceiveTask: Task<Void, Never>?
    @Published var isConnected: Bool = false
    
    // 断线重连状态追踪
    private var currentSessionId: String?
    /// 空闲收包循环连续失败次数，用于退避：3 次失败后休眠 10 分钟再试
    private var idleReceiveConsecutiveFailures: Int = 0
    private var hasRunningTask: Bool = false
    private var runningTaskId: String?
    private var hasRunningChat: Bool = false
    private var runningChatTaskId: String?
    
    var onSystemNotification: ((SystemNotification, Int) -> Void)?
    /// 收到服务端广播 tools_updated 时调用，各端据此刷新工具列表与待审批列表
    var onToolsUpdated: (() async -> Void)?
    /// 连接成功后检测到有运行中任务时回调
    var onTaskDetected: ((Bool, String?) -> Void)?
    /// 连接成功后检测到有运行中的 chat 流时回调
    var onChatResumeDetected: ((String) -> Void)?
    /// 收到全局监控事件（来自任意客户端的任务执行事件）时回调
    var onMonitorEvent: ((_ sourceSession: String, _ taskId: String, _ event: [String: Any]) -> Void)?
    /// 子 Duck 任务完成时回调（主 Agent 主动联系用户，将结果作为 assistant 消息展示）
    var onDuckTaskComplete: ((_ content: String, _ success: Bool, _ taskId: String, _ sessionId: String) -> Void)?
    /// 群聊创建时回调
    var onGroupChatCreated: ((_ group: GroupChat) -> Void)?
    /// 群聊消息回调
    var onGroupMessage: ((_ groupId: String, _ message: GroupMessage) -> Void)?
    /// 群聊状态更新回调
    var onGroupStatusUpdate: ((_ groupId: String, _ status: GroupChatStatus, _ taskSummary: GroupTaskSummary) -> Void)?

    init(port: Int = Int(PortConfiguration.defaultBackendPort)) {
        self.port = port
        self.baseURL = "http://127.0.0.1:\(port)"
        self.wsURL = "ws://127.0.0.1:\(port)/ws"
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 300
        config.timeoutIntervalForResource = 600
        self.urlSession = URLSession(configuration: config)
    }

    /// Update the port and reconnect (used when switching to duck mode at startup).
    func updatePort(_ newPort: Int) async {
        port = newPort
        baseURL = "http://127.0.0.1:\(newPort)"
        wsURL = "ws://127.0.0.1:\(newPort)/ws"
        await reconnect()
    }

    // MARK: - Connection

    func connect() async {
        disconnect()
        idleReceiveConsecutiveFailures = 0  // 主动连接时重置失败计数
        
        guard let url = URL(string: wsURL) else { return }
        
        webSocketTask = urlSession.webSocketTask(with: url)
        webSocketTask?.maximumMessageSize = 20 * 1024 * 1024  // 20MB，支持大截图传输
        webSocketTask?.resume()
        
        isConnected = true
        startPing()
        
        // 监听首个 connected 消息
        await listenForConnectedMessage()
        startIdleReceiveLoop()
    }
    
    private func listenForConnectedMessage() async {
        guard let webSocket = webSocketTask else { return }
        
        do {
            let result = try await webSocket.receive()
            
            switch result {
            case .string(let text):
                if let data = text.data(using: .utf8),
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let type = json["type"] as? String,
                   type == "connected" {
                    
                    currentSessionId = json["session_id"] as? String
                    hasRunningTask = json["has_running_task"] as? Bool ?? false
                    runningTaskId = json["running_task_id"] as? String
                    hasRunningChat = json["has_running_chat"] as? Bool ?? false
                    runningChatTaskId = json["running_chat_task_id"] as? String
                    let hasBufferedChat = json["has_buffered_chat"] as? Bool ?? false
                    
                    if hasRunningTask {
                        onTaskDetected?(hasRunningTask, runningTaskId)
                    }
                    // 只有在有运行中或有缓冲的 chat 时才触发恢复
                    if (hasRunningChat || hasBufferedChat), let sessionId = currentSessionId {
                        onChatResumeDetected?(sessionId)
                    }
                }
            default:
                break
            }
        } catch {
            print("Failed to receive connected message: \(error)")
        }
    }
    
    func disconnect() {
        cancelIdleReceiveLoop()
        pingTask?.cancel()
        pingTask = nil
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil
        isConnected = false
    }
    
    func reconnect() async {
        disconnect()
        try? await Task.sleep(nanoseconds: 500_000_000) // 0.5秒
        await connect()
    }
    
    private func startPing() {
        pingTask?.cancel()
        pingTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 10_000_000_000) // 10秒
                guard let self = self, let ws = self.webSocketTask else { break }
                
                ws.sendPing { [weak self] error in
                    if error != nil {
                        Task { @MainActor [weak self] in
                            self?.isConnected = false
                        }
                    }
                }
            }
        }
    }
    
    private func ensureConnected() async {
        if webSocketTask == nil || !isConnected {
            await connect()
        }
    }
    
    /// 取消空闲收包循环（在开始 stream 收包前调用，避免双 receive 竞争）
    private func cancelIdleReceiveLoop() {
        idleReceiveTask?.cancel()
        idleReceiveTask = nil
    }
    
    /// 启动空闲时收包循环：响应 server_ping、处理 system_notification/tools_updated，断线时触发重连
    private func startIdleReceiveLoop() {
        guard webSocketTask != nil, isConnected else {
            print("[BackendService] idleReceiveLoop not started: ws=\(webSocketTask != nil), connected=\(isConnected)")
            return
        }
        print("[BackendService] Starting idleReceiveLoop")
        cancelIdleReceiveLoop()
        idleReceiveTask = Task { [weak self] in
            guard let self = self else { return }
            while !Task.isCancelled {
                let (ws, connected): (URLSessionWebSocketTask?, Bool) = await MainActor.run {
                    (self.webSocketTask, self.isConnected)
                }
                guard let ws = ws, connected else { break }
                do {
                    let result = try await ws.receive()
                    await MainActor.run { self.idleReceiveConsecutiveFailures = 0 }  // 收包成功，重置失败计数
                    switch result {
                    case .string(let text):
                        if let data = text.data(using: .utf8),
                           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                           let type = json["type"] as? String {
                            switch type {
                            case "server_ping":
                                do {
                                    let pongMsg: [String: Any] = ["type": "pong"]
                                    let pongData = try JSONSerialization.data(withJSONObject: pongMsg)
                                    if let pongStr = String(data: pongData, encoding: .utf8) {
                                        try await ws.send(.string(pongStr))
                                    }
                                } catch {}
                            case "system_notification":
                                await MainActor.run { self.handleSystemNotification(json) }
                            case "tools_updated":
                                if let cb = await MainActor.run(body: { self.onToolsUpdated }) { await cb() }
                            case "monitor_event":
                                // 全局监控事件：来自任意客户端的任务执行事件
                                let sourceSession = json["source_session"] as? String ?? ""
                                let taskId = json["task_id"] as? String ?? ""
                                let event = json["event"] as? [String: Any] ?? [:]
                                let eventType = event["type"] as? String ?? "unknown"
                                print("[BackendService] Received monitor_event: type=\(eventType), taskId=\(taskId), session=\(sourceSession)")
                                await MainActor.run {
                                    self.onMonitorEvent?(sourceSession, taskId, event)
                                }
                            case "duck_task_complete":
                                // 子 Duck 任务完成，主 Agent 主动联系用户
                                let content = json["content"] as? String ?? ""
                                let success = json["success"] as? Bool ?? false
                                let taskId = json["task_id"] as? String ?? ""
                                let sessionId = json["session_id"] as? String ?? ""
                                await MainActor.run {
                                    self.onDuckTaskComplete?(content, success, taskId, sessionId)
                                }
                            case "duck_task_retry":
                                // Duck 任务自动重试通知（信息性）
                                let retryContent = json["content"] as? String ?? ""
                                let retryTaskId = json["task_id"] as? String ?? ""
                                let retrySessionId = json["session_id"] as? String ?? ""
                                await MainActor.run {
                                    self.onDuckTaskComplete?(retryContent, false, retryTaskId, retrySessionId)
                                }
                            case "group_chat_created":
                                if let groupData = try? JSONSerialization.data(withJSONObject: json["group"] ?? [:]),
                                   let group = try? JSONDecoder().decode(GroupChat.self, from: groupData) {
                                    await MainActor.run { self.onGroupChatCreated?(group) }
                                }
                            case "group_message":
                                let gid = json["group_id"] as? String ?? ""
                                if let msgData = try? JSONSerialization.data(withJSONObject: json["message"] ?? [:]),
                                   let msg = try? JSONDecoder().decode(GroupMessage.self, from: msgData) {
                                    await MainActor.run { self.onGroupMessage?(gid, msg) }
                                }
                            case "group_status_update":
                                let gid = json["group_id"] as? String ?? ""
                                let statusStr = json["status"] as? String ?? "active"
                                let gStatus = GroupChatStatus(rawValue: statusStr) ?? .active
                                if let summaryData = try? JSONSerialization.data(withJSONObject: json["task_summary"] ?? [:]),
                                   let summary = try? JSONDecoder().decode(GroupTaskSummary.self, from: summaryData) {
                                    await MainActor.run { self.onGroupStatusUpdate?(gid, gStatus, summary) }
                                }
                            case "client_disconnected":
                                break
                            default:
                                break
                            }
                        }
                    case .data:
                        break
                    @unknown default:
                        break
                    }
                } catch is CancellationError {
                    return
                } catch {
                    let shouldSleep10Min = await MainActor.run {
                        self.disconnect()
                        self.idleReceiveConsecutiveFailures += 1
                        let count = self.idleReceiveConsecutiveFailures
                        if count >= 3 {
                            self.idleReceiveConsecutiveFailures = 0
                        }
                        return count >= 3
                    }
                    if shouldSleep10Min {
                        try? await Task.sleep(nanoseconds: 600_000_000_000)  // 3 次失败后休眠 10 分钟
                    } else {
                        try? await Task.sleep(nanoseconds: 2_000_000_000)  // 2 秒后重试
                    }
                    Task { @MainActor in await self.reconnect() }
                    return
                }
            }
        }
    }
    
    // MARK: - Configuration
    
    nonisolated func updateSmtpConfig(smtpServer: String, smtpPort: Int, smtpUser: String, smtpPassword: String?) async throws {
        guard let url = URL(string: "\(baseURL)/config/smtp") else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var body: [String: Any] = [
            "smtp_server": smtpServer,
            "smtp_port": smtpPort,
            "smtp_user": smtpUser
        ]
        if let pwd = smtpPassword, !pwd.isEmpty {
            body["smtp_password"] = pwd
        }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
    }
    
    nonisolated func fetchSmtpConfig() async throws -> SmtpConfig {
        guard let url = URL(string: "\(baseURL)/config/smtp") else {
            throw URLError(.badURL)
        }
        let (data, _) = try await urlSession.data(from: url)
        return try JSONDecoder().decode(SmtpConfig.self, from: data)
    }
    
    nonisolated func fetchGitHubConfig() async throws -> GithubConfig {
        guard let url = URL(string: "\(baseURL)/config/github") else {
            throw URLError(.badURL)
        }
        let (data, _) = try await urlSession.data(from: url)
        return try JSONDecoder().decode(GithubConfig.self, from: data)
    }
    
    nonisolated func updateGitHubConfig(githubToken: String?) async throws {
        guard let url = URL(string: "\(baseURL)/config/github") else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = ["github_token": githubToken ?? ""]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
    }

    // MARK: - 多自定义模型提供商

    nonisolated func fetchCustomProviders() async throws -> [CustomProviderModel] {
        guard let url = URL(string: "\(baseURL)/config/custom-providers") else {
            throw URLError(.badURL)
        }
        let (data, _) = try await urlSession.data(from: url)
        let resp = try JSONDecoder().decode(CustomProvidersResponse.self, from: data)
        return resp.providers
    }

    /// 新建或更新一个自定义提供商；id 为空时后端自动生成
    nonisolated func upsertCustomProvider(id: String?, name: String, apiKey: String, baseUrl: String, model: String) async throws -> CustomProviderModel {
        guard let url = URL(string: "\(baseURL)/config/custom-providers") else {
            throw URLError(.badURL)
        }
        var body: [String: Any] = [
            "name": name,
            "api_key": apiKey,
            "base_url": baseUrl,
            "model": model,
        ]
        if let pid = id, !pid.isEmpty { body["id"] = pid }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, _) = try await urlSession.data(for: request)
        return try JSONDecoder().decode(CustomProviderModel.self, from: data)
    }

    nonisolated func deleteCustomProvider(id: String) async throws {
        guard let encodedId = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
              let url = URL(string: "\(baseURL)/config/custom-providers/\(encodedId)") else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
    }

    
    nonisolated func fetchPendingTools() async throws -> [PendingTool] {
        guard let url = URL(string: "\(baseURL)/tools/pending") else {
            throw URLError(.badURL)
        }
        let (data, _) = try await urlSession.data(from: url)
        let resp = try JSONDecoder().decode(PendingToolsResponse.self, from: data)
        return resp.pending
    }
    
    nonisolated func approveTool(toolName: String) async throws {
        guard let url = URL(string: "\(baseURL)/tools/approve") else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = ["tool_name": toolName]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }
    
    nonisolated func reloadTools() async throws {
        guard let url = URL(string: "\(baseURL)/tools/reload") else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
    }
    
    nonisolated func updateConfig(provider: String, apiKey: String, baseUrl: String, model: String, remoteFallbackProvider: String = "") async throws {
        guard let url = URL(string: "\(baseURL)/config") else {
            throw URLError(.badURL)
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        var body: [String: Any] = [
            "provider": provider,
            "api_key": apiKey,
            "base_url": baseUrl,
            "model": model
        ]
        body["remote_fallback_provider"] = remoteFallbackProvider
        
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        
        let (_, response) = try await urlSession.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
    }
    
    nonisolated func fetchConfig() async throws -> BackendConfig {
        guard let url = URL(string: "\(baseURL)/config") else {
            throw URLError(.badURL)
        }
        
        let (data, _) = try await urlSession.data(from: url)
        return try JSONDecoder().decode(BackendConfig.self, from: data)
    }

    /// 仅更新 LangChain 兼容开关（持久化到后端，无需重启）
    nonisolated func updateLangChainCompat(enabled: Bool) async throws {
        guard let url = URL(string: "\(baseURL)/config") else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["langchain_compat": enabled])
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
    }

    /// 尝试在后端安装 LangChain 可选依赖；失败时返回 (false, 提示文案)
    nonisolated func installLangChainDependencies() async -> (success: Bool, message: String) {
        guard let url = URL(string: "\(baseURL)/config/install-langchain") else {
            return (false, "无效的后端地址")
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 130
        do {
            let (data, response) = try await urlSession.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
                return (false, "请求失败，请确认后端已启动")
            }
            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let success = json["success"] as? Bool else {
                return (false, "无法解析安装结果")
            }
            let message = (json["message"] as? String) ?? ""
            if success {
                return (true, message)
            }
            let manualHint = "请在后端目录自行执行: pip install -r requirements-langchain.txt"
            return (false, message.isEmpty ? manualHint : "\(message)\n\n\(manualHint)")
        } catch {
            return (false, "安装请求失败: \(error.localizedDescription)。请在后端目录自行执行: pip install -r requirements-langchain.txt")
        }
    }

    // MARK: - Tools
    
    nonisolated func fetchTools() async throws -> [ToolDefinition] {
        guard let url = URL(string: "\(baseURL)/tools") else {
            throw URLError(.badURL)
        }
        
        let (data, _) = try await urlSession.data(from: url)
        
        struct ToolsResponse: Codable {
            let tools: [ToolDefinition]
        }
        
        let response = try JSONDecoder().decode(ToolsResponse.self, from: data)
        return response.tools
    }
    
    // MARK: - System Messages
    
    nonisolated func fetchSystemMessages(limit: Int = 50, category: String? = nil) async throws -> ([SystemNotification], Int) {
        var path = "\(baseURL)/system-messages?limit=\(limit)"
        if let category = category, !category.isEmpty {
            path += "&category=\(category.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? category)"
        }
        guard let url = URL(string: path) else {
            throw URLError(.badURL)
        }
        let (data, _) = try await urlSession.data(from: url)
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let messagesArray = json["messages"] as? [[String: Any]],
              let unreadCount = json["unread_count"] as? Int else {
            throw URLError(.cannotParseResponse)
        }
        let jsonData = try JSONSerialization.data(withJSONObject: messagesArray)
        let notifications = try JSONDecoder().decode([SystemNotification].self, from: jsonData)
        return (notifications, unreadCount)
    }
    
    nonisolated func markSystemMessageRead(_ messageId: String) async throws -> Int {
        guard let url = URL(string: "\(baseURL)/system-messages/\(messageId)/read") else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let (data, _) = try await urlSession.data(for: request)
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let unreadCount = json["unread_count"] as? Int else {
            return 0
        }
        return unreadCount
    }
    
    nonisolated func markAllSystemMessagesRead() async throws {
        guard let url = URL(string: "\(baseURL)/system-messages/read-all") else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
    }
    
    nonisolated func clearSystemMessages() async throws {
        guard let url = URL(string: "\(baseURL)/system-messages") else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
    }

    /// 清理缓存：清除 traces、任务检查点、chat 会话数据等，保留配置文件
    nonisolated func clearCache() async throws -> (deleted: Int, message: String) {
        guard let url = URL(string: "\(baseURL)/cache/clear") else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        struct ClearResponse: Codable {
            let ok: Bool
            let deleted: Int
            let message: String
        }
        let result = try JSONDecoder().decode(ClearResponse.self, from: data)
        return (result.deleted, result.message)
    }
    
    private func handleSystemNotification(_ json: [String: Any]) {
        guard let notifDict = json["notification"] as? [String: Any],
              let notifData = try? JSONSerialization.data(withJSONObject: notifDict),
              let notification = try? JSONDecoder().decode(SystemNotification.self, from: notifData) else {
            return
        }
        let unreadCount = json["unread_count"] as? Int ?? 0
        onSystemNotification?(notification, unreadCount)
    }
    
    // MARK: - Messaging
    
    nonisolated func sendMessage(_ content: String) async throws -> String {
        guard let url = URL(string: "\(baseURL)/chat") else {
            throw URLError(.badURL)
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 300
        
        let body = ["content": content]
        request.httpBody = try JSONEncoder().encode(body)
        
        let (data, _) = try await urlSession.data(for: request)
        
        struct ChatResponse: Codable {
            let response: String
        }
        
        let response = try JSONDecoder().decode(ChatResponse.self, from: data)
        return response.response
    }
    
    func sendMessageStream(_ content: String, sessionId: String? = nil, filePaths: [String] = []) -> AsyncThrowingStream<StreamChunk, Error> {
        return AsyncThrowingStream { [weak self] continuation in
            Task { [weak self] in
                guard let self = self else {
                    continuation.finish(throwing: URLError(.cancelled))
                    return
                }
                cancelIdleReceiveLoop()
                do {
                    // 确保连接
                    await self.ensureConnected()
                    
                    guard let webSocket = self.webSocketTask else {
                        continuation.finish(throwing: URLError(.cannotConnectToHost))
                        return
                    }
                    
                    // 发送消息，包含 session_id 和可选的 file_paths
                    var message: [String: Any] = [
                        "type": "chat",
                        "content": content
                    ]
                    if let sessionId = sessionId {
                        message["session_id"] = sessionId
                    }
                    if !filePaths.isEmpty {
                        message["file_paths"] = filePaths
                    }
                    
                    let jsonData = try JSONSerialization.data(withJSONObject: message)
                    let jsonString = String(data: jsonData, encoding: .utf8)!
                    
                    try await webSocket.send(.string(jsonString))
                    
                    // 接收响应
                    while true {
                        let result = try await webSocket.receive()
                        
                        switch result {
                        case .string(let text):
                            if let data = text.data(using: .utf8),
                               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                                
                                let type = json["type"] as? String ?? ""
                                
                                switch type {
                                case "content":
                                    if let content = json["content"] as? String {
                                        continuation.yield(.content(content))
                                    }
                                    
                                case "upgrade_complete":
                                    let plan = json["plan"] as? String ?? ""
                                    let loaded = json["loaded_tools"] as? [String] ?? []
                                    let summary = loaded.isEmpty
                                        ? "✅ 升级已完成。\(plan.isEmpty ? "" : plan)"
                                        : "✅ 升级已完成，已加载工具: \(loaded.joined(separator: ", "))"
                                    continuation.yield(.content(summary))
                                    
                                case "upgrade_error":
                                    let err = json["error"] as? String ?? "未知错误"
                                    continuation.yield(.content("❌ 升级失败: \(err)"))
                                    
                                case "tool_call":
                                    if let name = json["tool_name"] as? String,
                                       let args = json["tool_args"] as? [String: Any] {
                                        continuation.yield(.toolCall(name: name, args: args))
                                    }
                                    
                                case "tool_result":
                                    if let name = json["tool_name"] as? String,
                                       let success = json["success"] as? Bool,
                                       let resultStr = json["result"] as? String {
                                        continuation.yield(.toolResult(name: name, success: success, result: resultStr))
                                        // 注意：图片数据由后端单独发送的 "image" 消息处理，
                                        // 不再从 tool_result 的 result 字符串中提取，避免解析占位符导致"解析失败"
                                    }
                                    
                                case "image":
                                    if let base64 = json["base64"] as? String {
                                        let mimeType = json["mime_type"] as? String ?? "image/png"
                                        let path = json["path"] as? String
                                        continuation.yield(.imageData(base64: base64, mimeType: mimeType, path: path))
                                    } else if let path = json["path"] as? String {
                                        continuation.yield(.localImage(path: path))
                                    }
                                    
                                case "tool_executing":
                                    continue

                                case "llm_request_start":
                                    let provider = json["provider"] as? String ?? "unknown"
                                    let model = json["model"] as? String ?? ""
                                    let iteration = json["iteration"] as? Int ?? 0
                                    continuation.yield(.llmRequestStart(provider: provider, model: model, iteration: iteration))

                                case "llm_request_end":
                                    let provider = json["provider"] as? String ?? "unknown"
                                    let model = json["model"] as? String ?? ""
                                    let iteration = json["iteration"] as? Int ?? 0
                                    let latencyMs = json["latency_ms"] as? Int ?? 0
                                    let usage = json["usage"] as? [String: Any] ?? [:]
                                    let responsePreview = json["response_preview"] as? String
                                    let error = json["error"] as? String
                                    continuation.yield(.llmRequestEnd(provider: provider, model: model, iteration: iteration, latencyMs: latencyMs, usage: usage, responsePreview: responsePreview, error: error))
                                    
                                case "execution_log":
                                    if let toolName = json["tool_name"] as? String,
                                       let level = json["level"] as? String,
                                       let message = json["message"] as? String {
                                        let actionId = json["action_id"] as? String ?? ""
                                        continuation.yield(.executionLog(toolName: toolName, actionId: actionId, level: level, message: message))
                                    }
                                    
                                case "done":
                                    let modelName = json["model"] as? String
                                    var tokenUsage: TokenUsage? = nil
                                    if let usage = json["usage"] as? [String: Any] {
                                        tokenUsage = TokenUsage(
                                            promptTokens: usage["prompt_tokens"] as? Int ?? 0,
                                            completionTokens: usage["completion_tokens"] as? Int ?? 0,
                                            totalTokens: usage["total_tokens"] as? Int ?? 0
                                        )
                                    }
                                    continuation.yield(.done(model: modelName, tokenUsage: tokenUsage))
                                    startIdleReceiveLoop()
                                    continuation.finish()
                                    return
                                    
                                case "stopped":
                                    continuation.yield(.stopped)
                                    startIdleReceiveLoop()
                                    continuation.finish()
                                    return
                                    
                                case "error":
                                    let errorMsg = json["message"] as? String ?? json["error"] as? String ?? "Unknown error"
                                    continuation.yield(.error(errorMsg))
                                    startIdleReceiveLoop()
                                    continuation.finish()
                                    return
                                    
                                case "pong":
                                    continue
                                
                                case "server_ping":
                                    // 服务端心跳，回复 pong
                                    if let ws = self.webSocketTask {
                                        Task {
                                            do {
                                                let pongMsg: [String: Any] = ["type": "pong"]
                                                let pongData = try JSONSerialization.data(withJSONObject: pongMsg)
                                                if let pongStr = String(data: pongData, encoding: .utf8) {
                                                    try await ws.send(.string(pongStr))
                                                }
                                            } catch {}
                                        }
                                    }
                                    continue

                                case "duck_task_complete":
                                    let contentDtc = json["content"] as? String ?? ""
                                    let successDtc = json["success"] as? Bool ?? false
                                    let taskIdDtc = json["task_id"] as? String ?? ""
                                    let sessionIdDtc = json["session_id"] as? String ?? ""
                                    await MainActor.run { self.onDuckTaskComplete?(contentDtc, successDtc, taskIdDtc, sessionIdDtc) }
                                    continue
                                case "duck_task_retry":
                                    let retryContentDtc = json["content"] as? String ?? ""
                                    let retryTaskIdDtc = json["task_id"] as? String ?? ""
                                    let retrySessionIdDtc = json["session_id"] as? String ?? ""
                                    await MainActor.run { self.onDuckTaskComplete?(retryContentDtc, false, retryTaskIdDtc, retrySessionIdDtc) }
                                    continue

                                case "group_chat_created":
                                    if let groupData = try? JSONSerialization.data(withJSONObject: json["group"] ?? [:]),
                                       let group = try? JSONDecoder().decode(GroupChat.self, from: groupData) {
                                        await MainActor.run { self.onGroupChatCreated?(group) }
                                    }
                                    continue
                                case "group_message":
                                    let gidDtc = json["group_id"] as? String ?? ""
                                    if let msgData = try? JSONSerialization.data(withJSONObject: json["message"] ?? [:]),
                                       let msg = try? JSONDecoder().decode(GroupMessage.self, from: msgData) {
                                        await MainActor.run { self.onGroupMessage?(gidDtc, msg) }
                                    }
                                    continue
                                case "group_status_update":
                                    let gidDtc = json["group_id"] as? String ?? ""
                                    let statusStrDtc = json["status"] as? String ?? "active"
                                    let gStatusDtc = GroupChatStatus(rawValue: statusStrDtc) ?? .active
                                    if let summaryData = try? JSONSerialization.data(withJSONObject: json["task_summary"] ?? [:]),
                                       let summary = try? JSONDecoder().decode(GroupTaskSummary.self, from: summaryData) {
                                        await MainActor.run { self.onGroupStatusUpdate?(gidDtc, gStatusDtc, summary) }
                                    }
                                    continue
                                
                                case "system_notification":
                                    await MainActor.run { [weak self] in
                                        self?.handleSystemNotification(json)
                                    }
                                    continue
                                
                                case "tools_updated":
                                    if let cb = self.onToolsUpdated {
                                        await cb()
                                    }
                                    continue

                                case "monitor_event":
                                    let sourceSession = json["source_session"] as? String ?? ""
                                    let taskId = json["task_id"] as? String ?? ""
                                    let event = json["event"] as? [String: Any] ?? [:]
                                    await MainActor.run {
                                        self.onMonitorEvent?(sourceSession, taskId, event)
                                    }
                                    continue
                                    
                                default:
                                    continue
                                }
                            }
                            
                        case .data:
                            continue
                            
                        @unknown default:
                            continue
                        }
                    }
                    
                } catch {
                    disconnect()
                    startIdleReceiveLoop()
                    continuation.finish(throwing: error)
                }
            }
        }
    }
    
    // MARK: - Stop Stream
    
    func sendStopStream(sessionId: String? = nil) async {
        guard let webSocket = webSocketTask else { return }
        
        var message: [String: Any] = ["type": "stop"]
        if let sessionId = sessionId {
            message["session_id"] = sessionId
        }
        
        do {
            let jsonData = try JSONSerialization.data(withJSONObject: message)
            let jsonString = String(data: jsonData, encoding: .utf8)!
            try await webSocket.send(.string(jsonString))
        } catch {
            print("Failed to send stop: \(error)")
        }
    }
    
    // MARK: - Session Management
    
    /// 同步本地会话 ID 到后端（断线重连时，后端默认 session 为 "default"，需要切换到本地实际会话 ID）
    func syncSessionId(_ sessionId: String) async {
        guard let webSocket = webSocketTask else { return }
        
        let message: [String: Any] = [
            "type": "new_session",
            "session_id": sessionId
        ]
        
        do {
            let jsonData = try JSONSerialization.data(withJSONObject: message)
            let jsonString = String(data: jsonData, encoding: .utf8)!
            try await webSocket.send(.string(jsonString))
            print("[BackendService] Synced session ID: \(sessionId)")
        } catch {
            print("Failed to sync session: \(error)")
        }
    }
    
    func clearSession(_ sessionId: String) async {
        guard let webSocket = webSocketTask else { return }
        
        let message: [String: Any] = [
            "type": "clear_session",
            "session_id": sessionId
        ]
        
        do {
            let jsonData = try JSONSerialization.data(withJSONObject: message)
            let jsonString = String(data: jsonData, encoding: .utf8)!
            try await webSocket.send(.string(jsonString))
        } catch {
            print("Failed to clear session: \(error)")
        }
    }
    
    // MARK: - Task Resume (断线重连恢复)
    
    func resumeTask(sessionId: String) -> AsyncThrowingStream<StreamChunk, Error> {
        return AsyncThrowingStream { [weak self] continuation in
            Task { [weak self] in
                guard let self = self else {
                    continuation.finish(throwing: URLError(.cancelled))
                    return
                }
                cancelIdleReceiveLoop()
                do {
                    await self.ensureConnected()
                    
                    guard let webSocket = self.webSocketTask else {
                        continuation.finish(throwing: URLError(.cannotConnectToHost))
                        return
                    }
                    
                    let message: [String: Any] = [
                        "type": "resume_task",
                        "session_id": sessionId
                    ]
                    
                    let jsonData = try JSONSerialization.data(withJSONObject: message)
                    let jsonString = String(data: jsonData, encoding: .utf8)!
                    try await webSocket.send(.string(jsonString))
                    
                    // 接收恢复的消息流
                    while true {
                        let response = try await webSocket.receive()
                        
                        switch response {
                        case .string(let text):
                            if let data = text.data(using: .utf8),
                               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                               let type = json["type"] as? String {
                                
                                switch type {
                                case "resume_result":
                                    let found = json["found"] as? Bool ?? false
                                    if !found {
                                        let message = json["message"] as? String ?? "未找到任务"
                                        continuation.yield(.error(message))
                                        startIdleReceiveLoop()
                                        continuation.finish()
                                        return
                                    }
                                    // 继续接收后续 chunks
                                    continue
                                    
                                case "resume_streaming":
                                    // 历史回放完成，后续是实时流
                                    continue
                                    
                                // 处理所有 autonomous task 相关的 chunk 类型
                                case "task_start":
                                    let taskId = json["task_id"] as? String ?? ""
                                    let taskDesc = json["task"] as? String ?? ""
                                    continuation.yield(.taskStart(taskId: taskId, task: taskDesc))
                                    
                                case "model_selected":
                                    let modelType = json["model_type"] as? String ?? "unknown"
                                    let reason = json["reason"] as? String ?? ""
                                    let taskType = json["task_type"] as? String ?? ""
                                    let complexity = json["complexity"] as? Int ?? 0
                                    continuation.yield(.modelSelected(modelType: modelType, reason: reason, taskType: taskType, complexity: complexity))
                                    
                                case "action_plan":
                                    let action = json["action"] as? [String: Any] ?? [:]
                                    let iteration = json["iteration"] as? Int ?? 0
                                    continuation.yield(.actionPlan(action: action, iteration: iteration))
                                    
                                case "action_executing":
                                    let actionId = json["action_id"] as? String ?? ""
                                    let actionType = json["action_type"] as? String ?? ""
                                    continuation.yield(.actionExecuting(actionId: actionId, actionType: actionType))
                                    
                                case "action_result":
                                    let actionId = json["action_id"] as? String ?? ""
                                    let success = json["success"] as? Bool ?? false
                                    let output = json["output"] as? String
                                    let error = json["error"] as? String
                                    continuation.yield(.actionResult(actionId: actionId, success: success, output: output, error: error))
                                    // 兼容旧协议：action_result 内嵌 image_base64 时直接展示；新协议由 screenshot chunk 单独推送
                                    if success, let path = json["screenshot_path"] as? String, !path.isEmpty,
                                       let base64 = json["image_base64"] as? String, !base64.isEmpty {
                                        let mime = json["mime_type"] as? String ?? "image/png"
                                        continuation.yield(.imageData(base64: base64, mimeType: mime, path: path))
                                    }

                                case "llm_request_start":
                                    let provider = json["provider"] as? String ?? "unknown"
                                    let model = json["model"] as? String ?? ""
                                    let iteration = json["iteration"] as? Int ?? 0
                                    continuation.yield(.llmRequestStart(provider: provider, model: model, iteration: iteration))

                                case "llm_request_end":
                                    let provider = json["provider"] as? String ?? "unknown"
                                    let model = json["model"] as? String ?? ""
                                    let iteration = json["iteration"] as? Int ?? 0
                                    let latencyMs = json["latency_ms"] as? Int ?? 0
                                    let usage = json["usage"] as? [String: Any] ?? [:]
                                    let responsePreview = json["response_preview"] as? String
                                    let error = json["error"] as? String
                                    continuation.yield(.llmRequestEnd(provider: provider, model: model, iteration: iteration, latencyMs: latencyMs, usage: usage, responsePreview: responsePreview, error: error))
                                
                                case "screenshot":
                                    // 后端单独推送的截图 chunk，避免大 payload 导致 WebSocket 失败
                                    if let path = json["screenshot_path"] as? String, !path.isEmpty,
                                       let base64 = json["image_base64"] as? String, !base64.isEmpty {
                                        let mime = json["mime_type"] as? String ?? "image/png"
                                        continuation.yield(.imageData(base64: base64, mimeType: mime, path: path))
                                    }
                                    
                                case "reflect_start":
                                    continuation.yield(.reflectStart)
                                    
                                case "reflect_result":
                                    let reflection = json["reflection"] as? String ?? ""
                                    continuation.yield(.reflectResult(reflection: reflection))
                                    
                                case "task_complete":
                                    let taskId = json["task_id"] as? String ?? ""
                                    let success = json["success"] as? Bool ?? false
                                    let summary = json["summary"] as? String ?? ""
                                    let totalActions = json["total_actions"] as? Int ?? 0
                                    continuation.yield(.taskComplete(taskId: taskId, success: success, summary: summary, totalActions: totalActions))

                                case "task_stopped":
                                    let taskIdStopped = json["task_id"] as? String ?? ""
                                    let msg = json["message"] as? String ?? json["reason"] as? String ?? "任务已停止"
                                    let rec = json["recommendation"] as? String ?? ""
                                    let summaryStopped = rec.isEmpty ? msg : "\(msg)\n\n建议: \(rec)"
                                    let totalStopped = json["iterations"] as? Int ?? 0
                                    continuation.yield(.taskComplete(taskId: taskIdStopped, success: false, summary: summaryStopped, totalActions: totalStopped))

                                case "content":
                                    if let content = json["content"] as? String {
                                        continuation.yield(.content(content))
                                    }
                                    
                                case "done":
                                    let modelName = json["model"] as? String
                                    var tokenUsageResume: TokenUsage? = nil
                                    if let usage = json["usage"] as? [String: Any] {
                                        tokenUsageResume = TokenUsage(
                                            promptTokens: usage["prompt_tokens"] as? Int ?? 0,
                                            completionTokens: usage["completion_tokens"] as? Int ?? 0,
                                            totalTokens: usage["total_tokens"] as? Int ?? 0
                                        )
                                    }
                                    continuation.yield(.done(model: modelName, tokenUsage: tokenUsageResume))
                                    startIdleReceiveLoop()
                                    continuation.finish()
                                    return
                                    
                                case "error":
                                    let errorMsg = json["message"] as? String ?? json["error"] as? String ?? "Unknown error"
                                    continuation.yield(.error(errorMsg))
                                    startIdleReceiveLoop()
                                    continuation.finish()
                                    return
                                    
                                case "stopped":
                                    continuation.yield(.stopped)
                                    startIdleReceiveLoop()
                                    continuation.finish()
                                    return

                                case "monitor_event":
                                    let sourceSessionResume = json["source_session"] as? String ?? ""
                                    let taskIdResume = json["task_id"] as? String ?? ""
                                    let eventResume = json["event"] as? [String: Any] ?? [:]
                                    await MainActor.run {
                                        self.onMonitorEvent?(sourceSessionResume, taskIdResume, eventResume)
                                    }
                                    continue
                                    
                                default:
                                    continue
                                }
                            }
                            
                        case .data:
                            continue
                            
                        @unknown default:
                            continue
                        }
                    }
                    
                } catch {
                    disconnect()
                    startIdleReceiveLoop()
                    continuation.finish(throwing: error)
                }
            }
        }
    }
    
    // MARK: - Chat Resume (断线重连恢复 chat 流)
    
    func resumeChat(sessionId: String) -> AsyncThrowingStream<StreamChunk, Error> {
        return AsyncThrowingStream { [weak self] continuation in
            Task { [weak self] in
                guard let self = self else {
                    continuation.finish(throwing: URLError(.cancelled))
                    return
                }
                cancelIdleReceiveLoop()
                do {
                    await self.ensureConnected()
                    
                    guard let webSocket = self.webSocketTask else {
                        continuation.finish(throwing: URLError(.cannotConnectToHost))
                        return
                    }
                    
                    let message: [String: Any] = [
                        "type": "resume_chat",
                        "session_id": sessionId
                    ]
                    
                    let jsonData = try JSONSerialization.data(withJSONObject: message)
                    let jsonString = String(data: jsonData, encoding: .utf8)!
                    try await webSocket.send(.string(jsonString))
                    
                    while true {
                        let response = try await webSocket.receive()
                        
                        switch response {
                        case .string(let text):
                            if let data = text.data(using: .utf8),
                               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                               let type = json["type"] as? String {
                                
                                switch type {
                                case "resume_chat_result":
                                    let found = json["found"] as? Bool ?? false
                                    let taskId = json["task_id"] as? String
                                    let status = json["status"] as? String
                                    let messageId = json["last_message_id"] as? String
                                    
                                    // 发送 resume 结果，让 ViewModel 可以进行去重判断
                                    continuation.yield(.chatResumeResult(found: found, taskId: taskId, status: status, messageId: messageId))
                                    
                                    if !found {
                                        startIdleReceiveLoop()
                                        continuation.finish()
                                        return
                                    }
                                    continue
                                    
                                case "resume_chat_streaming":
                                    continue
                                    
                                case "content":
                                    if let content = json["content"] as? String {
                                        continuation.yield(.content(content))
                                    }
                                    
                                case "tool_call":
                                    if let name = json["tool_name"] as? String,
                                       let args = json["tool_args"] as? [String: Any] {
                                        continuation.yield(.toolCall(name: name, args: args))
                                    }
                                    
                                case "tool_result":
                                    if let name = json["tool_name"] as? String,
                                       let success = json["success"] as? Bool,
                                       let resultStr = json["result"] as? String {
                                        continuation.yield(.toolResult(name: name, success: success, result: resultStr))
                                    }
                                    
                                case "llm_request_start":
                                    let provider = json["provider"] as? String ?? "unknown"
                                    let model = json["model"] as? String ?? ""
                                    let iteration = json["iteration"] as? Int ?? 0
                                    continuation.yield(.llmRequestStart(provider: provider, model: model, iteration: iteration))

                                case "llm_request_end":
                                    let provider = json["provider"] as? String ?? "unknown"
                                    let model = json["model"] as? String ?? ""
                                    let iteration = json["iteration"] as? Int ?? 0
                                    let latencyMs = json["latency_ms"] as? Int ?? 0
                                    let usage = json["usage"] as? [String: Any] ?? [:]
                                    let responsePreview = json["response_preview"] as? String
                                    let error = json["error"] as? String
                                    continuation.yield(.llmRequestEnd(provider: provider, model: model, iteration: iteration, latencyMs: latencyMs, usage: usage, responsePreview: responsePreview, error: error))

                                case "execution_log":
                                    if let toolName = json["tool_name"] as? String,
                                       let level = json["level"] as? String,
                                       let logMessage = json["message"] as? String {
                                        let actionId = json["action_id"] as? String ?? ""
                                        continuation.yield(.executionLog(toolName: toolName, actionId: actionId, level: level, message: logMessage))
                                    }
                                    
                                case "image":
                                    if let base64 = json["base64"] as? String {
                                        let mimeType = json["mime_type"] as? String ?? "image/png"
                                        let path = json["path"] as? String
                                        continuation.yield(.imageData(base64: base64, mimeType: mimeType, path: path))
                                    } else if let path = json["path"] as? String {
                                        continuation.yield(.localImage(path: path))
                                    }
                                    
                                case "done":
                                    let modelName = json["model"] as? String
                                    var tokenUsageResume: TokenUsage? = nil
                                    if let usage = json["usage"] as? [String: Any] {
                                        tokenUsageResume = TokenUsage(
                                            promptTokens: usage["prompt_tokens"] as? Int ?? 0,
                                            completionTokens: usage["completion_tokens"] as? Int ?? 0,
                                            totalTokens: usage["total_tokens"] as? Int ?? 0
                                        )
                                    }
                                    continuation.yield(.done(model: modelName, tokenUsage: tokenUsageResume))
                                    startIdleReceiveLoop()
                                    continuation.finish()
                                    return
                                    
                                case "error":
                                    let errorMsg = json["message"] as? String ?? json["error"] as? String ?? "Unknown error"
                                    continuation.yield(.error(errorMsg))
                                    startIdleReceiveLoop()
                                    continuation.finish()
                                    return
                                    
                                case "stopped":
                                    continuation.yield(.stopped)
                                    startIdleReceiveLoop()
                                    continuation.finish()
                                    return
                                    
                                case "server_ping":
                                    if let ws = self.webSocketTask {
                                        Task {
                                            do {
                                                let pongMsg: [String: Any] = ["type": "pong"]
                                                let pongData = try JSONSerialization.data(withJSONObject: pongMsg)
                                                if let pongStr = String(data: pongData, encoding: .utf8) {
                                                    try await ws.send(.string(pongStr))
                                                }
                                            } catch {}
                                        }
                                    }
                                    continue

                                case "duck_task_complete":
                                    let contentDtc2 = json["content"] as? String ?? ""
                                    let successDtc2 = json["success"] as? Bool ?? false
                                    let taskIdDtc2 = json["task_id"] as? String ?? ""
                                    let sessionIdDtc2 = json["session_id"] as? String ?? ""
                                    await MainActor.run { self.onDuckTaskComplete?(contentDtc2, successDtc2, taskIdDtc2, sessionIdDtc2) }
                                    continue
                                case "duck_task_retry":
                                    let retryContentDtc2 = json["content"] as? String ?? ""
                                    let retryTaskIdDtc2 = json["task_id"] as? String ?? ""
                                    let retrySessionIdDtc2 = json["session_id"] as? String ?? ""
                                    await MainActor.run { self.onDuckTaskComplete?(retryContentDtc2, false, retryTaskIdDtc2, retrySessionIdDtc2) }
                                    continue

                                case "group_chat_created":
                                    if let groupData = try? JSONSerialization.data(withJSONObject: json["group"] ?? [:]),
                                       let group = try? JSONDecoder().decode(GroupChat.self, from: groupData) {
                                        await MainActor.run { self.onGroupChatCreated?(group) }
                                    }
                                    continue
                                case "group_message":
                                    let gidDtc2 = json["group_id"] as? String ?? ""
                                    if let msgData = try? JSONSerialization.data(withJSONObject: json["message"] ?? [:]),
                                       let msg = try? JSONDecoder().decode(GroupMessage.self, from: msgData) {
                                        await MainActor.run { self.onGroupMessage?(gidDtc2, msg) }
                                    }
                                    continue
                                case "group_status_update":
                                    let gidDtc2 = json["group_id"] as? String ?? ""
                                    let statusStrDtc2 = json["status"] as? String ?? "active"
                                    let gStatusDtc2 = GroupChatStatus(rawValue: statusStrDtc2) ?? .active
                                    if let summaryData = try? JSONSerialization.data(withJSONObject: json["task_summary"] ?? [:]),
                                       let summary = try? JSONDecoder().decode(GroupTaskSummary.self, from: summaryData) {
                                        await MainActor.run { self.onGroupStatusUpdate?(gidDtc2, gStatusDtc2, summary) }
                                    }
                                    continue

                                case "monitor_event":
                                    let sourceSessionChat = json["source_session"] as? String ?? ""
                                    let taskIdChat = json["task_id"] as? String ?? ""
                                    let eventChat = json["event"] as? [String: Any] ?? [:]
                                    await MainActor.run {
                                        self.onMonitorEvent?(sourceSessionChat, taskIdChat, eventChat)
                                    }
                                    continue
                                    
                                default:
                                    continue
                                }
                            }
                            
                        case .data:
                            continue
                            
                        @unknown default:
                            continue
                        }
                    }
                    
                } catch {
                    disconnect()
                    startIdleReceiveLoop()
                    continuation.finish(throwing: error)
                }
            }
        }
    }
    
    // MARK: - Autonomous Execution (DEPRECATED — now routes through chat)
    
    @available(*, deprecated, message: "Use sendMessageStream instead. Autonomous mode merged into chat.")
    func sendAutonomousTask(_ task: String, sessionId: String? = nil, enableModelSelection: Bool = true, preferLocal: Bool = false, preferredTier: String? = nil, filePaths: [String] = []) -> AsyncThrowingStream<StreamChunk, Error> {
        return sendMessageStream(task, sessionId: sessionId, filePaths: filePaths)
    }

    // MARK: - MCP (Model Context Protocol)

    nonisolated func fetchMCPServers() async throws -> [[String: Any]] {
        guard let url = URL(string: "\(baseURL)/mcp/servers") else { throw URLError(.badURL) }
        let (data, _) = try await urlSession.data(from: url)
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let servers = json["servers"] as? [[String: Any]] else { return [] }
        return servers
    }

    nonisolated func addMCPServer(name: String, transport: String, command: [String]?, cmdUrl: String?) async throws {
        guard let reqUrl = URL(string: "\(baseURL)/mcp/servers") else { throw URLError(.badURL) }
        var request = URLRequest(url: reqUrl)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var body: [String: Any] = ["name": name, "transport": transport]
        if let cmd = command { body["command"] = cmd }
        if let u = cmdUrl { body["url"] = u }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            // 提取后端返回的 detail 错误信息
            var detail = "HTTP \((response as? HTTPURLResponse)?.statusCode ?? 0)"
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let msg = json["detail"] as? String {
                detail = msg
            } else if let text = String(data: data, encoding: .utf8), !text.isEmpty {
                detail = String(text.prefix(200))
            }
            throw NSError(domain: "MCP", code: (response as? HTTPURLResponse)?.statusCode ?? 0,
                          userInfo: [NSLocalizedDescriptionKey: detail])
        }
    }

    nonisolated func deleteMCPServer(name: String) async throws {
        let encoded = name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? name
        guard let url = URL(string: "\(baseURL)/mcp/servers/\(encoded)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }

    nonisolated func fetchMCPTools() async throws -> [[String: Any]] {
        guard let url = URL(string: "\(baseURL)/mcp/tools") else { throw URLError(.badURL) }
        let (data, _) = try await urlSession.data(from: url)
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let tools = json["tools"] as? [[String: Any]] else { return [] }
        return tools
    }

    // MARK: - Rollback / Snapshots

    nonisolated func fetchSnapshots(taskId: String? = nil, limit: Int = 50) async throws -> [[String: Any]] {
        var path = "\(baseURL)/rollback/snapshots?limit=\(limit)"
        if let tid = taskId, !tid.isEmpty { path += "&task_id=\(tid)" }
        guard let url = URL(string: path) else { throw URLError(.badURL) }
        let (data, _) = try await urlSession.data(from: url)
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let snapshots = json["snapshots"] as? [[String: Any]] else { return [] }
        return snapshots
    }

    nonisolated func rollbackSnapshot(snapshotId: String) async throws -> String {
        guard let url = URL(string: "\(baseURL)/rollback") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["snapshot_id": snapshotId])
        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }
        let json = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        return json["message"] as? String ?? "已回滚"
    }

    // MARK: - HITL

    nonisolated func hitlConfirm(actionId: String) async throws {
        let encoded = actionId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? actionId
        guard let url = URL(string: "\(baseURL)/hitl/confirm/\(encoded)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }

    nonisolated func hitlReject(actionId: String) async throws {
        let encoded = actionId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? actionId
        guard let url = URL(string: "\(baseURL)/hitl/reject/\(encoded)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }

    // MARK: - Feature Flags

    nonisolated func fetchFeatureFlags() async throws -> [[String: Any]] {
        guard let url = URL(string: "\(baseURL)/feature-flags") else { throw URLError(.badURL) }
        let (data, _) = try await urlSession.data(from: url)
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let flags = json["flags"] as? [[String: Any]] else { return [] }
        return flags
    }

    nonisolated func updateFeatureFlag(name: String, value: Any) async throws {
        guard let url = URL(string: "\(baseURL)/feature-flags") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["name": name, "value": value])
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }

    // MARK: - Audit Log

    nonisolated func fetchAuditLogs(limit: Int = 50, offset: Int = 0, logType: String? = nil) async throws -> [[String: Any]] {
        var path = "\(baseURL)/audit?limit=\(limit)&offset=\(offset)"
        if let t = logType, !t.isEmpty {
            let encoded = t.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? t
            path += "&type=\(encoded)"
        }
        guard let url = URL(string: path) else { throw URLError(.badURL) }
        let (data, _) = try await urlSession.data(from: url)
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let logs = json["logs"] as? [[String: Any]] else { return [] }
        return logs
    }

    // MARK: - Context Visualization

    nonisolated func fetchContext() async throws -> [String: Any] {
        guard let url = URL(string: "\(baseURL)/context") else { throw URLError(.badURL) }
        let (data, _) = try await urlSession.data(from: url)
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    // MARK: - Chow Duck API

    nonisolated func fetchDuckList() async throws -> [[String: Any]] {
        guard let url = URL(string: "\(baseURL)/duck/list") else { throw URLError(.badURL) }
        let (data, _) = try await urlSession.data(from: url)
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let ducks = json["ducks"] as? [[String: Any]] else { return [] }
        return ducks
    }

    nonisolated func fetchDuckStats() async throws -> [String: Any] {
        guard let url = URL(string: "\(baseURL)/duck/stats") else { throw URLError(.badURL) }
        let (data, _) = try await urlSession.data(from: url)
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    nonisolated func fetchDuckTemplates() async throws -> [[String: Any]] {
        guard let url = URL(string: "\(baseURL)/duck/templates") else { throw URLError(.badURL) }
        let (data, _) = try await urlSession.data(from: url)
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let templates = json["templates"] as? [[String: Any]] else { return [] }
        return templates
    }

    nonisolated func createLocalDuck(name: String, duckType: String, skills: [String]) async throws -> [String: Any] {
        guard let url = URL(string: "\(baseURL)/duck/create-local") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = ["name": name, "duck_type": duckType, "skills": skills]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    nonisolated func destroyLocalDuck(duckId: String) async throws {
        guard let url = URL(string: "\(baseURL)/duck/local/\(duckId)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
    }

    nonisolated func startLocalDuck(duckId: String) async throws -> [String: Any] {
        guard let url = URL(string: "\(baseURL)/duck/local/\(duckId)/start") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    /// 更新分身 LLM 配置（引用主配置中的 provider，运行时动态解析）
    nonisolated func updateDuckLLMConfig(duckId: String, apiKey: String, baseUrl: String, model: String, providerRef: String = "") async throws -> [String: Any] {
        guard let url = URL(string: "\(baseURL)/duck/local/\(duckId)/llm-config") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = ["api_key": apiKey, "base_url": baseUrl, "model": model, "provider_ref": providerRef]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    /// 获取主 Agent 已配置的在线 LLM 列表，供子 Duck 配置时一键导入
    nonisolated func fetchMainAgentLLMProviders() async throws -> [[String: Any]] {
        guard let url = URL(string: "\(baseURL)/config/llm-providers-for-import") else { throw URLError(.badURL) }
        let (data, response) = try await urlSession.data(from: url)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let providers = json["providers"] as? [[String: Any]] else { return [] }
        return providers
    }

    nonisolated func removeDuck(duckId: String) async throws {
        guard let url = URL(string: "\(baseURL)/duck/remove/\(duckId)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
    }

    nonisolated func fetchEggs() async throws -> [[String: Any]] {
        guard let url = URL(string: "\(baseURL)/duck/eggs") else { throw URLError(.badURL) }
        let (data, _) = try await urlSession.data(from: url)
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let eggs = json["eggs"] as? [[String: Any]] else { return [] }
        return eggs
    }

    nonisolated func createEgg(duckType: String, name: String?) async throws -> [String: Any] {
        guard let url = URL(string: "\(baseURL)/duck/create-egg") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var body: [String: Any] = ["duck_type": duckType]
        if let name = name, !name.isEmpty { body["name"] = name }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    nonisolated func deleteEgg(eggId: String) async throws {
        guard let url = URL(string: "\(baseURL)/duck/egg/\(eggId)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
    }

    func eggDownloadURL(eggId: String) -> URL? {
        URL(string: "\(baseURL)/duck/egg/\(eggId)/download")
    }

}

