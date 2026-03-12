import Foundation
import Network

/// 集中管理所有端口配置，持久化到 UserDefaults
/// 启动时自动检测端口冲突并提示用户修改
@MainActor
class PortConfiguration: ObservableObject {
    static let shared = PortConfiguration()

    // MARK: - Published Port Values

    /// 后端 API/WebSocket 端口（主实例）
    @Published var backendPort: UInt16 {
        didSet { UserDefaults.standard.set(Int(backendPort), forKey: Keys.backendPort) }
    }
    /// Accessibility Bridge HTTP 端口
    @Published var axBridgePort: UInt16 {
        didSet { UserDefaults.standard.set(Int(axBridgePort), forKey: Keys.axBridgePort) }
    }
    /// IPC TCP 端口
    @Published var ipcPort: UInt16 {
        didSet { UserDefaults.standard.set(Int(ipcPort), forKey: Keys.ipcPort) }
    }
    /// Duck 分身后端起始端口
    @Published var duckStartPort: UInt16 {
        didSet { UserDefaults.standard.set(Int(duckStartPort), forKey: Keys.duckStartPort) }
    }

    // MARK: - Conflict State

    /// 端口冲突详情列表 (port, serviceName, conflictProcessName)
    @Published var conflicts: [PortConflict] = []
    @Published var showConflictAlert: Bool = false

    struct PortConflict: Identifiable {
        let id = UUID()
        let port: UInt16
        let serviceName: String
        let conflictProcess: String
    }

    // MARK: - Defaults

    nonisolated static let defaultBackendPort: UInt16 = 8769
    nonisolated static let defaultAXBridgePort: UInt16 = 5650
    nonisolated static let defaultIPCPort: UInt16 = 8767
    nonisolated static let defaultDuckStartPort: UInt16 = 8866

    // MARK: - UserDefaults Keys

    private enum Keys {
        static let backendPort = "port_backend"
        static let axBridgePort = "port_ax_bridge"
        static let ipcPort = "port_ipc"
        static let duckStartPort = "port_duck_start"
    }

    // MARK: - Init

    private init() {
        let defaults = UserDefaults.standard
        let bp = defaults.integer(forKey: Keys.backendPort)
        let ap = defaults.integer(forKey: Keys.axBridgePort)
        let ip = defaults.integer(forKey: Keys.ipcPort)
        let dp = defaults.integer(forKey: Keys.duckStartPort)

        backendPort   = bp > 0 ? UInt16(bp) : Self.defaultBackendPort
        axBridgePort  = ap > 0 ? UInt16(ap) : Self.defaultAXBridgePort
        ipcPort       = ip > 0 ? UInt16(ip) : Self.defaultIPCPort
        duckStartPort = dp > 0 ? UInt16(dp) : Self.defaultDuckStartPort
    }

    // MARK: - Reset to Defaults

    func resetToDefaults() {
        backendPort   = Self.defaultBackendPort
        axBridgePort  = Self.defaultAXBridgePort
        ipcPort       = Self.defaultIPCPort
        duckStartPort = Self.defaultDuckStartPort
    }

    // MARK: - All Managed Ports

    /// 返回所有已配置的端口及对应服务名
    var allPorts: [(port: UInt16, name: String)] {
        [
            (backendPort, "后端 API"),
            (axBridgePort, "AX Bridge"),
            (ipcPort, "IPC 服务"),
            (duckStartPort, "Duck 起始端口"),
        ]
    }

    // MARK: - Conflict Detection

    /// 检测所有端口是否有冲突（被其他进程占用）
    func checkConflicts() {
        var detected: [PortConflict] = []
        for (port, name) in allPorts {
            if let process = processOccupyingPort(port) {
                detected.append(PortConflict(port: port, serviceName: name, conflictProcess: process))
            }
        }
        // 内部互冲突检测：同一端口分配给多个服务
        var seen = Set<UInt16>()
        for (port, name) in allPorts {
            if seen.contains(port) {
                detected.append(PortConflict(port: port, serviceName: name, conflictProcess: "与其他 MacAgent 服务重复"))
            }
            seen.insert(port)
        }
        conflicts = detected
        showConflictAlert = !detected.isEmpty
    }

    /// 用 lsof 检测端口是否被占用，返回占用进程名（nil = 未占用或属于本 App 自身进程）
    private func processOccupyingPort(_ port: UInt16) -> String? {
        let pipe = Pipe()
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
        process.arguments = ["-nP", "-iTCP:\(port)", "-sTCP:LISTEN"]
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
            process.waitUntilExit()
        } catch {
            return nil
        }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        guard let output = String(data: data, encoding: .utf8), !output.isEmpty else {
            return nil
        }
        // 解析 lsof 输出, 第二行开始是结果
        let lines = output.components(separatedBy: "\n").filter { !$0.isEmpty }
        guard lines.count > 1 else { return nil }
        // lsof 列: COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME
        let parts = lines[1].split(separator: " ", omittingEmptySubsequences: true)
        guard parts.count >= 2 else { return "未知进程" }
        let command = String(parts[0])
        let pidStr = String(parts[1])
        guard let pid = Int32(pidStr) else { return command }

        // 1. 如果是当前 App 自身进程（AX Bridge / IPC 等），跳过
        if pid == ProcessInfo.processInfo.processIdentifier {
            return nil
        }

        // 2. 如果是 Python 进程，检查是否为本 App 启动的后端
        let lowerCmd = command.lowercased()
        if lowerCmd.contains("python") {
            if isMacAgentBackendProcess(pid: pid) {
                return nil
            }
        }

        return command
    }

    /// 检查指定 PID 的 Python 进程是否属于 MacAgent 后端
    private func isMacAgentBackendProcess(pid: Int32) -> Bool {
        let pipe = Pipe()
        let ps = Process()
        ps.executableURL = URL(fileURLWithPath: "/bin/ps")
        ps.arguments = ["-p", "\(pid)", "-o", "command="]
        ps.standardOutput = pipe
        ps.standardError = FileHandle.nullDevice
        do {
            try ps.run()
            ps.waitUntilExit()
        } catch {
            return false
        }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        guard let cmdLine = String(data: data, encoding: .utf8) else {
            return false
        }
        let lower = cmdLine.lowercased()
        // 后端特征：命令行包含 macagent 路径或 start.sh 或 main.py（在 backend 目录内）
        return lower.contains("macagent") && (lower.contains("main.py") || lower.contains("start.sh") || lower.contains("uvicorn"))
    }

    /// 写入端口配置文件，供 Python 后端读取
    func writePortConfigFile() {
        let config: [String: Int] = [
            "backend_port": Int(backendPort),
            "ax_bridge_port": Int(axBridgePort),
            "ipc_port": Int(ipcPort),
            "duck_start_port": Int(duckStartPort),
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: config, options: [.prettyPrinted, .sortedKeys]) else { return }
        let path = FileManager.default.temporaryDirectory.appendingPathComponent("macagent_ports.json")
        try? data.write(to: path, options: .atomic)
        print("[PortConfig] Written to \(path.path)")
    }
}
