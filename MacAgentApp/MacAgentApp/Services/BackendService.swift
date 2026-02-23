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
    
    // Autonomous mode chunks
    case taskStart(taskId: String, task: String)
    case modelSelected(modelType: String, reason: String, taskType: String, complexity: Int)
    case actionPlan(action: [String: Any], iteration: Int)
    case actionExecuting(actionId: String, actionType: String)
    case actionResult(actionId: String, success: Bool, output: String?, error: String?)
    case reflectStart
    case reflectResult(reflection: String)
    case taskComplete(taskId: String, success: Bool, summary: String, totalActions: Int)
}

@MainActor
class BackendService: ObservableObject {
    private let baseURL = "http://127.0.0.1:8765"
    private let wsURL = "ws://127.0.0.1:8765/ws"
    private var webSocketTask: URLSessionWebSocketTask?
    private var urlSession: URLSession
    private var pingTask: Task<Void, Never>?
    
    @Published var isConnected: Bool = false
    
    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 60
        config.timeoutIntervalForResource = 600
        self.urlSession = URLSession(configuration: config)
    }
    
    // MARK: - Connection
    
    func connect() async {
        disconnect()
        
        guard let url = URL(string: wsURL) else { return }
        
        webSocketTask = urlSession.webSocketTask(with: url)
        webSocketTask?.resume()
        
        isConnected = true
        startPing()
    }
    
    func disconnect() {
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
    
    // MARK: - Configuration
    
    nonisolated func updateConfig(provider: String, apiKey: String, baseUrl: String, model: String) async throws {
        guard let url = URL(string: "\(baseURL)/config") else {
            throw URLError(.badURL)
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: Any] = [
            "provider": provider,
            "api_key": apiKey,
            "base_url": baseUrl,
            "model": model
        ]
        
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
    
    func sendMessageStream(_ content: String, sessionId: String? = nil) -> AsyncThrowingStream<StreamChunk, Error> {
        return AsyncThrowingStream { [weak self] continuation in
            Task { [weak self] in
                guard let self = self else {
                    continuation.finish(throwing: URLError(.cancelled))
                    return
                }
                
                do {
                    // 确保连接
                    await self.ensureConnected()
                    
                    guard let webSocket = self.webSocketTask else {
                        continuation.finish(throwing: URLError(.cannotConnectToHost))
                        return
                    }
                    
                    // 发送消息，包含 session_id
                    var message: [String: Any] = [
                        "type": "chat",
                        "content": content
                    ]
                    if let sessionId = sessionId {
                        message["session_id"] = sessionId
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
                                        
                                        if let resultData = resultStr.data(using: .utf8),
                                           let resultJson = try? JSONSerialization.jsonObject(with: resultData) as? [String: Any] {
                                            if let imageBase64 = resultJson["image_base64"] as? String {
                                                let mimeType = resultJson["mime_type"] as? String ?? "image/png"
                                                let path = resultJson["screenshot_path"] as? String ?? resultJson["path"] as? String
                                                continuation.yield(.imageData(base64: imageBase64, mimeType: mimeType, path: path))
                                            } else if let screenshotPath = resultJson["screenshot_path"] as? String {
                                                continuation.yield(.localImage(path: screenshotPath))
                                            } else if let path = resultJson["path"] as? String,
                                                      path.hasSuffix(".png") || path.hasSuffix(".jpg") || path.hasSuffix(".jpeg") {
                                                continuation.yield(.localImage(path: path))
                                            }
                                        }
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
                                    continuation.finish()
                                    return
                                    
                                case "stopped":
                                    continuation.yield(.stopped)
                                    continuation.finish()
                                    return
                                    
                                case "error":
                                    let errorMsg = json["message"] as? String ?? json["error"] as? String ?? "Unknown error"
                                    continuation.yield(.error(errorMsg))
                                    continuation.finish()
                                    return
                                    
                                case "pong":
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
                    // 连接断开时尝试重连
                    await MainActor.run {
                        self.isConnected = false
                    }
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
    
    // MARK: - Autonomous Execution
    
    func sendAutonomousTask(_ task: String, sessionId: String? = nil, enableModelSelection: Bool = true, preferLocal: Bool = false) -> AsyncThrowingStream<StreamChunk, Error> {
        return AsyncThrowingStream { [weak self] continuation in
            Task { [weak self] in
                guard let self = self else {
                    continuation.finish(throwing: URLError(.cancelled))
                    return
                }
                
                do {
                    await self.ensureConnected()
                    
                    guard let webSocket = self.webSocketTask else {
                        continuation.finish(throwing: URLError(.cannotConnectToHost))
                        return
                    }
                    
                    var message: [String: Any] = [
                        "type": "autonomous_task",
                        "task": task,
                        "enable_model_selection": enableModelSelection,
                        "prefer_local": preferLocal
                    ]
                    
                    if let sessionId = sessionId {
                        message["session_id"] = sessionId
                    }
                    
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
                                    
                                case "execution_log":
                                    if let toolName = json["tool_name"] as? String,
                                       let level = json["level"] as? String,
                                       let message = json["message"] as? String {
                                        let actionId = json["action_id"] as? String ?? ""
                                        continuation.yield(.executionLog(toolName: toolName, actionId: actionId, level: level, message: message))
                                    }
                                    
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
                                    
                                case "done":
                                    let modelName = json["model"] as? String
                                    var tokenUsageAuto: TokenUsage? = nil
                                    if let usage = json["usage"] as? [String: Any] {
                                        tokenUsageAuto = TokenUsage(
                                            promptTokens: usage["prompt_tokens"] as? Int ?? 0,
                                            completionTokens: usage["completion_tokens"] as? Int ?? 0,
                                            totalTokens: usage["total_tokens"] as? Int ?? 0
                                        )
                                    }
                                    continuation.yield(.done(model: modelName, tokenUsage: tokenUsageAuto))
                                    continuation.finish()
                                    return
                                    
                                case "error":
                                    let errorMsg = json["message"] as? String ?? json["error"] as? String ?? "Unknown error"
                                    continuation.yield(.error(errorMsg))
                                    continuation.finish()
                                    return
                                    
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
                    await MainActor.run {
                        self.isConnected = false
                    }
                    continuation.finish(throwing: error)
                }
            }
        }
    }
}
