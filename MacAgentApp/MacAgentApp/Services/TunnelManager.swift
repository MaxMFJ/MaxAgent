import Foundation
import Combine
import AppKit
import CoreImage.CIFilterBuiltins

@MainActor
class TunnelManager: ObservableObject {
    static let shared = TunnelManager()
    
    @Published var isTunnelRunning = false
    @Published var tunnelURL: String = ""
    @Published var authToken: String = ""
    @Published var isAuthEnabled = false
    @Published var tunnelLogs: [LogEntry] = []
    @Published var connectedClients: [ConnectedClient] = []
    @Published var qrCodeImage: NSImage?
    
    private var tunnelProcess: Process?
    private var outputPipe: Pipe?
    private var errorPipe: Pipe?
    private var checkConnectionTask: Task<Void, Never>?
    
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
    }
    
    // MARK: - Cloudflared Installation Check
    
    /// 检查 cloudflared 是否已安装。Mac App 从 Finder 启动时 PATH 不包含 Homebrew，需直接检查已知路径。
    func checkCloudflaredInstalled() -> Bool {
        return getCloudflaredPath() != nil
    }
    
    /// 获取 cloudflared 可执行文件路径。优先检查 Homebrew 等常用安装路径，避免依赖 PATH。
    func getCloudflaredPath() -> String? {
        // 按优先级检查已知安装路径（Mac App GUI 启动时 PATH 通常不包含 Homebrew）
        let possiblePaths = [
            "/opt/homebrew/bin/cloudflared",      // Apple Silicon Homebrew
            "/usr/local/bin/cloudflared",         // Intel Homebrew
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
        process.arguments = ["tunnel", "--url", "http://localhost:8765"]
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
        
        isTunnelRunning = false
        tunnelURL = ""
        qrCodeImage = nil
        connectedClients = []
        
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
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8765/auth/generate-token")!)
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
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8765/auth/disable")!)
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
            let url = URL(string: "http://127.0.0.1:8765/connections")!
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
}
