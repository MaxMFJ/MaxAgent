import Foundation
import Network
import ApplicationServices
import AppKit

// MARK: - IPC Protocol Models

/// XPC 通信协议（Swift 端 / XPC Helper 端使用）
@objc protocol MacAgentXPCProtocol {
    func sendMessage(_ jsonData: Data, withReply reply: @escaping (Data) -> Void)
    func ping(withReply reply: @escaping (String) -> Void)
}

/// 协议版本
let IPC_PROTOCOL_VERSION: Int = 1

/// IPC 消息类型
enum IPCMessageType: String, Codable {
    case action = "ACTION"          // 单个动作
    case batch = "BATCH"            // 批量动作
    case query = "QUERY"            // 查询状态
    case subscribe = "SUBSCRIBE"    // 订阅事件
    case unsubscribe = "UNSUBSCRIBE"
    case heartbeat = "HEARTBEAT"
    case event = "EVENT"            // 服务端推送事件
    case ack = "ACK"                // 确认
    case nack = "NACK"              // 拒绝
}

/// IPC 请求
struct IPCRequest: Codable {
    let id: String
    let type: IPCMessageType
    let version: Int?               // 协议版本
    let seq: UInt64?                // 序列号
    let clientId: String?           // 客户端 ID（多 Agent 支持）
    let token: String?              // 认证令牌
    let payload: [String: AnyCodable]?
    let batch: BatchRequest?
    let action: ActionRequest?
}

/// IPC 响应
struct IPCResponse: Codable {
    let id: String
    let type: IPCMessageType
    let success: Bool
    let error: String?
    let version: Int
    let seq: UInt64                 // 响应序列号
    let payload: [String: AnyCodable]?
    let batchResult: BatchResult?
    let actionResult: ActionResult?
    let stateVersion: UInt64
}

/// IPC 事件推送
struct IPCEvent: Codable {
    let type: IPCMessageType
    let eventType: String
    let stateVersion: UInt64
    let seq: UInt64
    let payload: [String: AnyCodable]
}

// MARK: - IPCService

/// 事件过滤器
struct EventFilter: Codable {
    var appNames: [String]?     // 仅监听这些应用
    var roles: [String]?        // 仅监听这些 role 类型
    var eventTypes: [String]?   // 仅监听这些事件类型
}

/// 审计日志条目
struct AuditEntry: Codable {
    let timestamp: Double
    let action: String
    let clientId: String
    let requestId: String
    let success: Bool
    let detail: String
}

/// TCP IPC 服务
/// 替代 HTTP Bridge，延迟 <1ms
/// 协议: 每条消息 = 4 字节长度头 (big-endian UInt32) + JSON payload
class IPCService: ObservableObject {
    static let shared = IPCService()
    
    @Published var isRunning = false
    @Published var connectionCount: Int = 0
    @Published var requestCount: Int = 0
    
    private var listener: NWListener?
    private var connections: [String: NWConnection] = [:]
    private var clientIds: [String: String] = [:]          // connectionId -> clientId
    private var subscriptions: [String: Set<String>] = [:] // connectionId -> subscribed event types
    private var eventFilters: [String: EventFilter] = [:]  // connectionId -> filter
    private let queue = DispatchQueue(label: "com.macagent.ipc", qos: .userInteractive)
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()
    private let batchExecutor = ActionBatchExecutor.shared
    private let stateStore = GUIStateStore.shared
    private let observerManager = AXObserverManager.shared
    
    /// 单调递增序列号
    private var seqCounter: UInt64 = 0
    private let seqLock = NSLock()
    
    /// 事件节流：记录上次事件时间（按类型）
    private var lastEventTime: [String: CFAbsoluteTime] = [:]
    private let throttleIntervalMs: Double = 50 // 50ms 内同类事件去重
    
    /// 操作审计日志
    private var auditLog: [AuditEntry] = []
    private let maxAuditEntries = 500
    
    let socketPath: String
    
    /// 认证令牌（每次启动随机生成，写入文件供本地 Python 读取）
    private(set) var authToken: String = ""
    private let authTokenPath: String
    /// 已认证连接
    private var authenticatedConns: Set<String> = []
    
    /// 多 Agent 协作：Agent 注册表
    struct AgentInfo: Codable {
        let clientId: String
        let connId: String
        var label: String?          // 可读名称（如 "duck-worker-1"）
        var claimedApps: Set<String> // 该 Agent 声称正在操作的应用
        var joinedAt: Double
    }
    private var agentRegistry: [String: AgentInfo] = [:]  // clientId -> AgentInfo
    
    /// 应用级锁：某个 Agent "claim" 正在操作某应用，其他 Agent 应避免操作
    /// 键=appName（小写），值=clientId
    private var appLocks: [String: String] = [:]
    
    /// XPC 监听器（用于 Swift-to-Swift 高速通信）
    private var xpcListener: NSXPCListener?
    private var xpcDelegate: XPCServiceDelegate?
    
    private init() {
        let tmpDir = FileManager.default.temporaryDirectory.path
        socketPath = "\(tmpDir)/macagent_ax.sock"
        authTokenPath = "\(tmpDir)/macagent_ipc_token"
        authToken = UUID().uuidString
    }
    
    /// 将 auth token 写入文件（仅当前用户可读）
    private func writeAuthToken() {
        let data = authToken.data(using: .utf8)!
        FileManager.default.createFile(atPath: authTokenPath, contents: data, attributes: [.posixPermissions: 0o600])
        print("[IPC] Auth token written to \(authTokenPath)")
    }
    
    /// 生成下一个序列号
    private func nextSeq() -> UInt64 {
        seqLock.lock()
        defer { seqLock.unlock() }
        seqCounter += 1
        return seqCounter
    }
    
    /// 记录审计日志
    private func audit(_ action: String, connId: String, requestId: String, success: Bool, detail: String = "") {
        let entry = AuditEntry(
            timestamp: CFAbsoluteTimeGetCurrent(),
            action: action,
            clientId: clientIds[connId] ?? connId.prefix(8).description,
            requestId: requestId,
            success: success,
            detail: detail
        )
        auditLog.append(entry)
        if auditLog.count > maxAuditEntries {
            auditLog.removeFirst(auditLog.count - maxAuditEntries)
        }
    }
    
    /// 检查事件是否应被节流
    private func shouldThrottle(eventType: String) -> Bool {
        let now = CFAbsoluteTimeGetCurrent()
        if let last = lastEventTime[eventType] {
            if (now - last) * 1000 < throttleIntervalMs {
                return true
            }
        }
        lastEventTime[eventType] = now
        return false
    }
    
    // MARK: - Lifecycle
    
    func start() {
        guard !isRunning else { return }
        
        // 生成并写入 auth token
        authToken = UUID().uuidString
        writeAuthToken()
        
        // 清理旧 socket 文件
        try? FileManager.default.removeItem(atPath: socketPath)
        
        do {
            let params = NWParameters.tcp
            params.allowLocalEndpointReuse = true
            // 使用 TCP 监听 localhost 端口 (从 PortConfiguration 读取)
            let ipcPort = MainActor.assumeIsolated { PortConfiguration.shared.ipcPort }
            listener = try NWListener(using: params, on: NWEndpoint.Port(rawValue: ipcPort)!)
        } catch {
            print("[IPC] Failed to create listener: \(error)")
            return
        }
        
        listener?.stateUpdateHandler = { [weak self] state in
            DispatchQueue.main.async {
                switch state {
                case .ready:
                    self?.isRunning = true
                    print("[IPC] Listening on \(self?.socketPath ?? "")")
                case .failed(let error):
                    print("[IPC] Listener failed: \(error)")
                    self?.isRunning = false
                case .cancelled:
                    self?.isRunning = false
                default:
                    break
                }
            }
        }
        
        listener?.newConnectionHandler = { [weak self] connection in
            self?.handleNewConnection(connection)
        }
        
        listener?.start(queue: queue)
        setupEventForwarding()
        
        // 启动 XPC 监听器（Mach service 名称）
        startXPCListener()
    }
    
    /// 启动 XPC 监听器用于 Swift-to-Swift 零拷贝通信
    private func startXPCListener() {
        let xpcServiceName = "com.macagent.ipc.xpc"
        xpcListener = NSXPCListener(machServiceName: xpcServiceName)
        xpcDelegate = XPCServiceDelegate(service: self)
        xpcListener?.delegate = xpcDelegate
        xpcListener?.resume()
        print("[IPC] XPC listener started: \(xpcServiceName)")
    }
    
    /// 处理 XPC 收到的 JSON 请求（复用 TCP 同款逻辑）
    func handleXPCRequest(data: Data) -> Data {
        guard let request = try? decoder.decode(IPCRequest.self, from: data) else {
            let errResp = makeResponse(id: "xpc", type: .nack, success: false, error: "Invalid JSON")
            return (try? encoder.encode(errResp)) ?? Data()
        }
        let connId = "xpc-\(request.clientId ?? UUID().uuidString.prefix(8).description)"
        let response = processRequest(request: request, connId: connId)
        return (try? encoder.encode(response)) ?? Data()
    }
    
    func stop() {
        listener?.cancel()
        xpcListener?.suspend()
        xpcListener = nil
        for conn in connections.values {
            conn.cancel()
        }
        connections.removeAll()
        subscriptions.removeAll()
        try? FileManager.default.removeItem(atPath: socketPath)
        DispatchQueue.main.async { [weak self] in
            self?.isRunning = false
            self?.connectionCount = 0
        }
    }
    
    // MARK: - Connection Handling
    
    private func handleNewConnection(_ connection: NWConnection) {
        let connId = UUID().uuidString
        connections[connId] = connection
        DispatchQueue.main.async { [weak self] in
            self?.connectionCount = self?.connections.count ?? 0
        }
        
        connection.stateUpdateHandler = { [weak self] state in
            switch state {
            case .ready:
                print("[IPC] Client connected: \(connId.prefix(8))")
                self?.receiveMessage(connection: connection, connId: connId)
            case .failed, .cancelled:
                print("[IPC] Client disconnected: \(connId.prefix(8))")
                self?.connections.removeValue(forKey: connId)
                self?.subscriptions.removeValue(forKey: connId)
                self?.eventFilters.removeValue(forKey: connId)
                // 清理 Agent 注册表和应用锁
                if let cid = self?.clientIds[connId] {
                    if let claimed = self?.agentRegistry[cid]?.claimedApps {
                        for app in claimed { self?.appLocks.removeValue(forKey: app) }
                    }
                    self?.agentRegistry.removeValue(forKey: cid)
                }
                self?.clientIds.removeValue(forKey: connId)
                self?.authenticatedConns.remove(connId)
                DispatchQueue.main.async {
                    self?.connectionCount = self?.connections.count ?? 0
                }
            default:
                break
            }
        }
        
        connection.start(queue: queue)
    }
    
    // MARK: - Message Framing: 4-byte length + 4-byte CRC32 + JSON
    
    /// CRC32 校验（IEEE 多项式）
    private func crc32(_ data: Data) -> UInt32 {
        var crc: UInt32 = 0xFFFFFFFF
        for byte in data {
            crc ^= UInt32(byte)
            for _ in 0..<8 {
                crc = (crc >> 1) ^ (crc & 1 != 0 ? 0xEDB88320 : 0)
            }
        }
        return crc ^ 0xFFFFFFFF
    }
    
    private func receiveMessage(connection: NWConnection, connId: String) {
        // 读 8 字节头：4 字节长度 + 4 字节 CRC32
        connection.receive(minimumIncompleteLength: 8, maximumLength: 8) { [weak self] data, _, isComplete, error in
            guard let self = self else { return }
            
            if isComplete || error != nil {
                connection.cancel()
                return
            }
            
            guard let headerData = data, headerData.count == 8 else {
                // 兼容旧协议：可能只有 4 字节头
                if let d = data, d.count == 4 {
                    self.receiveMessageLegacy(headerData: d, connection: connection, connId: connId)
                    return
                }
                self.receiveMessage(connection: connection, connId: connId)
                return
            }
            
            let length = headerData.withUnsafeBytes { $0.load(fromByteOffset: 0, as: UInt32.self).bigEndian }
            let expectedCRC = headerData.withUnsafeBytes { $0.load(fromByteOffset: 4, as: UInt32.self).bigEndian }
            
            guard length > 0, length < 10_000_000 else {
                connection.cancel()
                return
            }
            
            // 读 JSON payload
            connection.receive(minimumIncompleteLength: Int(length), maximumLength: Int(length)) { [weak self] data, _, _, error in
                guard let self = self else { return }
                
                if let error = error {
                    print("[IPC] Read error: \(error)")
                    return
                }
                
                guard let jsonData = data else {
                    self.receiveMessage(connection: connection, connId: connId)
                    return
                }
                
                // CRC32 校验
                let actualCRC = self.crc32(jsonData)
                if expectedCRC != 0 && actualCRC != expectedCRC {
                    print("[IPC] CRC32 mismatch: expected \(expectedCRC), got \(actualCRC)")
                    // 发送 NACK 让客户端重试
                    let nack = self.makeResponse(id: "crc_error", type: .nack, success: false, error: "CRC32 checksum mismatch")
                    if let respData = try? self.encoder.encode(nack) {
                        self.sendMessage(respData, to: connection)
                    }
                    self.receiveMessage(connection: connection, connId: connId)
                    return
                }
                
                DispatchQueue.main.async { self.requestCount += 1 }
                self.processMessage(data: jsonData, connection: connection, connId: connId)
                self.receiveMessage(connection: connection, connId: connId)
            }
        }
    }
    
    /// 兼容旧协议（无 CRC32 的 4 字节头）
    private func receiveMessageLegacy(headerData: Data, connection: NWConnection, connId: String) {
        let length = headerData.withUnsafeBytes { $0.load(as: UInt32.self).bigEndian }
        guard length > 0, length < 10_000_000 else {
            connection.cancel()
            return
        }
        connection.receive(minimumIncompleteLength: Int(length), maximumLength: Int(length)) { [weak self] data, _, _, error in
            guard let self = self else { return }
            if error != nil { return }
            guard let jsonData = data else {
                self.receiveMessage(connection: connection, connId: connId)
                return
            }
            DispatchQueue.main.async { self.requestCount += 1 }
            self.processMessage(data: jsonData, connection: connection, connId: connId)
            self.receiveMessage(connection: connection, connId: connId)
        }
    }
    
    private func sendMessage(_ data: Data, to connection: NWConnection) {
        var length = UInt32(data.count).bigEndian
        let lengthData = Data(bytes: &length, count: 4)
        var checksum = crc32(data).bigEndian
        let crcData = Data(bytes: &checksum, count: 4)
        
        connection.send(content: lengthData + crcData + data, completion: .contentProcessed { error in
            if let error = error {
                print("[IPC] Send error: \(error)")
            }
        })
    }
    
    // MARK: - Message Processing
    
    /// 构建标准响应
    private func makeResponse(
        id: String, type: IPCMessageType, success: Bool, error: String? = nil,
        payload: [String: AnyCodable]? = nil, batchResult: BatchResult? = nil,
        actionResult: ActionResult? = nil
    ) -> IPCResponse {
        return IPCResponse(
            id: id, type: type, success: success, error: error,
            version: IPC_PROTOCOL_VERSION, seq: nextSeq(),
            payload: payload, batchResult: batchResult, actionResult: actionResult,
            stateVersion: stateStore.version
        )
    }
    
    private func processMessage(data: Data, connection: NWConnection, connId: String) {
        guard let request = try? decoder.decode(IPCRequest.self, from: data) else {
            let errorResp = makeResponse(id: "unknown", type: .nack, success: false, error: "Invalid JSON")
            if let respData = try? encoder.encode(errorResp) {
                sendMessage(respData, to: connection)
            }
            return
        }
        
        // 注册 clientId
        if let cid = request.clientId {
            clientIds[connId] = cid
        }
        
        // 认证检查：HEARTBEAT 免认证，其它需要 token
        if request.type != .heartbeat && !authenticatedConns.contains(connId) {
            if let token = request.token, token == authToken {
                authenticatedConns.insert(connId)
            } else {
                let errorResp = makeResponse(id: request.id, type: .nack, success: false, error: "Unauthorized: invalid or missing token")
                audit("AUTH_FAIL", connId: connId, requestId: request.id, success: false)
                if let respData = try? encoder.encode(errorResp) {
                    sendMessage(respData, to: connection)
                }
                return
            }
        }
        
        let response = processRequest(request: request, connId: connId)
        
        if let respData = try? encoder.encode(response) {
            sendMessage(respData, to: connection)
        }
    }
    
    /// 核心请求处理逻辑（TCP 和 XPC 共用）
    private func processRequest(request: IPCRequest, connId: String) -> IPCResponse {
        switch request.type {
        case .heartbeat:
            return makeResponse(id: request.id, type: .heartbeat, success: true, payload: [
                "socket_path": AnyCodable(socketPath),
                "uptime": AnyCodable(ProcessInfo.processInfo.systemUptime),
                "protocol_version": AnyCodable(IPC_PROTOCOL_VERSION),
                "client_count": AnyCodable(connections.count)
            ])
            
        case .action:
            if let action = request.action {
                let result = batchExecutor.execute(action: action)
                audit("ACTION:\(action.actionType.rawValue)", connId: connId, requestId: request.id, success: result.success)
                return makeResponse(id: request.id, type: .action, success: result.success, error: result.error, actionResult: result)
            } else {
                return makeResponse(id: request.id, type: .nack, success: false, error: "Missing action")
            }
            
        case .batch:
            if let batch = request.batch {
                let result = batchExecutor.executeBatch(batch: batch)
                audit("BATCH:\(batch.actions.count)actions", connId: connId, requestId: request.id, success: result.success, detail: "\(result.durationMs)ms")
                return makeResponse(id: request.id, type: .batch, success: result.success, batchResult: result)
            } else {
                return makeResponse(id: request.id, type: .nack, success: false, error: "Missing batch")
            }
            
        case .query:
            return handleQuery(request: request)
            
        case .subscribe:
            let events = (request.payload?["events"]?.value as? [String]) ?? ["*"]
            var subs = subscriptions[connId] ?? Set<String>()
            for e in events { subs.insert(e) }
            subscriptions[connId] = subs
            if let filterPayload = request.payload?["filter"]?.value as? [String: Any] {
                var filter = EventFilter()
                filter.appNames = filterPayload["app_names"] as? [String]
                filter.roles = filterPayload["roles"] as? [String]
                filter.eventTypes = filterPayload["event_types"] as? [String]
                eventFilters[connId] = filter
            }
            audit("SUBSCRIBE", connId: connId, requestId: request.id, success: true, detail: events.joined(separator: ","))
            return makeResponse(id: request.id, type: .subscribe, success: true, payload: [
                "subscribed": AnyCodable(Array(subs))
            ])
            
        case .unsubscribe:
            subscriptions.removeValue(forKey: connId)
            eventFilters.removeValue(forKey: connId)
            return makeResponse(id: request.id, type: .unsubscribe, success: true)
            
        case .event, .ack, .nack:
            return makeResponse(id: request.id, type: .nack, success: false, error: "Not a valid request type")
        }
    }
    
    // MARK: - Query Handler
    
    private func handleQuery(request: IPCRequest) -> IPCResponse {
        let queryType = request.payload?["query"]?.value as? String ?? "state"
        
        switch queryType {
        case "state":
            let sinceVersion = (request.payload?["since_version"]?.value as? Int).map { UInt64($0) }
            if let sv = sinceVersion, sv < stateStore.version {
                let diff = stateStore.getDiff(sinceVersion: sv)
                let eventDicts = diff.events.map { e -> [String: Any] in
                    ["event_type": e.eventType, "app_name": e.appName, "pid": Int(e.pid),
                     "element_role": e.elementRole, "element_title": e.elementTitle]
                }
                return makeResponse(id: request.id, type: .query, success: true, payload: [
                    "type": AnyCodable("diff"),
                    "from_version": AnyCodable(Int(diff.fromVersion)),
                    "to_version": AnyCodable(Int(diff.toVersion)),
                    "focus_changed": AnyCodable(diff.focusChanged),
                    "events": AnyCodable(eventDicts)
                ])
            }
            let snapshot = stateStore.getSnapshot()
            // 如果 windowStates 为空但有焦点应用，做实时 AX 查询补充窗口数
            var windowCount = snapshot.windows.count
            if windowCount == 0 && !snapshot.focusedAppName.isEmpty {
                if let windows = AccessibilityService.shared.getWindowInfo(appName: snapshot.focusedAppName) {
                    windowCount = windows.count
                }
            }
            return makeResponse(id: request.id, type: .query, success: true, payload: [
                "type": AnyCodable("snapshot"),
                "version": AnyCodable(Int(snapshot.version)),
                "focused_app": AnyCodable(snapshot.focusedAppName),
                "focused_app_pid": AnyCodable(Int(snapshot.focusedAppPid)),
                "focused_window": AnyCodable(stateStore.focusedWindowTitle),
                "focused_element_role": AnyCodable(snapshot.focusedElementRole),
                "focused_element_title": AnyCodable(snapshot.focusedElementTitle),
                "window_count": AnyCodable(windowCount)
            ])
            
        case "apps":
            let apps = AccessibilityService.shared.listRunningApps()
            let appDicts = apps.map { a -> [String: Any] in
                ["name": a.name, "pid": Int(a.pid), "bundle_id": a.bundleId]
            }
            return makeResponse(id: request.id, type: .query, success: true, payload: [
                "apps": AnyCodable(appDicts)
            ])
            
        case "windows":
            guard let appName = request.payload?["app_name"]?.value as? String else {
                return makeResponse(id: request.id, type: .query, success: false, error: "Missing app_name")
            }
            guard let windows = AccessibilityService.shared.getWindowInfo(appName: appName) else {
                return makeResponse(id: request.id, type: .query, success: false, error: "App not found")
            }
            let winDicts = windows.map { w -> [String: Any] in
                var d: [String: Any] = ["title": w.title, "focused": w.focused, "minimized": w.minimized, "full_screen": w.fullScreen]
                if let p = w.position { d["x"] = p.x; d["y"] = p.y }
                if let s = w.size { d["width"] = s.width; d["height"] = s.height }
                return d
            }
            return makeResponse(id: request.id, type: .query, success: true, payload: [
                "windows": AnyCodable(winDicts)
            ])
            
        case "elements":
            guard let appName = request.payload?["app_name"]?.value as? String else {
                return makeResponse(id: request.id, type: .query, success: false, error: "Missing app_name")
            }
            let maxDepth = (request.payload?["max_depth"]?.value as? Int) ?? 5
            guard let elements = AccessibilityService.shared.getFlatElements(appName: appName, maxDepth: maxDepth) else {
                return makeResponse(id: request.id, type: .query, success: false, error: "App not found")
            }
            let elemDicts = elements.prefix(200).map { e -> [String: Any] in
                var d: [String: Any] = ["role": e.role, "title": e.title, "label": e.label, "enabled": e.enabled, "identifier": e.identifier]
                if let c = e.center { d["center_x"] = c.x; d["center_y"] = c.y }
                return d
            }
            return makeResponse(id: request.id, type: .query, success: true, payload: [
                "elements": AnyCodable(elemDicts),
                "count": AnyCodable(elemDicts.count),
                "total": AnyCodable(elements.count)
            ])
            
        case "focused":
            let info = AccessibilityService.shared.getFocusedElement()
            return makeResponse(id: request.id, type: .query, success: true, payload: [
                "role": AnyCodable(info?.role ?? ""),
                "title": AnyCodable(info?.title ?? ""),
                "value": AnyCodable(info?.value ?? ""),
                "label": AnyCodable(info?.label ?? "")
            ])
            
        case "audit":
            // 返回审计日志
            let count = min(auditLog.count, (request.payload?["count"]?.value as? Int) ?? 50)
            let entries = auditLog.suffix(count)
            let dicts = entries.map { e -> [String: Any] in
                ["timestamp": e.timestamp, "action": e.action, "client": e.clientId,
                 "request_id": e.requestId, "success": e.success, "detail": e.detail]
            }
            return makeResponse(id: request.id, type: .query, success: true, payload: [
                "audit": AnyCodable(dicts),
                "total": AnyCodable(auditLog.count)
            ])
            
        case "agents":
            // 列出所有已连接的 Agent
            let agentDicts = agentRegistry.values.map { a -> [String: Any] in
                ["client_id": a.clientId, "label": a.label ?? "", "claimed_apps": Array(a.claimedApps), "joined_at": a.joinedAt]
            }
            return makeResponse(id: request.id, type: .query, success: true, payload: [
                "agents": AnyCodable(agentDicts),
                "count": AnyCodable(agentRegistry.count),
                "app_locks": AnyCodable(appLocks)
            ])
            
        case "claim_app":
            // Agent 声明正在操作某应用
            guard let appName = request.payload?["app_name"]?.value as? String,
                  let cid = request.clientId ?? clientIds[request.id] else {
                return makeResponse(id: request.id, type: .query, success: false, error: "Missing app_name or clientId")
            }
            let key = appName.lowercased()
            if let owner = appLocks[key], owner != cid {
                return makeResponse(id: request.id, type: .query, success: false, error: "App '\(appName)' is locked by agent '\(owner)'")
            }
            appLocks[key] = cid
            agentRegistry[cid]?.claimedApps.insert(key)
            audit("CLAIM_APP", connId: cid, requestId: request.id, success: true, detail: appName)
            return makeResponse(id: request.id, type: .query, success: true, payload: [
                "claimed": AnyCodable(appName),
                "owner": AnyCodable(cid)
            ])
            
        case "release_app":
            // Agent 释放应用操作锁
            guard let appName = request.payload?["app_name"]?.value as? String,
                  let cid = request.clientId ?? clientIds[request.id] else {
                return makeResponse(id: request.id, type: .query, success: false, error: "Missing app_name or clientId")
            }
            let key = appName.lowercased()
            if appLocks[key] == cid {
                appLocks.removeValue(forKey: key)
                agentRegistry[cid]?.claimedApps.remove(key)
            }
            audit("RELEASE_APP", connId: cid, requestId: request.id, success: true, detail: appName)
            return makeResponse(id: request.id, type: .query, success: true)
            
        case "register_agent":
            // Agent 注册自己
            guard let cid = request.clientId ?? clientIds[request.id] else {
                return makeResponse(id: request.id, type: .query, success: false, error: "Missing clientId")
            }
            let label = request.payload?["label"]?.value as? String
            let connId = clientIds.first(where: { $0.value == cid })?.key ?? request.id
            agentRegistry[cid] = AgentInfo(clientId: cid, connId: connId, label: label, claimedApps: [], joinedAt: CFAbsoluteTimeGetCurrent())
            audit("REGISTER_AGENT", connId: cid, requestId: request.id, success: true, detail: label ?? cid)
            return makeResponse(id: request.id, type: .query, success: true, payload: [
                "registered": AnyCodable(cid),
                "label": AnyCodable(label ?? "")
            ])
            
        case "find_text":
            // Vision OCR 文字搜索
            guard let searchText = request.payload?["text"]?.value as? String else {
                return makeResponse(id: request.id, type: .query, success: false, error: "Missing text")
            }
            let vision = VisionFallbackService.shared
            let matches: [TextMatch]
            if let appName = request.payload?["app_name"]?.value as? String,
               let pid = NSWorkspace.shared.runningApplications.first(where: { $0.localizedName == appName })?.processIdentifier {
                matches = vision.findTextInApp(pid: pid, searchText: searchText)
            } else {
                matches = vision.findText(searchText, in: vision.captureMainScreen())
            }
            let encoded = matches.map { m -> [String: Any] in
                ["text": m.text, "confidence": m.confidence,
                 "x": m.center.x, "y": m.center.y,
                 "rect_x": m.rect.origin.x, "rect_y": m.rect.origin.y,
                 "rect_w": m.rect.width, "rect_h": m.rect.height]
            }
            audit("FIND_TEXT", connId: request.clientId ?? "unknown", requestId: request.id, success: !matches.isEmpty, detail: searchText)
            return makeResponse(id: request.id, type: .query, success: true, payload: [
                "matches": AnyCodable(encoded),
                "count": AnyCodable(matches.count)
            ])
            
        default:
            return makeResponse(id: request.id, type: .query, success: false, error: "Unknown query: \(queryType)")
        }
    }
    
    // MARK: - Event Forwarding (with throttle + filter)
    
    private func setupEventForwarding() {
        observerManager.onEvent = { [weak self] axEvent in
            guard let self = self else { return }
            
            // 事件节流：同类事件 50ms 内合并
            if self.shouldThrottle(eventType: axEvent.eventType) { return }
            
            let eventSeq = self.nextSeq()
            let event = IPCEvent(type: .event, eventType: axEvent.eventType, stateVersion: self.stateStore.version, seq: eventSeq, payload: [
                "app_name": AnyCodable(axEvent.appName),
                "pid": AnyCodable(Int(axEvent.pid)),
                "element_role": AnyCodable(axEvent.elementRole),
                "element_title": AnyCodable(axEvent.elementTitle)
            ])
            
            guard let data = try? self.encoder.encode(event) else { return }
            
            for (connId, conn) in self.connections {
                guard let subs = self.subscriptions[connId] else { continue }
                
                // 检查事件类型订阅
                guard subs.contains("*") || subs.contains(axEvent.eventType) else { continue }
                
                // 检查高级过滤器
                if let filter = self.eventFilters[connId] {
                    if let appNames = filter.appNames, !appNames.contains(where: { axEvent.appName.lowercased().contains($0.lowercased()) }) {
                        continue
                    }
                    if let roles = filter.roles, !roles.contains(axEvent.elementRole) {
                        continue
                    }
                }
                
                self.sendMessage(data, to: conn)
            }
        }
    }
}

// MARK: - XPC Delegate

/// NSXPCListener 代理，负责接受 XPC 连接并绑定协议
class XPCServiceDelegate: NSObject, NSXPCListenerDelegate {
    private weak var service: IPCService?
    
    init(service: IPCService) {
        self.service = service
    }
    
    func listener(_ listener: NSXPCListener, shouldAcceptNewConnection newConnection: NSXPCConnection) -> Bool {
        newConnection.exportedInterface = NSXPCInterface(with: MacAgentXPCProtocol.self)
        newConnection.exportedObject = XPCRequestHandler(service: service)
        newConnection.resume()
        print("[XPC] Accepted new connection")
        return true
    }
}

/// XPC 请求处理器，实现 MacAgentXPCProtocol
class XPCRequestHandler: NSObject, MacAgentXPCProtocol {
    private weak var service: IPCService?
    
    init(service: IPCService?) {
        self.service = service
    }
    
    func sendMessage(_ jsonData: Data, withReply reply: @escaping (Data) -> Void) {
        guard let svc = service else {
            reply(Data())
            return
        }
        let response = svc.handleXPCRequest(data: jsonData)
        reply(response)
    }
    
    func ping(withReply reply: @escaping (String) -> Void) {
        reply("pong")
    }
}
