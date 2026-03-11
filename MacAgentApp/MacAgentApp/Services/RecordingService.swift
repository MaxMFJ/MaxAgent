import Foundation

/// 录制条目概览（列表用，不含 actions 详情）
struct RecordingSummary: Codable, Identifiable {
    let id: String
    let name: String
    let description: String
    let action_count: Int
    let created_at: Double
    let tags: [String]
}

/// 录制的单条操作
struct RecordedActionItem: Codable, Identifiable {
    var id: String { "\(tool)_\(action)_\(timestamp)" }
    let tool: String
    let action: String
    let parameters: [String: AnyCodable]
    let timestamp: Double
    let delay_ms: Int
}

/// 完整录制详情
struct RecordingDetail: Codable {
    let id: String
    let name: String
    let description: String
    let actions: [RecordedActionItem]
    let created_at: Double
    let updated_at: Double
    let tags: [String]
}

/// 回放结果
struct ReplayResult: Codable {
    let success: Bool
    let total: Int
    let executed: Int?
    let failed: Int?
    let dry_run: Bool?
    let error: String?
}

/// 录制管理服务 — 与后端 /recordings API 通信
@MainActor
class RecordingService: ObservableObject {
    @Published var recordings: [RecordingSummary] = []
    @Published var isRecording: Bool = false
    @Published var activeRecordingId: String?
    @Published var activeRecordingName: String = ""
    @Published var activeActionCount: Int = 0
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?

    private let urlSession: URLSession
    private var baseURL: String
    private var statusPollTask: Task<Void, Never>?

    init(baseURL: String = "http://127.0.0.1:\(PortConfiguration.defaultBackendPort)") {
        self.baseURL = baseURL
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        self.urlSession = URLSession(configuration: config)
    }

    func updateBaseURL(_ url: String) {
        self.baseURL = url
    }

    // MARK: - 录制控制

    func startRecording(name: String, sessionId: String = "default") async {
        guard let url = URL(string: "\(baseURL)/recordings/start") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = ["session_id": sessionId, "name": name]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (data, _) = try await urlSession.data(for: request)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let ok = json["ok"] as? Bool, ok,
               let recId = json["recording_id"] as? String {
                isRecording = true
                activeRecordingId = recId
                activeRecordingName = name
                activeActionCount = 0
                errorMessage = nil
                startStatusPolling()
            }
        } catch {
            errorMessage = "启动录制失败: \(error.localizedDescription)"
        }
    }

    func stopRecording(sessionId: String = "default") async {
        guard let url = URL(string: "\(baseURL)/recordings/stop?session_id=\(sessionId)") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        do {
            let (_, _) = try await urlSession.data(for: request)
            stopStatusPolling()
            isRecording = false
            activeRecordingId = nil
            activeRecordingName = ""
            activeActionCount = 0
            await fetchRecordings()
        } catch {
            errorMessage = "停止录制失败: \(error.localizedDescription)"
        }
    }

    func checkRecordingStatus(sessionId: String = "default") async {
        guard let url = URL(string: "\(baseURL)/recordings/status?session_id=\(sessionId)") else { return }
        do {
            let (data, _) = try await urlSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                let recording = json["recording"] as? Bool ?? false
                isRecording = recording
                if recording {
                    activeRecordingId = json["recording_id"] as? String
                    activeRecordingName = json["name"] as? String ?? ""
                    activeActionCount = json["action_count"] as? Int ?? 0
                } else {
                    stopStatusPolling()
                }
            }
        } catch {
            // 忽略状态查询错误
        }
    }

    /// 启动定时轮询录制状态（每 2 秒刷新 action_count）
    func startStatusPolling() {
        stopStatusPolling()
        statusPollTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                guard !Task.isCancelled else { break }
                await checkRecordingStatus()
            }
        }
    }

    func stopStatusPolling() {
        statusPollTask?.cancel()
        statusPollTask = nil
    }

    // MARK: - 录制管理

    func fetchRecordings() async {
        guard let url = URL(string: "\(baseURL)/recordings/list") else { return }
        isLoading = true
        defer { isLoading = false }

        do {
            let (data, _) = try await urlSession.data(from: url)
            struct Resp: Codable { let recordings: [RecordingSummary] }
            let resp = try JSONDecoder().decode(Resp.self, from: data)
            recordings = resp.recordings
        } catch {
            errorMessage = "获取录制列表失败: \(error.localizedDescription)"
        }
    }

    func deleteRecording(id: String) async {
        guard let url = URL(string: "\(baseURL)/recordings/\(id)") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"

        do {
            let (_, _) = try await urlSession.data(for: request)
            recordings.removeAll { $0.id == id }
        } catch {
            errorMessage = "删除录制失败: \(error.localizedDescription)"
        }
    }

    func replayRecording(id: String, speed: Double = 1.0, dryRun: Bool = false) async -> ReplayResult? {
        guard let url = URL(string: "\(baseURL)/recordings/\(id)/replay") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 300 // 回放可能执行很久
        let body: [String: Any] = ["speed": speed, "dry_run": dryRun]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (data, _) = try await urlSession.data(for: request)
            return try JSONDecoder().decode(ReplayResult.self, from: data)
        } catch {
            errorMessage = "回放失败: \(error.localizedDescription)"
            return nil
        }
    }

    func getRecordingDetail(id: String) async -> RecordingDetail? {
        guard let url = URL(string: "\(baseURL)/recordings/\(id)") else { return nil }
        do {
            let (data, _) = try await urlSession.data(from: url)
            struct Resp: Codable { let ok: Bool; let recording: RecordingDetail }
            let resp = try JSONDecoder().decode(Resp.self, from: data)
            return resp.recording
        } catch {
            return nil
        }
    }
}
