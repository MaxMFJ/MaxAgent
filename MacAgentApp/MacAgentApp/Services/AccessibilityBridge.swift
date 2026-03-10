import Foundation
import Network
import ApplicationServices

/// AccessibilityBridge — 轻量级 HTTP 服务器
/// 运行在 Swift 进程中 (端口 5650)，暴露 Accessibility API 给 Python 后端调用
/// 使用 Network.framework (NWListener)，无需第三方依赖
@MainActor
class AccessibilityBridge: ObservableObject {
    static let shared = AccessibilityBridge()
    
    @Published var isRunning = false
    @Published var port: UInt16 = PortConfiguration.defaultAXBridgePort
    @Published var requestCount: Int = 0
    
    private var listener: NWListener?
    private let axService = AccessibilityService.shared
    private let queue = DispatchQueue(label: "com.macagent.ax-bridge", qos: .userInteractive)
    
    private init() {}
    
    // MARK: - Lifecycle
    
    func start(port: UInt16? = nil) {
        guard !isRunning else { return }
        let resolvedPort = port ?? PortConfiguration.shared.axBridgePort
        self.port = resolvedPort
        
        do {
            let params = NWParameters.tcp
            params.allowLocalEndpointReuse = true
            listener = try NWListener(using: params, on: NWEndpoint.Port(rawValue: resolvedPort)!)
        } catch {
            print("[AX-Bridge] Failed to create listener: \(error)")
            return
        }
        
        listener?.stateUpdateHandler = { [weak self] state in
            Task { @MainActor in
                switch state {
                case .ready:
                    self?.isRunning = true
                    print("[AX-Bridge] Listening on port \(port)")
                case .failed(let error):
                    print("[AX-Bridge] Listener failed: \(error)")
                    self?.isRunning = false
                case .cancelled:
                    self?.isRunning = false
                default:
                    break
                }
            }
        }
        
        listener?.newConnectionHandler = { [weak self] connection in
            self?.handleConnection(connection)
        }
        
        listener?.start(queue: queue)
    }
    
    func stop() {
        listener?.cancel()
        listener = nil
        isRunning = false
        print("[AX-Bridge] Stopped")
    }
    
    // MARK: - Connection Handling
    
    private nonisolated func handleConnection(_ connection: NWConnection) {
        connection.stateUpdateHandler = { state in
            if case .failed(let error) = state {
                print("[AX-Bridge] Connection failed: \(error)")
                connection.cancel()
            }
        }
        connection.start(queue: queue)
        receiveHTTP(connection: connection)
    }
    
    private nonisolated func receiveHTTP(connection: NWConnection) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, isComplete, error in
            guard let self = self, let data = data, !data.isEmpty else {
                if isComplete { connection.cancel() }
                return
            }
            
            guard let rawRequest = String(data: data, encoding: .utf8) else {
                self.sendResponse(connection: connection, status: 400, body: ["error": "Invalid request"])
                return
            }
            
            // 解析 HTTP 请求
            let (method, path, bodyData) = self.parseHTTPRequest(rawRequest, rawData: data)
            
            Task { @MainActor in
                self.requestCount += 1
                let response = await self.routeRequest(method: method, path: path, body: bodyData)
                self.sendResponse(connection: connection, status: response.status, body: response.body)
            }
        }
    }
    
    // MARK: - HTTP Parsing
    
    private nonisolated func parseHTTPRequest(_ raw: String, rawData: Data) -> (method: String, path: String, body: Data?) {
        let lines = raw.components(separatedBy: "\r\n")
        guard let requestLine = lines.first else { return ("GET", "/", nil) }
        let parts = requestLine.components(separatedBy: " ")
        let method = parts.count > 0 ? parts[0] : "GET"
        let path = parts.count > 1 ? parts[1] : "/"
        
        // 解析 body（查找空行之后的内容）
        if let bodyRange = raw.range(of: "\r\n\r\n") {
            let headerPart = raw[raw.startIndex..<bodyRange.lowerBound]
            let headerBytes = headerPart.utf8.count + 4 // +4 for \r\n\r\n
            if rawData.count > headerBytes {
                let bodyData = rawData.subdata(in: headerBytes..<rawData.count)
                return (method, path, bodyData)
            }
        }
        return (method, path, nil)
    }
    
    // MARK: - Router
    
    private struct HTTPResponse {
        let status: Int
        let body: Any
    }
    
    private func routeRequest(method: String, path: String, body: Data?) async -> HTTPResponse {
        // 去除 query string
        let cleanPath = path.components(separatedBy: "?").first ?? path
        
        switch (method, cleanPath) {
        case ("GET", "/ax/status"):
            return handleStatus()
            
        case ("GET", "/ax/apps"):
            return handleListApps()
            
        case ("POST", "/ax/windows"):
            return handleGetWindows(body: body)
            
        case ("POST", "/ax/elements"):
            return handleGetElements(body: body)
            
        case ("POST", "/ax/elements/flat"):
            return handleGetFlatElements(body: body)
            
        case ("POST", "/ax/action"):
            return handlePerformAction(body: body)
            
        case ("POST", "/ax/set-value"):
            return handleSetValue(body: body)
            
        case ("GET", "/ax/focused"):
            return handleGetFocused()
            
        case ("POST", "/ax/element-at"):
            return handleGetElementAt(body: body)
            
        case ("POST", "/ax/find"):
            return handleFindElements(body: body)
            
        default:
            return HTTPResponse(status: 404, body: [
                "error": "Not found",
                "available_endpoints": [
                    "GET  /ax/status",
                    "GET  /ax/apps",
                    "POST /ax/windows",
                    "POST /ax/elements",
                    "POST /ax/elements/flat",
                    "POST /ax/action",
                    "POST /ax/set-value",
                    "GET  /ax/focused",
                    "POST /ax/element-at",
                    "POST /ax/find"
                ]
            ])
        }
    }
    
    // MARK: - Handlers
    
    private func handleStatus() -> HTTPResponse {
        return HTTPResponse(status: 200, body: [
            "trusted": axService.isTrusted,
            "running": true,
            "port": Int(port),
            "request_count": requestCount
        ])
    }
    
    private func handleListApps() -> HTTPResponse {
        let apps = axService.listRunningApps()
        let encoded = apps.map { app -> [String: Any] in
            [
                "name": app.name,
                "pid": Int(app.pid),
                "bundle_id": app.bundleId ?? "",
                "window_count": app.windows.count
            ]
        }
        return HTTPResponse(status: 200, body: ["apps": encoded])
    }
    
    private func handleGetWindows(body: Data?) -> HTTPResponse {
        guard let params = parseJSON(body),
              let appName = params["app_name"] as? String else {
            return HTTPResponse(status: 400, body: ["error": "Missing app_name"])
        }
        
        guard let windows = axService.getWindowInfo(appName: appName) else {
            return HTTPResponse(status: 404, body: ["error": "App not found: \(appName)"])
        }
        
        let encoded = windows.map { win -> [String: Any] in
            var dict: [String: Any] = [
                "title": win.title,
                "focused": win.focused,
                "minimized": win.minimized,
                "full_screen": win.fullScreen
            ]
            if let p = win.position { dict["position"] = ["x": p.x, "y": p.y] }
            if let s = win.size { dict["size"] = ["width": s.width, "height": s.height] }
            return dict
        }
        return HTTPResponse(status: 200, body: ["windows": encoded])
    }
    
    private func handleGetElements(body: Data?) -> HTTPResponse {
        guard let params = parseJSON(body),
              let appName = params["app_name"] as? String else {
            return HTTPResponse(status: 400, body: ["error": "Missing app_name"])
        }
        let maxDepth = params["max_depth"] as? Int ?? 5
        let windowIndex = params["window_index"] as? Int ?? 0
        
        guard let elements = axService.getElementTree(appName: appName, maxDepth: maxDepth, windowIndex: windowIndex) else {
            return HTTPResponse(status: 404, body: ["error": "App or window not found: \(appName)"])
        }
        
        let encoded = elements.map { encodeElement($0) }
        return HTTPResponse(status: 200, body: ["elements": encoded, "count": encoded.count])
    }
    
    private func handleGetFlatElements(body: Data?) -> HTTPResponse {
        guard let params = parseJSON(body),
              let appName = params["app_name"] as? String else {
            return HTTPResponse(status: 400, body: ["error": "Missing app_name"])
        }
        let maxDepth = params["max_depth"] as? Int ?? 5
        let windowIndex = params["window_index"] as? Int ?? 0
        let maxCount = params["max_count"] as? Int ?? 200
        
        guard var elements = axService.getFlatElements(appName: appName, maxDepth: maxDepth, windowIndex: windowIndex) else {
            return HTTPResponse(status: 404, body: ["error": "App or window not found: \(appName)"])
        }
        
        let totalCount = elements.count
        if elements.count > maxCount {
            elements = Array(elements.prefix(maxCount))
        }
        
        let encoded = elements.map { encodeElement($0) }
        return HTTPResponse(status: 200, body: [
            "elements": encoded,
            "count": encoded.count,
            "total_count": totalCount
        ])
    }
    
    private func handlePerformAction(body: Data?) -> HTTPResponse {
        guard let params = parseJSON(body),
              let appName = params["app_name"] as? String else {
            return HTTPResponse(status: 400, body: ["error": "Missing app_name"])
        }
        let role = params["role"] as? String
        let title = params["title"] as? String
        let action = params["action_name"] as? String ?? (kAXPressAction as String)
        let windowIndex = params["window_index"] as? Int ?? 0
        
        let success = axService.performAction(appName: appName, role: role, title: title, action: action, windowIndex: windowIndex)
        
        if success {
            return HTTPResponse(status: 200, body: ["success": true, "action": action])
        } else {
            return HTTPResponse(status: 400, body: ["success": false, "error": "Action failed or element not found"])
        }
    }
    
    private func handleSetValue(body: Data?) -> HTTPResponse {
        guard let params = parseJSON(body),
              let appName = params["app_name"] as? String,
              let value = params["value"] as? String else {
            return HTTPResponse(status: 400, body: ["error": "Missing app_name or value"])
        }
        let role = params["role"] as? String
        let title = params["title"] as? String
        let windowIndex = params["window_index"] as? Int ?? 0
        
        let success = axService.setValue(appName: appName, role: role, title: title, value: value, windowIndex: windowIndex)
        
        if success {
            return HTTPResponse(status: 200, body: ["success": true])
        } else {
            return HTTPResponse(status: 400, body: ["success": false, "error": "Set value failed or element not found"])
        }
    }
    
    private func handleGetFocused() -> HTTPResponse {
        guard let element = axService.getFocusedElement() else {
            return HTTPResponse(status: 200, body: ["element": NSNull()])
        }
        return HTTPResponse(status: 200, body: ["element": encodeElement(element)])
    }
    
    private func handleGetElementAt(body: Data?) -> HTTPResponse {
        guard let params = parseJSON(body),
              let x = (params["x"] as? NSNumber)?.floatValue,
              let y = (params["y"] as? NSNumber)?.floatValue else {
            return HTTPResponse(status: 400, body: ["error": "Missing x or y"])
        }
        
        guard let element = axService.getElementAtPosition(x: x, y: y) else {
            return HTTPResponse(status: 200, body: ["element": NSNull()])
        }
        return HTTPResponse(status: 200, body: ["element": encodeElement(element)])
    }
    
    private func handleFindElements(body: Data?) -> HTTPResponse {
        guard let params = parseJSON(body),
              let appName = params["app_name"] as? String else {
            return HTTPResponse(status: 400, body: ["error": "Missing app_name"])
        }
        let role = params["role"] as? String
        let title = params["title"] as? String
        let maxDepth = params["max_depth"] as? Int ?? 5
        let windowIndex = params["window_index"] as? Int ?? 0
        let maxCount = params["max_count"] as? Int ?? 50
        
        guard var elements = axService.getFlatElements(appName: appName, maxDepth: maxDepth, windowIndex: windowIndex) else {
            return HTTPResponse(status: 404, body: ["error": "App or window not found: \(appName)"])
        }
        
        // 过滤
        if let role = role, !role.isEmpty {
            let lowerRole = role.lowercased()
            elements = elements.filter { $0.role.lowercased().contains(lowerRole) }
        }
        if let title = title, !title.isEmpty {
            let lowerTitle = title.lowercased()
            elements = elements.filter {
                $0.title.lowercased().contains(lowerTitle)
                || $0.label.lowercased().contains(lowerTitle)
                || $0.description.lowercased().contains(lowerTitle)
                || $0.identifier.lowercased().contains(lowerTitle)
                || $0.value.lowercased().contains(lowerTitle)
            }
        }
        
        let totalMatched = elements.count
        if elements.count > maxCount {
            elements = Array(elements.prefix(maxCount))
        }
        
        let encoded = elements.map { encodeElement($0) }
        return HTTPResponse(status: 200, body: [
            "elements": encoded,
            "count": encoded.count,
            "total_matched": totalMatched
        ])
    }
    
    // MARK: - Encoding Helpers
    
    private nonisolated func encodeElement(_ elem: AXElementInfo) -> [String: Any] {
        var dict: [String: Any] = [
            "role": elem.role,
            "role_description": elem.roleDescription,
            "title": elem.title,
            "value": elem.value,
            "label": elem.label,
            "description": elem.description,
            "enabled": elem.enabled,
            "focused": elem.focused,
            "identifier": elem.identifier,
            "subrole": elem.subrole
        ]
        if let p = elem.position { dict["position"] = ["x": p.x, "y": p.y] }
        if let s = elem.size { dict["size"] = ["width": s.width, "height": s.height] }
        if let c = elem.center { dict["center"] = ["x": c.x, "y": c.y] }
        if let children = elem.children, !children.isEmpty {
            dict["children"] = children.map { encodeElement($0) }
        }
        return dict
    }
    
    // MARK: - HTTP Response
    
    private nonisolated func sendResponse(connection: NWConnection, status: Int, body: Any) {
        let statusText: String
        switch status {
        case 200: statusText = "OK"
        case 400: statusText = "Bad Request"
        case 404: statusText = "Not Found"
        case 500: statusText = "Internal Server Error"
        default:  statusText = "Unknown"
        }
        
        var jsonData: Data
        do {
            jsonData = try JSONSerialization.data(withJSONObject: body, options: [.sortedKeys])
        } catch {
            jsonData = "{\"error\": \"JSON serialization failed\"}".data(using: .utf8)!
        }
        
        let header = """
        HTTP/1.1 \(status) \(statusText)\r
        Content-Type: application/json; charset=utf-8\r
        Content-Length: \(jsonData.count)\r
        Access-Control-Allow-Origin: *\r
        Access-Control-Allow-Methods: GET, POST, OPTIONS\r
        Access-Control-Allow-Headers: Content-Type\r
        Connection: close\r
        \r
        
        """
        
        var responseData = header.data(using: .utf8)!
        responseData.append(jsonData)
        
        connection.send(content: responseData, completion: .contentProcessed { _ in
            connection.cancel()
        })
    }
    
    // MARK: - JSON Parsing
    
    private nonisolated func parseJSON(_ data: Data?) -> [String: Any]? {
        guard let data = data, !data.isEmpty else { return nil }
        return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    }
}
