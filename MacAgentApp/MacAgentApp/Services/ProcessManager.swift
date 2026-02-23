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
    
    func startBackend() {
        guard !isBackendRunning else { return }
        
        addLog(to: &backendLogs, message: "Starting backend service...", level: .info)
        
        let backendPath = getBackendPath()
        guard FileManager.default.fileExists(atPath: backendPath) else {
            addLog(to: &backendLogs, message: "Backend not found at: \(backendPath)", level: .error)
            return
        }
        
        let process = Process()
        let pipe = Pipe()
        let errorPipe = Pipe()
        
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = ["-c", "cd '\(backendPath)' && ./start.sh"]
        process.standardOutput = pipe
        process.standardError = errorPipe
        process.environment = ProcessInfo.processInfo.environment
        
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
        } catch {
            addLog(to: &backendLogs, message: "Failed to start backend: \(error.localizedDescription)", level: .error)
        }
    }
    
    func stopBackend() {
        addLog(to: &backendLogs, message: "Stopping backend service...", level: .info)
        
        // 先尝试正常终止
        backendProcess?.terminate()
        backendProcess = nil
        
        // 异步杀掉可能存在的进程，避免阻塞主线程
//        Task.detached {
//            let killTask = Process()
//            killTask.executableURL = URL(fileURLWithPath: "/bin/bash")
//            killTask.arguments = ["-c", "lsof -ti:8765 | xargs kill -9 2>/dev/null || true"]
//            try? killTask.run()
//            killTask.waitUntilExit()
//        }
        
        isBackendRunning = false
        addLog(to: &backendLogs, message: "Backend service stopped", level: .info)
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
    
    private func getBackendPath() -> String {
        // 尝试找到后端路径
        let possiblePaths = [
            // 开发路径
            FileManager.default.currentDirectoryPath + "/../backend",
            // 相对于应用的路径
            Bundle.main.bundlePath + "/../../../backend",
            // 固定路径（用户可以自定义）
            NSHomeDirectory() + "/Desktop/未命名文件夹/MacAgent/backend"
        ]
        
        for path in possiblePaths {
            let startScript = (path as NSString).appendingPathComponent("start.sh")
            if FileManager.default.fileExists(atPath: startScript) {
                return path
            }
        }
        
        // 默认返回最后一个
        return possiblePaths.last!
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
}
