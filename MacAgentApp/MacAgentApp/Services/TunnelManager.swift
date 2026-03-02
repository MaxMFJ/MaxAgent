import Foundation
import Combine
import AppKit
import CoreImage.CIFilterBuiltins

@MainActor
class TunnelManager: ObservableObject {
    static let shared = TunnelManager()

    /// 与 tunnel_monitor / 后端统一的端口
    static let backendPort = 8765       // 后端服务
    static let cloudflaredMetricsPort = 4040  // cloudflared metrics API
    
    @Published var isTunnelRunning = false
    @Published var tunnelURL: String = ""
    @Published var authToken: String = ""
    @Published var isAuthEnabled = false
    @Published var tunnelLogs: [LogEntry] = []
    @Published var connectedClients: [ConnectedClient] = []
    @Published var qrCodeImage: NSImage?
    
    // ── 新增：后端 Tunnel 生命周期状态 ──
    @Published var autoStartEnabled: Bool = false
    @Published var isLanOnly: Bool = false
    @Published var consecutiveFailures: Int = 0
    @Published var totalRestarts: Int = 0
    @Published var currentBackoffSeconds: Int = 0
    @Published var backoffUntil: String? = nil  // ISO 格式
    @Published var lanIP: String = ""
    @Published var lanWSUrl: String = ""
    @Published var lanHTTPUrl: String = ""
    @Published var recentEvents: [[String: String]] = []
    
    private var tunnelProcess: Process?
    private var outputPipe: Pipe?
    private var errorPipe: Pipe?
    private var checkConnectionTask: Task<Void, Never>?
    private var detectExternalTask: Task<Void, Never>?
    private var backendStatusTask: Task<Void, Never>?
    /// 外部 tunnel 检测连续失败次数，用于 control stream 断开后及时显示「已停止」
    private var externalTunnelFailureCount = 0
    
    struct LogEntry: Identifiable {
        let id = UUID()
        let timestamp: Date
        let message: String
        let level: LogLevel
        
        enum LogLevel {
            case info, warning, error, debug
        }
    }
    
    struct ConnectedClient: Identifiable {
        let id: String
        let clientType: String
        let connectedAt: Date
    }
    
    private init() {
        loadAuthToken()
        startExternalTunnelDetection()
        startBackendStatusPolling()
        loadAutoStartConfig()
    }

    // MARK: - 检测外部启动的 Tunnel（tunnel_monitor 脚本、Agent 等）

    /// 定期检测是否有外部启动的 cloudflared，并更新状态与日志
    private func startExternalTunnelDetection() {
        detectExternalTask?.cancel()
        detectExternalTask = Task {
            while !Task.isCancelled {
                // 仅当本 App 未启动 tunnel 时检测外部 tunnel
                if tunnelProcess == nil {
                    await detectExternallyRunningTunnel()
                }
                try? await Task.sleep(nanoseconds: 5_000_000_000)  // 每 5 秒
            }
        }
    }

    private func stopExternalTunnelDetection() {
        detectExternalTask?.cancel()
        detectExternalTask = nil
    }

    private func detectExternallyRunningTunnel() async {
        do {
            // cloudflared 使用 Prometheus metrics（非 JSON API），从 /metrics 解析 URL
            let url = URL(string: "http://127.0.0.1:\(Self.cloudflaredMetricsPort)/metrics")!
            var request = URLRequest(url: url)
            request.timeoutInterval = 2
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                await markExternalTunnelUnavailableIfRepeated()
                return
            }
            guard let metricsText = String(data: data, encoding: .utf8) else {
                await markExternalTunnelUnavailableIfRepeated()
                return
            }
            // 解析: cloudflared_tunnel_user_hostnames_counts{userHostname="https://xxx.trycloudflare.com"} 1
            if let tunnelUrl = Self.parseTunnelURLFromMetrics(metricsText) {
                await MainActor.run {
                    externalTunnelFailureCount = 0
                    if !isTunnelRunning || tunnelURL != tunnelUrl {
                        isTunnelRunning = true
                        tunnelURL = tunnelUrl
                        generateQRCode()
                        startConnectionMonitoring()
                    }
                    loadExternalTunnelLogs()
                }
            } else {
                // ha_connections > 0 表示 tunnel 连接存在但可能还没分配 hostname
                if metricsText.contains("cloudflared_tunnel_ha_connections 1") {
                    // tunnel 存在但 URL 尚未注册，不标记失败
                    return
                }
                await markExternalTunnelUnavailableIfRepeated()
            }
        } catch {
            await markExternalTunnelUnavailableIfRepeated()
        }
    }

    /// 从 Prometheus metrics 文本中提取 trycloudflare.com URL
    static func parseTunnelURLFromMetrics(_ text: String) -> String? {
        // 匹配: cloudflared_tunnel_user_hostnames_counts{userHostname="https://xxx.trycloudflare.com"} 1
        let pattern = #"cloudflared_tunnel_user_hostnames_counts\{userHostname="(https://[^"]*trycloudflare\.com[^"]*)"\}"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              let range = Range(match.range(at: 1), in: text) else { return nil }
        return String(text[range])
    }

    /// 外部 tunnel 连续检测失败时置为「已停止」，避免 control stream 断开后仍显示运行中
    private func markExternalTunnelUnavailableIfRepeated() async {
        await MainActor.run {
            guard tunnelProcess == nil else { return }
            externalTunnelFailureCount += 1
            if externalTunnelFailureCount >= 2 && isTunnelRunning {
                isTunnelRunning = false
                tunnelURL = ""
                qrCodeImage = nil
                connectedClients = []
                checkConnectionTask?.cancel()
                checkConnectionTask = nil
                addLog("Tunnel 已断开（无法访问 cloudflared 状态），请重新启动", level: .warning)
            }
        }
    }

    private func loadExternalTunnelLogs() {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let logFiles = [
            "\(home)/cloudflared.log",
            "\(home)/tunnel_monitor.log"
        ]
        for path in logFiles {
            guard FileManager.default.fileExists(atPath: path),
                  let content = try? String(contentsOf: URL(fileURLWithPath: path), encoding: .utf8) else { continue }
            tunnelLogs.removeAll()
            let lines = content.components(separatedBy: .newlines).filter { !$0.isEmpty }.suffix(100)
            for line in lines {
                var level: LogEntry.LogLevel = .info
                if line.contains("ERR") || line.lowercased().contains("error") { level = .error }
                else if line.contains("WARN") || line.lowercased().contains("warning") { level = .warning }
                addLog(String(line), level: level)
            }
            break
        }
    }
    
    // MARK: - Cloudflared Installation Check
    
    /// 检查 cloudflared 是否已安装。Mac App 从 Finder 启动时 PATH 不包含 Homebrew，需直接检查已知路径。
    func checkCloudflaredInstalled() -> Bool {
        return getCloudflaredPath() != nil
    }
    
    /// 获取 cloudflared 可执行文件路径。优先检查 Homebrew 等常用安装路径，避免依赖 PATH。
    func getCloudflaredPath() -> String? {
        // 按优先级检查已知安装路径（Mac App GUI 启动时 PATH 通常不包含 Homebrew）
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let possiblePaths = [
            "/opt/homebrew/bin/cloudflared",      // Apple Silicon Homebrew
            "/usr/local/bin/cloudflared",         // Intel Homebrew
            "\(home)/bin/cloudflared",            // 用户手动安装
            "/opt/homebrew/Cellar/cloudflared/",  // Homebrew Cellar (需拼接版本/bin)
            "/usr/bin/cloudflared"
        ]
        
        for path in possiblePaths {
            if path.hasSuffix("/") {
                // 处理 Cellar 路径：查找最新版本的 bin/cloudflared
                if let versions = try? FileManager.default.contentsOfDirectory(atPath: path),
                   let latest = versions.sorted(by: >).first {
                    let binPath = path + latest + "/bin/cloudflared"
                    if FileManager.default.fileExists(atPath: binPath) {
                        return binPath
                    }
                }
            } else if FileManager.default.fileExists(atPath: path) {
                return path
            }
        }
        
        // 回退：使用 which，显式设置包含 Homebrew 的 PATH（GUI App 启动时 PATH 通常不包含 Homebrew）
        let homebrewPath = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = homebrewPath + (env["PATH"].map { ":" + $0 } ?? "")
        
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/which")
        process.arguments = ["cloudflared"]
        process.environment = env
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = Pipe()  // 忽略 stderr
        
        do {
            try process.run()
            process.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            if let path = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
               !path.isEmpty,
               FileManager.default.fileExists(atPath: path) {
                return path
            }
        } catch {}
        
        return nil
    }
    
    // MARK: - Tunnel Management
    
    func startTunnel() {
        guard !isTunnelRunning else {
            addLog("Tunnel is already running", level: .warning)
            return
        }
        
        guard let cloudflaredPath = getCloudflaredPath() else {
            addLog("cloudflared not found. Please install: brew install cloudflared", level: .error)
            return
        }
        
        addLog("Starting Cloudflare Tunnel...", level: .info)
        
        let process = Process()
        let outputPipe = Pipe()
        let errorPipe = Pipe()
        
        process.executableURL = URL(fileURLWithPath: cloudflaredPath)
        process.arguments = ["tunnel", "--url", "http://localhost:\(Self.backendPort)", "--metrics", "127.0.0.1:\(Self.cloudflaredMetricsPort)"]
        process.standardOutput = outputPipe
        process.standardError = errorPipe
        
        outputPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if let output = String(data: data, encoding: .utf8), !output.isEmpty {
                Task { @MainActor [weak self] in
                    self?.parseTunnelOutput(output)
                }
            }
        }
        
        errorPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if let output = String(data: data, encoding: .utf8), !output.isEmpty {
                Task { @MainActor [weak self] in
                    self?.parseTunnelOutput(output)
                }
            }
        }
        
        process.terminationHandler = { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.isTunnelRunning = false
                self?.tunnelURL = ""
                self?.qrCodeImage = nil
                self?.addLog("Tunnel stopped", level: .warning)
            }
        }
        
        do {
            try process.run()
            tunnelProcess = process
            self.outputPipe = outputPipe
            self.errorPipe = errorPipe
            isTunnelRunning = true
            
            startConnectionMonitoring()
        } catch {
            addLog("Failed to start tunnel: \(error.localizedDescription)", level: .error)
        }
    }
    
    func stopTunnel() {
        addLog("Stopping tunnel...", level: .info)
        
        checkConnectionTask?.cancel()
        checkConnectionTask = nil
        
        tunnelProcess?.terminate()
        tunnelProcess = nil
        outputPipe = nil
        errorPipe = nil

        // 若由 tunnel_monitor 等外部启动，也终止 cloudflared 进程
        if isTunnelRunning {
            let killTask = Process()
            killTask.executableURL = URL(fileURLWithPath: "/usr/bin/pkill")
            killTask.arguments = ["-f", "cloudflared"]
            try? killTask.run()
            killTask.waitUntilExit()
        }
        
        isTunnelRunning = false
        tunnelURL = ""
        qrCodeImage = nil
        connectedClients = []
        externalTunnelFailureCount = 0

        addLog("Tunnel stopped", level: .info)
    }
    
    private func parseTunnelOutput(_ output: String) {
        let lines = output.components(separatedBy: .newlines)
        
        for line in lines where !line.isEmpty {
            if line.contains(".trycloudflare.com") {
                if let range = line.range(of: "https://[a-z0-9-]+\\.trycloudflare\\.com", options: .regularExpression) {
                    let url = String(line[range])
                    tunnelURL = url
                    addLog("Tunnel URL: \(url)", level: .info)
                    generateQRCode()
                }
            }
            
            var level: LogEntry.LogLevel = .info
            if line.contains("ERR") || line.contains("error") {
                level = .error
            } else if line.contains("WARN") || line.contains("warning") {
                level = .warning
            } else if line.contains("DBG") || line.contains("debug") {
                level = .debug
            }
            
            addLog(line, level: level)
        }
    }
    
    // MARK: - Auth Token Management
    
    func generateAuthToken() {
        let token = generateSecureToken()
        authToken = token
        isAuthEnabled = true
        saveAuthToken()
        
        Task {
            await enableAuthOnBackend(token: token)
        }
        
        generateQRCode()
        addLog("New auth token generated", level: .info)
    }
    
    func disableAuth() {
        isAuthEnabled = false
        saveAuthToken()
        
        Task {
            await disableAuthOnBackend()
        }
        
        generateQRCode()
        addLog("Authentication disabled", level: .info)
    }
    
    private func generateSecureToken() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        return Data(bytes).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
    
    private func saveAuthToken() {
        UserDefaults.standard.set(authToken, forKey: "TunnelAuthToken")
        UserDefaults.standard.set(isAuthEnabled, forKey: "TunnelAuthEnabled")
    }
    
    private func loadAuthToken() {
        authToken = UserDefaults.standard.string(forKey: "TunnelAuthToken") ?? ""
        isAuthEnabled = UserDefaults.standard.bool(forKey: "TunnelAuthEnabled")
    }
    
    private func enableAuthOnBackend(token: String) async {
        do {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:\(Self.backendPort)/auth/generate-token")!)
            request.httpMethod = "POST"
            request.timeoutInterval = 5
            
            let (_, response) = try await URLSession.shared.data(for: request)
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                addLog("Auth enabled on backend", level: .info)
            }
        } catch {
            addLog("Failed to enable auth on backend: \(error.localizedDescription)", level: .warning)
        }
    }
    
    private func disableAuthOnBackend() async {
        do {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:\(Self.backendPort)/auth/disable")!)
            request.httpMethod = "POST"
            request.timeoutInterval = 5
            
            let (_, _) = try await URLSession.shared.data(for: request)
        } catch {}
    }
    
    // MARK: - QR Code Generation
    
    func generateQRCode() {
        guard !tunnelURL.isEmpty else {
            qrCodeImage = nil
            return
        }
        
        var connectionInfo: [String: String] = ["url": tunnelURL]
        if isAuthEnabled && !authToken.isEmpty {
            connectionInfo["token"] = authToken
        }
        
        guard let jsonData = try? JSONSerialization.data(withJSONObject: connectionInfo),
              let jsonString = String(data: jsonData, encoding: .utf8) else {
            return
        }
        
        let context = CIContext()
        let filter = CIFilter.qrCodeGenerator()
        
        filter.message = Data(jsonString.utf8)
        filter.correctionLevel = "M"
        
        guard let outputImage = filter.outputImage else { return }
        
        let scale = 10.0
        let scaledImage = outputImage.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        
        guard let cgImage = context.createCGImage(scaledImage, from: scaledImage.extent) else { return }
        
        qrCodeImage = NSImage(cgImage: cgImage, size: NSSize(width: 200, height: 200))
    }
    
    // MARK: - Connection Monitoring
    
    private func startConnectionMonitoring() {
        checkConnectionTask?.cancel()
        
        checkConnectionTask = Task {
            while !Task.isCancelled && isTunnelRunning {
                await fetchConnectedClients()
                try? await Task.sleep(nanoseconds: 5_000_000_000)
            }
        }
    }
    
    private func fetchConnectedClients() async {
        do {
            let url = URL(string: "http://127.0.0.1:\(Self.backendPort)/connections")!
            var request = URLRequest(url: url)
            request.timeoutInterval = 3
            
            let (data, response) = try await URLSession.shared.data(for: request)
            
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let byType = json["by_type"] as? [String: Int] {
                    
                    var clients: [ConnectedClient] = []
                    for (type, count) in byType {
                        for i in 0..<count {
                            clients.append(ConnectedClient(
                                id: "\(type)-\(i)",
                                clientType: type,
                                connectedAt: Date()
                            ))
                        }
                    }
                    connectedClients = clients
                }
            }
        } catch {}
    }
    
    // MARK: - Helpers
    
    private func addLog(_ message: String, level: LogEntry.LogLevel) {
        let entry = LogEntry(timestamp: Date(), message: message, level: level)
        tunnelLogs.append(entry)
        
        if tunnelLogs.count > 500 {
            tunnelLogs.removeFirst(tunnelLogs.count - 500)
        }
    }
    
    func clearLogs() {
        tunnelLogs.removeAll()
    }

    /// 刷新外部 tunnel 的日志（由 tunnel_monitor 启动时从 ~/cloudflared.log 读取）
    func refreshLogsIfExternal() {
        guard tunnelProcess == nil, isTunnelRunning else { return }
        loadExternalTunnelLogs()
    }
    
    func copyTunnelURL() {
        guard !tunnelURL.isEmpty else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(tunnelURL, forType: .string)
    }
    
    func copyConnectionInfo() {
        var info: [String: String] = ["url": tunnelURL]
        if isAuthEnabled && !authToken.isEmpty {
            info["token"] = authToken
        }
        
        if let jsonData = try? JSONSerialization.data(withJSONObject: info, options: .prettyPrinted),
           let jsonString = String(data: jsonData, encoding: .utf8) {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(jsonString, forType: .string)
        }
    }
    
    // MARK: - 后端 Tunnel API 集成
    
    /// 从后端 /tunnel/status 拉取全生命周期状态
    private func startBackendStatusPolling() {
        backendStatusTask?.cancel()
        backendStatusTask = Task {
            while !Task.isCancelled {
                await fetchBackendTunnelStatus()
                try? await Task.sleep(nanoseconds: 8_000_000_000)  // 每 8 秒
            }
        }
    }
    
    private func fetchBackendTunnelStatus() async {
        do {
            let url = URL(string: "http://127.0.0.1:\(Self.backendPort)/tunnel/status")!
            var request = URLRequest(url: url)
            request.timeoutInterval = 3
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { return }
            guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
            
            await MainActor.run {
                if let running = json["is_running"] as? Bool {
                    // 同步后端状态到前端（后端管理的 tunnel 优先）
                    if running != isTunnelRunning && tunnelProcess == nil {
                        isTunnelRunning = running
                    }
                }
                if let u = json["tunnel_url"] as? String, !u.isEmpty, tunnelProcess == nil {
                    if tunnelURL != u {
                        tunnelURL = u
                        generateQRCode()
                    }
                }
                isLanOnly = json["is_lan_only"] as? Bool ?? false
                consecutiveFailures = json["consecutive_failures"] as? Int ?? 0
                totalRestarts = json["total_restarts"] as? Int ?? 0
                currentBackoffSeconds = json["current_backoff_seconds"] as? Int ?? 0
                backoffUntil = json["backoff_until"] as? String
                
                if let lanInfo = json["lan_info"] as? [String: String] {
                    lanIP = lanInfo["ip"] ?? ""
                    lanWSUrl = lanInfo["ws_url"] ?? ""
                    lanHTTPUrl = lanInfo["http_url"] ?? ""
                }
                
                if let events = json["recent_events"] as? [[String: String]] {
                    recentEvents = events
                }
                
                if let autoStart = json["auto_start_enabled"] as? Bool {
                    if autoStart != autoStartEnabled {
                        autoStartEnabled = autoStart
                    }
                }
            }
        } catch {
            // 后端未运行时静默跳过
        }
    }
    
    /// 通过后端 API 启动 Tunnel
    func startTunnelViaBackend() {
        Task {
            do {
                var request = URLRequest(url: URL(string: "http://127.0.0.1:\(Self.backendPort)/tunnel/start")!)
                request.httpMethod = "POST"
                request.timeoutInterval = 30
                let (data, response) = try await URLSession.shared.data(for: request)
                if let http = response as? HTTPURLResponse, http.statusCode == 200,
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    if let url = json["url"] as? String, !url.isEmpty {
                        await MainActor.run {
                            tunnelURL = url
                            isTunnelRunning = true
                            generateQRCode()
                            startConnectionMonitoring()
                            addLog("通过后端启动 Tunnel: \(url)", level: .info)
                        }
                    } else {
                        await MainActor.run {
                            addLog("Tunnel 启动中，等待 URL 注册...", level: .info)
                        }
                    }
                }
            } catch {
                await MainActor.run {
                    addLog("后端启动 Tunnel 失败: \(error.localizedDescription)", level: .error)
                }
            }
        }
    }
    
    /// 通过后端 API 停止 Tunnel
    func stopTunnelViaBackend() {
        Task {
            do {
                var request = URLRequest(url: URL(string: "http://127.0.0.1:\(Self.backendPort)/tunnel/stop")!)
                request.httpMethod = "POST"
                request.timeoutInterval = 10
                let (_, _) = try await URLSession.shared.data(for: request)
                await MainActor.run {
                    isTunnelRunning = false
                    tunnelURL = ""
                    qrCodeImage = nil
                    addLog("通过后端停止 Tunnel", level: .info)
                }
            } catch {
                await MainActor.run {
                    addLog("后端停止 Tunnel 失败: \(error.localizedDescription)", level: .warning)
                }
            }
        }
    }
    
    /// 设置自动启动
    func setAutoStart(_ enabled: Bool) {
        autoStartEnabled = enabled
        saveAutoStartConfig()
        Task {
            do {
                var request = URLRequest(url: URL(string: "http://127.0.0.1:\(Self.backendPort)/tunnel/auto-start")!)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try? JSONSerialization.data(withJSONObject: ["enabled": enabled])
                request.timeoutInterval = 5
                let (_, _) = try await URLSession.shared.data(for: request)
            } catch {
                // 后端未运行时部分配置保存在本地
            }
        }
    }
    
    /// 复制局域网连接信息
    func copyLanInfo() {
        guard !lanWSUrl.isEmpty else { return }
        var info: [String: String] = ["ws_url": lanWSUrl, "http_url": lanHTTPUrl, "ip": lanIP]
        if isAuthEnabled && !authToken.isEmpty {
            info["token"] = authToken
        }
        if let jsonData = try? JSONSerialization.data(withJSONObject: info, options: .prettyPrinted),
           let jsonString = String(data: jsonData, encoding: .utf8) {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(jsonString, forType: .string)
        }
    }
    
    // MARK: - Auto Start Config Persistence (本地)
    
    private func loadAutoStartConfig() {
        autoStartEnabled = UserDefaults.standard.bool(forKey: "TunnelAutoStart")
    }
    
    private func saveAutoStartConfig() {
        UserDefaults.standard.set(autoStartEnabled, forKey: "TunnelAutoStart")
    }
}
