import Foundation
import Network
import Combine

// MARK: - Duck Config Model

struct DuckConfig: Codable, Equatable {
    var mode: String           // "duck" or "main"
    var mainAgentUrl: String   // ws://... the main backend duck WebSocket endpoint
    var token: String
    var duckId: String
    var duckType: String
    var permissions: [String]
    var duckName: String?

    enum CodingKeys: String, CodingKey {
        case mode
        case mainAgentUrl = "main_agent_url"
        case token
        case duckId = "duck_id"
        case duckType = "duck_type"
        case permissions
        case duckName = "duck_name"
    }

    var isDuckMode: Bool { mode == "duck" }

    static var empty: DuckConfig {
        DuckConfig(mode: "main", mainAgentUrl: "", token: "", duckId: "", duckType: "general", permissions: [])
    }
}

// MARK: - EggModeManager

@MainActor
class EggModeManager: ObservableObject {
    static let shared = EggModeManager()

    @Published private(set) var config: DuckConfig?
    @Published private(set) var isDuckMode: Bool = false
    @Published private(set) var assignedPort: Int = Int(PortConfiguration.defaultBackendPort)  // main default, duckStartPort+ for duck
    @Published var importError: String?
    @Published var importSuccess: Bool = false

    private let configFileName = "duck_config.json"

    private var configFileURL: URL? {
        guard let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else { return nil }
        let dir = support.appendingPathComponent("ChowDuck", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent(configFileName)
    }

    private init() {
        loadConfig()
    }

    // MARK: - Load

    func loadConfig() {
        guard let url = configFileURL, FileManager.default.fileExists(atPath: url.path) else {
            config = nil
            isDuckMode = false
            assignedPort = Int(PortConfiguration.shared.backendPort)
            return
        }
        do {
            let data = try Data(contentsOf: url)
            let decoded = try JSONDecoder().decode(DuckConfig.self, from: data)
            config = decoded
            isDuckMode = decoded.isDuckMode
        } catch {
            print("[EggModeManager] Failed to load duck_config.json: \(error)")
            config = nil
            isDuckMode = false
        }
    }

    // MARK: - Import from file (JSON or ZIP)

    func importConfig(from fileURL: URL) async {
        importError = nil
        importSuccess = false

        let ext = fileURL.pathExtension.lowercased()

        do {
            let parsedConfig: DuckConfig
            if ext == "zip" {
                parsedConfig = try await extractConfigFromZip(url: fileURL)
            } else if ext == "json" {
                let data = try Data(contentsOf: fileURL)
                parsedConfig = try JSONDecoder().decode(DuckConfig.self, from: data)
            } else {
                importError = "不支持的文件格式，请选择 .json 或 .zip 文件"
                return
            }

            guard parsedConfig.mode == "duck" else {
                importError = "配置文件的 mode 不是 \"duck\"，无法导入"
                return
            }
            guard !parsedConfig.mainAgentUrl.isEmpty else {
                importError = "配置文件缺少 main_agent_url 字段"
                return
            }

            try saveConfig(parsedConfig)
            config = parsedConfig
            isDuckMode = true
            importSuccess = true
        } catch let e as EggImportError {
            importError = e.localizedDescription
        } catch {
            importError = "导入失败：\(error.localizedDescription)"
        }
    }

    // MARK: - Save

    private func saveConfig(_ cfg: DuckConfig) throws {
        guard let url = configFileURL else {
            throw EggImportError.saveFailed("无法获取配置目录")
        }
        let data = try JSONEncoder().encode(cfg)
        try data.write(to: url, options: .atomic)
    }

    // MARK: - Clear (exit duck mode)

    func clearConfig() {
        guard let url = configFileURL else { return }
        try? FileManager.default.removeItem(at: url)
        config = nil
        isDuckMode = false
        assignedPort = Int(PortConfiguration.shared.backendPort)
    }

    // MARK: - Port Discovery

    /// Find first available TCP port starting from `startPort`.
    /// Runs on a background thread, returns the free port.
    func findAvailablePort(startPort: Int? = nil, maxTries: Int = 100) async -> Int {
        let start = startPort ?? Int(PortConfiguration.shared.duckStartPort)
        return await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .utility).async {
                for port in start ..< (start + maxTries) {
                    if Self.isPortFree(port: port) {
                        continuation.resume(returning: port)
                        return
                    }
                }
                continuation.resume(returning: start)  // fallback
            }
        }
    }

    nonisolated private static func isPortFree(port: Int) -> Bool {
        let socketFD = socket(AF_INET, SOCK_STREAM, 0)
        guard socketFD >= 0 else { return false }
        defer { close(socketFD) }

        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = in_port_t(port).bigEndian
        addr.sin_addr.s_addr = INADDR_ANY

        // Try to bind — if successful, port is free
        let result = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(socketFD, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        return result == 0
    }

    /// Resolve and assign the duck backend port. Call this at app startup when in duck mode.
    func resolvePort() async {
        if isDuckMode {
            assignedPort = await findAvailablePort()
        } else {
            assignedPort = Int(PortConfiguration.shared.backendPort)
        }
    }

    // MARK: - ZIP Extraction

    private func extractConfigFromZip(url: URL) async throws -> DuckConfig {
        // Use unzip via process
        let tempDir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/unzip")
        process.arguments = ["-o", url.path, "-d", tempDir.path]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        try process.run()
        process.waitUntilExit()

        // Find config.json inside extracted content
        let candidates = ["config.json", "duck_config.json"]
        for name in candidates {
            let candidate = tempDir.appendingPathComponent(name)
            if FileManager.default.fileExists(atPath: candidate.path) {
                let data = try Data(contentsOf: candidate)
                return try JSONDecoder().decode(DuckConfig.self, from: data)
            }
        }
        // Search recursively one level deep
        if let contents = try? FileManager.default.contentsOfDirectory(at: tempDir, includingPropertiesForKeys: nil) {
            for item in contents {
                for name in candidates {
                    let sub = item.appendingPathComponent(name)
                    if FileManager.default.fileExists(atPath: sub.path) {
                        let data = try Data(contentsOf: sub)
                        return try JSONDecoder().decode(DuckConfig.self, from: data)
                    }
                }
            }
        }
        throw EggImportError.configNotFoundInZip
    }
}

// MARK: - Errors

enum EggImportError: LocalizedError {
    case configNotFoundInZip
    case saveFailed(String)

    var errorDescription: String? {
        switch self {
        case .configNotFoundInZip:
            return "ZIP 中未找到 config.json 或 duck_config.json"
        case .saveFailed(let msg):
            return "保存配置失败：\(msg)"
        }
    }
}
