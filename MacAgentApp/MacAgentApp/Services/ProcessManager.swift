import Foundation
import Combine

@MainActor
class ProcessManager: ObservableObject {
    static let shared = ProcessManager()
    
    @Published var isBackendRunning = false {
        didSet {
            if isBackendRunning && !oldValue {
                onBackendStarted?()
                startLogPolling()
            } else if !isBackendRunning && oldValue {
                stopLogPolling()
            }
        }
    }
    @Published var isOllamaRunning = false
    @Published var backendLogs: [LogEntry] = []
    @Published var ollamaLogs: [LogEntry] = []
    
    var onBackendStarted: (() -> Void)?
    
    private var backendProcess: Process?
    private var ollamaProcess: Process?
    private var backendPipe: Pipe?
    private var ollamaPipe: Pipe?
    
    private let maxLogEntries = 1000
    
    // 日志轮询
    private var logPollingTask: Task<Void, Never>?
    private var statusPollingTask: Task<Void, Never>?
    private var lastLogPosition: UInt64 = 0
    private var logFilePath: String?
    
    struct LogEntry: Identifiable {
        let id = UUID()
        let timestamp: Date
        let message: String
        let level: LogLevel
        
        enum LogLevel: String {
            case info = "INFO"
            case warning = "WARNING"
            case error = "ERROR"
            case debug = "DEBUG"
        }
    }
    
    private init() {
        checkServicesStatus()
        startStatusPolling()
    }

    /// 定期轮询服务状态，避免 health 偶尔超时导致误显示「已停止」
    private func startStatusPolling() {
        statusPollingTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 15_000_000_000)  // 每 15 秒
                await checkBackendStatus()
                await checkOllamaStatus()
            }
        }
    }
    
    // MARK: - Log Polling (for externally started backend)
    
    private func startLogPolling() {
        stopLogPolling()
        
        logPollingTask = Task {
            while !Task.isCancelled {
                await pollBackendLogs()
                try? await Task.sleep(nanoseconds: 1_000_000_000) // 1 second
            }
        }
    }
    
    private func stopLogPolling() {
        logPollingTask?.cancel()
        logPollingTask = nil
    }
    
    private var lastLogIndex = 0
    
    private func pollBackendLogs() async {
        // 从后端 API 获取日志
        do {
            let url = URL(string: "http://127.0.0.1:8765/logs?limit=100&since_index=\(lastLogIndex)")!
            var request = URLRequest(url: url)
            request.timeoutInterval = 3
            
            let (data, response) = try await URLSession.shared.data(for: request)
            
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                if let logsData = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let logs = logsData["logs"] as? [[String: Any]],
                   let nextIndex = logsData["next_index"] as? Int {
                    
                    for log in logs {
                        let message = log["message"] as? String ?? ""
                        let level = log["level"] as? String ?? "INFO"
                        
                        // 避免重复添加
                        if !message.isEmpty {
                            addLog(to: &backendLogs, message: message, level: parseLevel(level))
                        }
                    }
                    
                    lastLogIndex = nextIndex
                }
            }
        } catch {
            // API 不存在或失败，静默处理
        }
    }
    
    private func parseLevel(_ level: String) -> LogEntry.LogLevel {
        switch level.uppercased() {
        case "ERROR": return .error
        case "WARNING", "WARN": return .warning
        case "DEBUG": return .debug
        default: return .info
        }
    }
    
    // MARK: - Status Check
    
    func checkServicesStatus() {
        Task {
            await checkBackendStatus()
            await checkOllamaStatus()
        }
    }
    
    private func checkBackendStatus() async {
        do {
            let url = URL(string: "http://127.0.0.1:8765/health")!
            var request = URLRequest(url: url)
            request.timeoutInterval = 2
            let (_, response) = try await URLSession.shared.data(for: request)
            if let httpResponse = response as? HTTPURLResponse {
                let wasRunning = isBackendRunning
                isBackendRunning = httpResponse.statusCode == 200
                
                // 如果后端正在运行但之前没有运行，开始轮询日志
                if isBackendRunning && !wasRunning {
                    startLogPolling()
                    addLog(to: &backendLogs, message: "检测到后端服务已运行", level: .info)
                }
            }
        } catch {
            isBackendRunning = backendProcess?.isRunning ?? false
        }
    }
    
    private func checkOllamaStatus() async {
        do {
            let url = URL(string: "http://127.0.0.1:11434/api/tags")!
            let (_, response) = try await URLSession.shared.data(from: url)
            if let httpResponse = response as? HTTPURLResponse {
                isOllamaRunning = httpResponse.statusCode == 200
            }
        } catch {
            isOllamaRunning = false
        }
    }
    
    // MARK: - Backend Management
    
    /// 获取可写的 data 目录（打包后 Bundle 内 data 只读，需使用 Application Support）
    private func getWritableDataDir(backendPath: String) -> String? {
        let bundleDataPath = (backendPath as NSString).appendingPathComponent("data")
        // 若 bundle 内 data 可写，直接使用
        if FileManager.default.isWritableFile(atPath: bundleDataPath) {
            return nil  // 使用默认路径
        }
        // 使用 Application Support，首次启动时从 bundle 复制 data 模板
        guard let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else { return nil }
        let appSupport = support.appendingPathComponent("com.macagent.app", isDirectory: true)
        let dataDir = appSupport.appendingPathComponent("backend_data", isDirectory: true)
        try? FileManager.default.createDirectory(at: dataDir, withIntermediateDirectories: true)
        // 首次：若 backend_data 为空，从 bundle 复制 data 内容
        let contents = (try? FileManager.default.contentsOfDirectory(atPath: dataDir.path)) ?? []
        if contents.isEmpty, FileManager.default.fileExists(atPath: bundleDataPath) {
            copyDataFromBundle(from: bundleDataPath, to: dataDir.path)
        }
        return dataDir.path
    }
    
    private func copyDataFromBundle(from srcPath: String, to dstPath: String) {
        guard let items = try? FileManager.default.contentsOfDirectory(atPath: srcPath) else { return }
        for item in items {
            let src = (srcPath as NSString).appendingPathComponent(item)
            let dst = (dstPath as NSString).appendingPathComponent(item)
            try? FileManager.default.copyItem(atPath: src, toPath: dst)
        }
    }
    
    func startBackend() {
        guard !isBackendRunning else { return }
        
        addLog(to: &backendLogs, message: "Starting backend service...", level: .info)
        
        let backendPath = getBackendPath()
        guard FileManager.default.fileExists(atPath: backendPath) else {
            addLog(to: &backendLogs, message: "Backend not found at: \(backendPath)", level: .error)
            return
        }
        
        let startScript = (backendPath as NSString).appendingPathComponent("start.sh")
        guard FileManager.default.fileExists(atPath: startScript) else {
            addLog(to: &backendLogs, message: "start.sh not found at: \(backendPath)", level: .error)
            return
        }
        
        var env = ProcessInfo.processInfo.environment
        if let dataDir = getWritableDataDir(backendPath: backendPath) {
            env["MACAGENT_DATA_DIR"] = dataDir
        }
        
        // 确保 PATH 包含 Homebrew 等常用路径，否则 cliclick/python3 等工具找不到
        let extraPaths = ["/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin", "/usr/local/sbin"]
        let currentPath = env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        let pathComponents = Set(currentPath.components(separatedBy: ":"))
        let missingPaths = extraPaths.filter { !pathComponents.contains($0) && FileManager.default.fileExists(atPath: $0) }
        if !missingPaths.isEmpty {
            env["PATH"] = (missingPaths + [currentPath]).joined(separator: ":")
        }
        
        let process = Process()
        let pipe = Pipe()
        let errorPipe = Pipe()
        
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = ["-c", "cd '\(backendPath)' && bash start.sh"]
        process.standardOutput = pipe
        process.standardError = errorPipe
        process.environment = env
        
        // 读取标准输出
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if let output = String(data: data, encoding: .utf8), !output.isEmpty {
                Task { @MainActor [weak self] in
                    guard let self = self else { return }
                    self.parseAndAddLog(output, to: &self.backendLogs)
                }
            }
        }
        
        // 读取错误输出
        errorPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if let output = String(data: data, encoding: .utf8), !output.isEmpty {
                Task { @MainActor [weak self] in
                    guard let self = self else { return }
                    self.parseAndAddLog(output, to: &self.backendLogs, defaultLevel: .error)
                }
            }
        }
        
        process.terminationHandler = { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self = self else { return }
                self.isBackendRunning = false
                self.addLog(to: &self.backendLogs, message: "Backend service stopped", level: .warning)
            }
        }
        
        do {
            try process.run()
            backendProcess = process
            backendPipe = pipe
            
            // 等待一秒后检查状态
            Task {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                await checkBackendStatus()
            }
            // 启动/停止后端后提示重启 App，避免状态不一致或意外退出导致用户无感知
            DispatchQueue.main.async {
                NotificationCenter.default.post(name: .backendSettingDidChange, object: nil)
            }
        } catch {
            addLog(to: &backendLogs, message: "Failed to start backend: \(error.localizedDescription)", level: .error)
        }
    }
    
    func stopBackend() {
        addLog(to: &backendLogs, message: "Stopping backend service...", level: .info)
        
        // 仅当本次是由本 App 启动的后端时，才按端口杀进程，避免误杀用户在其他终端/方式启动的服务
        let wasStartedByApp = (backendProcess != nil)
        
        backendProcess?.terminate()
        backendProcess = nil
        isBackendRunning = false
        addLog(to: &backendLogs, message: "Backend service stopped", level: .info)
        
        // 提示重启 App，避免「停止后台导致程序关闭」后用户无感知，可自动重新打开
        DispatchQueue.main.async {
            NotificationCenter.default.post(name: .backendSettingDidChange, object: nil)
        }
        guard wasStartedByApp else { return }
        // 由本 App 启动时，必须按端口杀掉实际占用 8765 的子进程（如 python main.py），
        // 否则子进程会继续运行，状态轮询会再次显示「已运行」
        Task.detached(priority: .userInitiated) {
            let killTask = Process()
            killTask.executableURL = URL(fileURLWithPath: "/bin/bash")
            killTask.arguments = ["-c", "lsof -ti:8765 | xargs kill -9 2>/dev/null || true"]
            try? killTask.run()
            killTask.waitUntilExit()
        }
    }
    
    // MARK: - Ollama Management
    
    func startOllama() {
        guard !isOllamaRunning else { return }
        
        addLog(to: &ollamaLogs, message: "Starting Ollama...", level: .info)
        
        // 检查 Ollama 是否安装
        let checkProcess = Process()
        checkProcess.executableURL = URL(fileURLWithPath: "/usr/bin/which")
        checkProcess.arguments = ["ollama"]
        let checkPipe = Pipe()
        checkProcess.standardOutput = checkPipe
        
        do {
            try checkProcess.run()
            checkProcess.waitUntilExit()
            
            if checkProcess.terminationStatus != 0 {
                addLog(to: &ollamaLogs, message: "Ollama not installed. Please install from https://ollama.ai", level: .error)
                return
            }
        } catch {
            addLog(to: &ollamaLogs, message: "Failed to check Ollama: \(error.localizedDescription)", level: .error)
            return
        }
        
        let process = Process()
        let pipe = Pipe()
        let errorPipe = Pipe()
        
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = ["-c", "ollama serve"]
        process.standardOutput = pipe
        process.standardError = errorPipe
        
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if let output = String(data: data, encoding: .utf8), !output.isEmpty {
                Task { @MainActor [weak self] in
                    guard let self = self else { return }
                    self.parseAndAddLog(output, to: &self.ollamaLogs)
                }
            }
        }
        
        errorPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if let output = String(data: data, encoding: .utf8), !output.isEmpty {
                Task { @MainActor [weak self] in
                    guard let self = self else { return }
                    self.parseAndAddLog(output, to: &self.ollamaLogs)
                }
            }
        }
        
        process.terminationHandler = { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self = self else { return }
                self.isOllamaRunning = false
                self.addLog(to: &self.ollamaLogs, message: "Ollama stopped", level: .warning)
            }
        }
        
        do {
            try process.run()
            ollamaProcess = process
            ollamaPipe = pipe
            
            Task {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                await checkOllamaStatus()
            }
        } catch {
            addLog(to: &ollamaLogs, message: "Failed to start Ollama: \(error.localizedDescription)", level: .error)
        }
    }
    
    func stopOllama() {
        addLog(to: &ollamaLogs, message: "Stopping Ollama...", level: .info)
        
        ollamaProcess?.terminate()
        ollamaProcess = nil
        
//        // 异步杀掉进程，避免阻塞主线程
//        Task.detached {
//            let killTask = Process()
//            killTask.executableURL = URL(fileURLWithPath: "/bin/bash")
//            killTask.arguments = ["-c", "pkill -f 'ollama serve' 2>/dev/null || true"]
//            try? killTask.run()
//            killTask.waitUntilExit()
//        }
        
        isOllamaRunning = false
        addLog(to: &ollamaLogs, message: "Ollama stopped", level: .info)
    }
    
    // MARK: - Helpers
    
    /// 返回 backend 目录路径。Debug 优先用项目 backend，Archive 用 Bundle 内置
    private func getBackendPath() -> String {
        let inDerivedData = Bundle.main.bundlePath.contains("DerivedData")
        
        // 辅助函数：检查路径是否包含有效的 backend
        func isValidBackendPath(_ path: String) -> Bool {
            let startScript = (path as NSString).appendingPathComponent("start.sh")
            return FileManager.default.fileExists(atPath: startScript)
        }
        
        // 辅助函数：从指定目录开始向上查找 backend
        func findBackendFromPath(_ startPath: String, maxDepth: Int = 5) -> String? {
            var currentPath = startPath
            for _ in 0..<maxDepth {
                // 检查当前目录下的 backend
                let backendPath = (currentPath as NSString).appendingPathComponent("backend")
                if isValidBackendPath(backendPath) {
                    return backendPath
                }
                // 向上一级
                let parent = (currentPath as NSString).deletingLastPathComponent
                if parent == currentPath { break }  // 已到根目录
                currentPath = parent
            }
            return nil
        }
        
        // 优先检查 App Bundle 内 Resources/backend（Debug 通过 symlink、Release 通过 copy）
        if let resourcesPath = Bundle.main.resourcePath {
            let bundledBackend = (resourcesPath as NSString).appendingPathComponent("backend")
            if isValidBackendPath(bundledBackend) {
                return bundledBackend
            }
        }
        
        // Debug 模式回退：Copy Backend 脚本可能未执行（首次构建等），尝试从源码位置查找
        if inDerivedData {
            // 1. 从当前工作目录向上查找
            let cwd = FileManager.default.currentDirectoryPath
            if let found = findBackendFromPath(cwd) {
                return found
            }
            
            // 2. 从 App Bundle 位置向上查找
            if let found = findBackendFromPath(Bundle.main.bundlePath) {
                return found
            }
            
            // 3. 搜索 Desktop 下所有一级子目录中的 MacAgent/backend
            let home = FileManager.default.homeDirectoryForCurrentUser.path
            let desktopPath = home + "/Desktop"
            if let desktopContents = try? FileManager.default.contentsOfDirectory(atPath: desktopPath) {
                for item in desktopContents {
                    let candidate = desktopPath + "/" + item + "/MacAgent/backend"
                    if isValidBackendPath(candidate) {
                        return candidate
                    }
                }
                // 也检查 Desktop/MacAgent/backend（直接在桌面的情况）
                let directCandidate = desktopPath + "/MacAgent/backend"
                if isValidBackendPath(directCandidate) {
                    return directCandidate
                }
            }
            
            // 4. 其他常用位置
            let fallbackCandidates = [
                home + "/Documents/GitHub/MacAgent/backend",
                home + "/Projects/MacAgent/backend",
                home + "/Developer/MacAgent/backend",
            ]
            for path in fallbackCandidates {
                if isValidBackendPath(path) {
                    return path
                }
            }
        }
        
        // 与 .app 同级的 backend（非 DerivedData 场景）
        if let found = findBackendFromPath(Bundle.main.bundlePath) {
            return found
        }
        
        // 兜底
        return (Bundle.main.resourcePath ?? "") + "/backend"
    }
    
    private func addLog(to logs: inout [LogEntry], message: String, level: LogEntry.LogLevel) {
        let entry = LogEntry(timestamp: Date(), message: message, level: level)
        logs.append(entry)
        
        // 限制日志数量
        if logs.count > maxLogEntries {
            logs.removeFirst(logs.count - maxLogEntries)
        }
    }
    
    private func parseAndAddLog(_ output: String, to logs: inout [LogEntry], defaultLevel: LogEntry.LogLevel = .info) {
        let lines = output.components(separatedBy: .newlines).filter { !$0.isEmpty }
        
        for line in lines {
            var level = defaultLevel
            
            if line.contains("ERROR") {
                level = .error
            } else if line.contains("WARNING") {
                level = .warning
            } else if line.contains("DEBUG") {
                level = .debug
            } else if line.contains("INFO") {
                level = .info
            }
            
            addLog(to: &logs, message: line, level: level)
        }
    }
    
    func clearLogs(for service: String) {
        if service == "backend" {
            backendLogs.removeAll()
        } else if service == "ollama" {
            ollamaLogs.removeAll()
        }
    }

    // MARK: - Duck Backend

    /// Start the backend in Duck mode on the specified port.
    /// The backend process reads DUCK_MODE=1 / DUCK_PORT / DUCK_CONFIG_PATH from env.
    func startDuckBackend(port: Int, config: DuckConfig) {
        guard !isBackendRunning else {
            addLog(to: &backendLogs, message: "[Duck] Backend already running, skipping duck backend start", level: .warning)
            return
        }

        addLog(to: &backendLogs, message: "[Duck] Starting duck backend on port \(port)…", level: .info)

        let backendPath = getBackendPath()
        guard FileManager.default.fileExists(atPath: backendPath) else {
            addLog(to: &backendLogs, message: "[Duck] Backend not found at: \(backendPath)", level: .error)
            return
        }

        let startScript = (backendPath as NSString).appendingPathComponent("start.sh")
        guard FileManager.default.fileExists(atPath: startScript) else {
            addLog(to: &backendLogs, message: "[Duck] start.sh not found at: \(backendPath)", level: .error)
            return
        }

        // Write duck config to a temporary path so the backend can read it
        let configPath = (backendPath as NSString).appendingPathComponent("duck_runtime_config.json")
        if let data = try? JSONEncoder().encode(config) {
            try? data.write(to: URL(fileURLWithPath: configPath))
        }

        var env = ProcessInfo.processInfo.environment
        if let dataDir = getWritableDataDir(backendPath: backendPath) {
            env["MACAGENT_DATA_DIR"] = dataDir
        }
        env["DUCK_MODE"] = "1"
        env["DUCK_PORT"] = "\(port)"
        env["DUCK_CONFIG_PATH"] = configPath
        env["DUCK_MAIN_AGENT_URL"] = config.mainAgentUrl
        env["DUCK_TOKEN"] = config.token
        env["DUCK_ID"] = config.duckId
        env["DUCK_TYPE"] = config.duckType
        env["DUCK_PERMISSIONS"] = config.permissions.joined(separator: ",")

        // Ensure Homebrew paths
        let extraPaths = ["/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin", "/usr/local/sbin"]
        let currentPath = env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        let pathComponents = Set(currentPath.components(separatedBy: ":"))
        let missingPaths = extraPaths.filter { !pathComponents.contains($0) && FileManager.default.fileExists(atPath: $0) }
        if !missingPaths.isEmpty {
            env["PATH"] = (missingPaths + [currentPath]).joined(separator: ":")
        }

        let process = Process()
        let pipe = Pipe()
        let errorPipe = Pipe()

        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = ["-c", "cd '\(backendPath)' && bash start.sh"]
        process.standardOutput = pipe
        process.standardError = errorPipe
        process.environment = env

        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if let output = String(data: data, encoding: .utf8), !output.isEmpty {
                Task { @MainActor [weak self] in
                    guard let self = self else { return }
                    self.parseAndAddLog(output, to: &self.backendLogs)
                }
            }
        }

        errorPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if let output = String(data: data, encoding: .utf8), !output.isEmpty {
                Task { @MainActor [weak self] in
                    guard let self = self else { return }
                    self.parseAndAddLog(output, to: &self.backendLogs, defaultLevel: .error)
                }
            }
        }

        process.terminationHandler = { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self = self else { return }
                self.isBackendRunning = false
                self.addLog(to: &self.backendLogs, message: "[Duck] Duck backend stopped", level: .warning)
            }
        }

        do {
            try process.run()
            backendProcess = process
            backendPipe = pipe
            Task {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                await checkDuckBackendStatus(port: port)
            }
        } catch {
            addLog(to: &backendLogs, message: "[Duck] Failed to start duck backend: \(error.localizedDescription)", level: .error)
        }
    }

    private func checkDuckBackendStatus(port: Int) async {
        do {
            let url = URL(string: "http://127.0.0.1:\(port)/health")!
            var request = URLRequest(url: url)
            request.timeoutInterval = 2
            let (_, response) = try await URLSession.shared.data(for: request)
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                isBackendRunning = true
                addLog(to: &backendLogs, message: "[Duck] Duck backend running on port \(port)", level: .info)
            }
        } catch {
            addLog(to: &backendLogs, message: "[Duck] Duck backend health check failed on port \(port): \(error.localizedDescription)", level: .warning)
        }
    }
}

extension Notification.Name {
    /// 启动/停止后端后发送，用于提示用户并自动重启 App，避免程序关闭后用户无感知
    static let backendSettingDidChange = Notification.Name("BackendSettingDidChange")
}
