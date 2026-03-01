import SwiftUI
import Combine
import Foundation

// MARK: - 监控专用数据模型

struct EpisodeRecord: Identifiable {
    let id: String
    let taskDescription: String
    let success: Bool
    let totalActions: Int
    let totalIterations: Int
    let executionTimeMs: Int
    let tokenUsage: TokenUsage
    let toolsUsed: [String]
    let createdAt: Date
    let result: String
}

struct ToolRankItem: Identifiable {
    let id = UUID()
    let tool: String
    let count: Int
}

struct ExecutionStatistics {
    var totalTasks: Int = 0
    var successCount: Int = 0
    var successRate: Double = 0
    var avgIterations: Double = 0
    var avgTokensPerTask: Int = 0
    var toolRanking: [ToolRankItem] = []
}

struct BackendLogEntry: Identifiable {
    let id = UUID()
    let timestamp: String
    let level: String
    let message: String
}

struct SystemHealthInfo {
    var backendHealthy: Bool = false
    var llmProvider: String = "--"
    var llmModel: String = "--"
    var evomapStatus: String = "disabled"
    var wsConnectionCount: Int = 0
    var wsConnectionsByType: [String: Int] = [:]
}

struct LocalLLMInfo {
    var available: Bool = false
    var provider: String = "--"
    var model: String = "--"
    var ollamaAvailable: Bool = false
    var ollamaServerRunning: Bool = false
    var ollamaModel: String = ""
    var lmStudioAvailable: Bool = false
    var lmStudioServerRunning: Bool = false
    var lmStudioModel: String = ""
}

struct MemoryStatusInfo {
    var embeddingModelLoaded: Bool = false
    var totalMemories: Int = 0
    var sessionSummary: [String: Int] = [:]
}

struct ModelSelectorInfo {
    var totalSelections: Int = 0
    var localCount: Int = 0
    var remoteCount: Int = 0
    var localSuccessRate: Double = 0
    var remoteSuccessRate: Double = 0
    var localRatio: Double {
        totalSelections > 0 ? Double(localCount) / Double(totalSelections) : 0
    }
}

// MARK: - 用户平台统计数据模型

struct UsageOverviewData {
    var totalRequests: Int = 0
    var successCount: Int = 0
    var totalTokens: Int = 0
    var totalPromptTokens: Int = 0
    var totalCompletionTokens: Int = 0
    var avgRPM: Double = 0
    var avgTPM: Double = 0
    var rpmHistory: [Double] = []   // 30 个点, 每分钟
    var tpmHistory: [Double] = []   // 30 个点
    var requestHistory: [Double] = []
}

struct ModelConsumptionItem: Identifiable {
    let id = UUID()
    let model: String
    let tokens: Int
}

struct ModelCallItem: Identifiable {
    let id = UUID()
    let model: String
    let count: Int
}

struct ConsumptionTrendItem: Identifiable {
    let id = UUID()
    let time: String
    let tokens: Int
}

struct ModelAnalysisData {
    var consumptionDistribution: [ModelConsumptionItem] = []
    var consumptionTrend: [ConsumptionTrendItem] = []
    var callDistribution: [ModelCallItem] = []
    var callRanking: [ModelCallItem] = []
}

// MARK: - MonitoringViewModel

@MainActor
class MonitoringViewModel: ObservableObject {

    // MARK: Tab1 - AI 执行过程（镜像 AgentViewModel）
    @Published var currentIteration: Int = 0
    @Published var actionLogs: [ActionLogEntry] = []
    @Published var taskProgress: TaskProgress?
    @Published var selectedModelType: String?
    @Published var selectedModelReason: String?
    @Published var taskComplexity: Int = 0
    @Published var recentToolCalls: [ToolCall] = []
    @Published var sessionTokenUsage: TokenUsage = TokenUsage()
    @Published var taskElapsedSeconds: Int = 0
    @Published var tokenHistory: [Int] = []  // 用于迷你图表动画

    // MARK: LLM Neural Stream
    @Published var llmStreamingText: String = ""
    @Published var isStreamingLLM: Bool = false

    // MARK: Tab2 - 系统状态（HTTP 轮询）
    @Published var healthInfo: SystemHealthInfo = SystemHealthInfo()
    @Published var localLLMInfo: LocalLLMInfo = LocalLLMInfo()
    @Published var memoryStatus: MemoryStatusInfo = MemoryStatusInfo()
    @Published var modelSelectorInfo: ModelSelectorInfo = ModelSelectorInfo()
    @Published var lastPolledAt: Date?
    @Published var isPolling: Bool = false

    // MARK: Tab3 - 历史任务分析（HTTP 轮询）
    @Published var episodes: [EpisodeRecord] = []
    @Published var statistics: ExecutionStatistics = ExecutionStatistics()
    @Published var isLoadingHistory: Bool = false
    @Published var selectedEpisodeId: String?

    // MARK: Tab4 - 日志流（镜像 AgentViewModel + HTTP 轮询）
    @Published var executionLogs: [ExecutionLogEntry] = []
    @Published var systemNotifications: [SystemNotification] = []
    @Published var backendLogs: [BackendLogEntry] = []
    @Published var logLevelFilter: String? = nil
    @Published var logSearchText: String = ""
    @Published var logSourceFilter: String = "tool"

    // MARK: Tab5 - 用户平台统计（HTTP 轮询）
    @Published var usageOverview: UsageOverviewData = UsageOverviewData()
    @Published var modelAnalysis: ModelAnalysisData = ModelAnalysisData()

    // MARK: 私有
    private var cancellables = Set<AnyCancellable>()
    private var pollingTask: Task<Void, Never>?
    private var historyRefreshTask: Task<Void, Never>?
    private var elapsedTimer: Task<Void, Never>?
    private var nextLogIndex: Int = 0
    private let baseURL = "http://127.0.0.1:8765"

    private let httpSession: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 8
        return URLSession(configuration: config)
    }()

    // MARK: 计算属性

    var filteredExecutionLogs: [ExecutionLogEntry] {
        executionLogs.filter { log in
            let lvl = logLevelFilter.map { log.level.uppercased() == $0 } ?? true
            let kw = logSearchText.isEmpty ||
                log.message.localizedCaseInsensitiveContains(logSearchText) ||
                log.toolName.localizedCaseInsensitiveContains(logSearchText)
            return lvl && kw
        }
    }

    var filteredBackendLogs: [BackendLogEntry] {
        backendLogs.filter { log in
            let lvl = logLevelFilter.map { log.level.uppercased() == $0 } ?? true
            let kw = logSearchText.isEmpty || log.message.localizedCaseInsensitiveContains(logSearchText)
            return lvl && kw
        }
    }

    var filteredNotifications: [SystemNotification] {
        systemNotifications.filter { n in
            let kw = logSearchText.isEmpty ||
                n.title.localizedCaseInsensitiveContains(logSearchText) ||
                n.content.localizedCaseInsensitiveContains(logSearchText)
            return kw
        }
    }

    var currentTaskSuccessRate: Double {
        guard let p = taskProgress, p.totalActions > 0 else { return 0 }
        return Double(p.successfulActions) / Double(p.totalActions)
    }

    // MARK: - 订阅 AgentViewModel

    func subscribeToAgentViewModel(_ agent: AgentViewModel) {
        cancellables.removeAll()

        agent.$currentIteration
            .receive(on: DispatchQueue.main)
            .assign(to: &$currentIteration)

        agent.$actionLogs
            .receive(on: DispatchQueue.main)
            .assign(to: &$actionLogs)

        agent.$taskProgress
            .receive(on: DispatchQueue.main)
            .assign(to: &$taskProgress)

        agent.$selectedModelType
            .receive(on: DispatchQueue.main)
            .assign(to: &$selectedModelType)

        agent.$selectedModelReason
            .receive(on: DispatchQueue.main)
            .assign(to: &$selectedModelReason)

        agent.$taskComplexity
            .receive(on: DispatchQueue.main)
            .assign(to: &$taskComplexity)

        agent.$recentToolCalls
            .receive(on: DispatchQueue.main)
            .assign(to: &$recentToolCalls)

        agent.$executionLogs
            .receive(on: DispatchQueue.main)
            .assign(to: &$executionLogs)

        agent.$systemNotifications
            .receive(on: DispatchQueue.main)
            .assign(to: &$systemNotifications)

        agent.$llmStreamingText
            .receive(on: DispatchQueue.main)
            .assign(to: &$llmStreamingText)

        agent.$isStreamingLLM
            .receive(on: DispatchQueue.main)
            .assign(to: &$isStreamingLLM)

        // Token 使用累积（从当前对话聚合）
        agent.$currentConversation
            .receive(on: DispatchQueue.main)
            .map { conversation -> TokenUsage in
                guard let msgs = conversation?.messages else { return TokenUsage() }
                return msgs.compactMap { $0.tokenUsage }.reduce(TokenUsage()) { acc, u in
                    var r = acc; r.add(u); return r
                }
            }
            .sink { [weak self] usage in
                self?.sessionTokenUsage = usage
                var hist = self?.tokenHistory ?? []
                let last = hist.last ?? 0
                if usage.totalTokens > last || hist.isEmpty {
                    hist.append(usage.totalTokens)
                    if hist.count > 25 { hist.removeFirst() }
                    self?.tokenHistory = hist
                }
            }
            .store(in: &cancellables)

        // 任务运行计时
        agent.$taskProgress
            .receive(on: DispatchQueue.main)
            .sink { [weak self] progress in
                if progress?.status == .running {
                    self?.startElapsedTimer(from: progress?.startTime ?? Date())
                } else {
                    self?.stopElapsedTimer()
                }
            }
            .store(in: &cancellables)
    }

    // MARK: - 轮询控制

    func startPolling() {
        stopPolling()
        pollingTask = Task {
            var tick = 0
            while !Task.isCancelled {
                tick += 1
                isPolling = true
                await fetchHealthAndConnections()
                await fetchBackendLogs()
                if tick % 2 == 0 {
                    await fetchMemoryStatus()
                    await fetchLocalLLMStatus()
                    await fetchModelSelectorStats()
                    await fetchUsageOverview()
                    await fetchModelAnalysis()
                }
                isPolling = false
                lastPolledAt = Date()
                try? await Task.sleep(nanoseconds: 5_000_000_000)
            }
        }

        // 历史数据首次加载
        Task { await fetchHistory() }
        // 每 30 秒刷新历史
        historyRefreshTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 30_000_000_000)
                await fetchHistory()
            }
        }
    }

    func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
        historyRefreshTask?.cancel()
        historyRefreshTask = nil
        stopElapsedTimer()
    }

    // MARK: - HTTP 数据拉取

    private func fetchHealthAndConnections() async {
        guard let healthURL = URL(string: "\(baseURL)/health"),
              let connURL = URL(string: "\(baseURL)/connections") else { return }
        do {
            let (hd, _) = try await httpSession.data(from: healthURL)
            if let json = try? JSONSerialization.jsonObject(with: hd) as? [String: Any] {
                healthInfo.backendHealthy = json["status"] as? String == "healthy"
                healthInfo.llmProvider = json["provider"] as? String ?? "--"
                healthInfo.llmModel = json["model"] as? String ?? "--"
                healthInfo.evomapStatus = json["evomap"] as? String ?? "disabled"
            }
        } catch { healthInfo.backendHealthy = false }

        do {
            let (cd, _) = try await httpSession.data(from: connURL)
            if let json = try? JSONSerialization.jsonObject(with: cd) as? [String: Any] {
                healthInfo.wsConnectionCount = json["total_connections"] as? Int ?? 0
                healthInfo.wsConnectionsByType = json["by_type"] as? [String: Int] ?? [:]
            }
        } catch {}
    }

    private func fetchMemoryStatus() async {
        guard let url = URL(string: "\(baseURL)/memory/status") else { return }
        do {
            let (data, _) = try await httpSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                memoryStatus.embeddingModelLoaded = json["embedding_model_loaded"] as? Bool ?? false
                memoryStatus.totalMemories = json["total_memories"] as? Int ?? 0
                if let sessions = json["sessions"] as? [String: [String: Any]] {
                    memoryStatus.sessionSummary = sessions.mapValues { $0["items"] as? Int ?? 0 }
                }
            }
        } catch {}
    }

    private func fetchLocalLLMStatus() async {
        guard let url = URL(string: "\(baseURL)/local-llm/status") else { return }
        do {
            let (data, _) = try await httpSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                if let cur = json["current"] as? [String: Any] {
                    localLLMInfo.available = cur["available"] as? Bool ?? false
                    localLLMInfo.provider = cur["provider"] as? String ?? "--"
                    localLLMInfo.model = cur["model"] as? String ?? "--"
                }
                if let ollama = json["ollama"] as? [String: Any] {
                    localLLMInfo.ollamaAvailable = ollama["available"] as? Bool ?? false
                    localLLMInfo.ollamaServerRunning = ollama["server_running"] as? Bool ?? localLLMInfo.ollamaAvailable
                    localLLMInfo.ollamaModel = ollama["model"] as? String ?? ""
                }
                if let lms = json["lm_studio"] as? [String: Any] {
                    localLLMInfo.lmStudioAvailable = lms["available"] as? Bool ?? false
                    localLLMInfo.lmStudioServerRunning = lms["server_running"] as? Bool ?? localLLMInfo.lmStudioAvailable
                    localLLMInfo.lmStudioModel = lms["model"] as? String ?? ""
                }
            }
        } catch {}
    }

    private func fetchModelSelectorStats() async {
        guard let url = URL(string: "\(baseURL)/model-selector/status") else { return }
        do {
            let (data, _) = try await httpSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                modelSelectorInfo.totalSelections = json["total_selections"] as? Int ?? 0
                modelSelectorInfo.localCount = json["local_selections"] as? Int ?? 0
                modelSelectorInfo.remoteCount = json["remote_selections"] as? Int ?? 0
                if let rate = json["success_rate_by_type"] as? [String: Any] {
                    modelSelectorInfo.localSuccessRate = rate["local"] as? Double ?? 0
                    modelSelectorInfo.remoteSuccessRate = rate["remote"] as? Double ?? 0
                }
            }
        } catch {}
    }

    private func fetchBackendLogs() async {
        guard let url = URL(string: "\(baseURL)/logs?limit=50&since_index=\(nextLogIndex)") else { return }
        do {
            let (data, _) = try await httpSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let logs = json["logs"] as? [[String: Any]],
               let nextIdx = json["next_index"] as? Int {
                let newEntries = logs.compactMap { d -> BackendLogEntry? in
                    guard let ts = d["timestamp"] as? String,
                          let lv = d["level"] as? String,
                          let msg = d["message"] as? String else { return nil }
                    return BackendLogEntry(timestamp: ts, level: lv, message: msg)
                }
                backendLogs.append(contentsOf: newEntries)
                if backendLogs.count > 500 {
                    backendLogs.removeFirst(backendLogs.count - 500)
                }
                nextLogIndex = nextIdx
            }
        } catch {}
    }

    func fetchHistory() async {
        isLoadingHistory = true
        defer { isLoadingHistory = false }

        async let episodesResult: Void = _fetchEpisodes()
        async let statsResult: Void = _fetchStatistics()
        _ = await (episodesResult, statsResult)
    }

    private func _fetchEpisodes() async {
        guard let url = URL(string: "\(baseURL)/monitor/episodes?count=30") else { return }
        do {
            let (data, _) = try await httpSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let list = json["episodes"] as? [[String: Any]] {
                episodes = list.compactMap { d -> EpisodeRecord? in
                    guard let id = d["episode_id"] as? String else { return nil }
                    let tu = d["token_usage"] as? [String: Any] ?? [:]
                    let usage = TokenUsage(
                        promptTokens: tu["prompt_tokens"] as? Int ?? 0,
                        completionTokens: tu["completion_tokens"] as? Int ?? 0,
                        totalTokens: tu["total_tokens"] as? Int ?? 0
                    )
                    let createdStr = d["created_at"] as? String ?? ""
                    let date = ISO8601DateFormatter().date(from: createdStr) ?? Date()
                    return EpisodeRecord(
                        id: id,
                        taskDescription: d["task_description"] as? String ?? "",
                        success: d["success"] as? Bool ?? false,
                        totalActions: d["total_actions"] as? Int ?? 0,
                        totalIterations: d["total_iterations"] as? Int ?? 0,
                        executionTimeMs: d["execution_time_ms"] as? Int ?? 0,
                        tokenUsage: usage,
                        toolsUsed: d["tools_used"] as? [String] ?? [],
                        createdAt: date,
                        result: d["result"] as? String ?? ""
                    )
                }
            }
        } catch {}
    }

    private func _fetchStatistics() async {
        guard let url = URL(string: "\(baseURL)/monitor/statistics") else { return }
        do {
            let (data, _) = try await httpSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                var s = ExecutionStatistics()
                s.totalTasks = json["total_tasks"] as? Int ?? 0
                s.successCount = json["success_count"] as? Int ?? 0
                s.successRate = json["success_rate"] as? Double ?? 0
                s.avgIterations = json["avg_iterations"] as? Double ?? 0
                s.avgTokensPerTask = json["avg_tokens_per_task"] as? Int ?? 0
                if let ranking = json["tool_ranking"] as? [[String: Any]] {
                    s.toolRanking = ranking.compactMap { d -> ToolRankItem? in
                        guard let t = d["tool"] as? String, let c = d["count"] as? Int else { return nil }
                        return ToolRankItem(tool: t, count: c)
                    }
                }
                statistics = s
            }
        } catch {}
    }

    // MARK: - 用户平台统计拉取

    private func fetchUsageOverview() async {
        guard let url = URL(string: "\(baseURL)/usage-stats/overview") else { return }
        do {
            let (data, _) = try await httpSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                var o = UsageOverviewData()
                o.totalRequests = json["total_requests"] as? Int ?? 0
                o.successCount = json["success_count"] as? Int ?? 0
                o.totalTokens = json["total_tokens"] as? Int ?? 0
                o.totalPromptTokens = json["total_prompt_tokens"] as? Int ?? 0
                o.totalCompletionTokens = json["total_completion_tokens"] as? Int ?? 0
                o.avgRPM = json["avg_rpm"] as? Double ?? 0
                o.avgTPM = json["avg_tpm"] as? Double ?? 0
                o.rpmHistory = (json["rpm_history"] as? [Any])?.compactMap { ($0 as? NSNumber)?.doubleValue } ?? []
                o.tpmHistory = (json["tpm_history"] as? [Any])?.compactMap { ($0 as? NSNumber)?.doubleValue } ?? []
                o.requestHistory = (json["request_history"] as? [Any])?.compactMap { ($0 as? NSNumber)?.doubleValue } ?? []
                usageOverview = o
            }
        } catch {}
    }

    private func fetchModelAnalysis() async {
        guard let url = URL(string: "\(baseURL)/usage-stats/model-analysis") else { return }
        do {
            let (data, _) = try await httpSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                var m = ModelAnalysisData()
                if let cd = json["consumption_distribution"] as? [[String: Any]] {
                    m.consumptionDistribution = cd.compactMap { d in
                        guard let model = d["model"] as? String,
                              let tokens = d["tokens"] as? Int else { return nil }
                        return ModelConsumptionItem(model: model, tokens: tokens)
                    }
                }
                if let ct = json["consumption_trend"] as? [[String: Any]] {
                    m.consumptionTrend = ct.compactMap { d in
                        guard let time = d["time"] as? String,
                              let tokens = d["tokens"] as? Int else { return nil }
                        return ConsumptionTrendItem(time: time, tokens: tokens)
                    }
                }
                if let callDist = json["call_distribution"] as? [[String: Any]] {
                    m.callDistribution = callDist.compactMap { d in
                        guard let model = d["model"] as? String,
                              let count = d["count"] as? Int else { return nil }
                        return ModelCallItem(model: model, count: count)
                    }
                }
                if let cr = json["call_ranking"] as? [[String: Any]] {
                    m.callRanking = cr.compactMap { d in
                        guard let model = d["model"] as? String,
                              let count = d["count"] as? Int else { return nil }
                        return ModelCallItem(model: model, count: count)
                    }
                }
                modelAnalysis = m
            }
        } catch {}
    }

    // MARK: - 计时器

    private func startElapsedTimer(from startDate: Date) {
        stopElapsedTimer()
        elapsedTimer = Task {
            while !Task.isCancelled {
                taskElapsedSeconds = Int(Date().timeIntervalSince(startDate))
                try? await Task.sleep(nanoseconds: 1_000_000_000)
            }
        }
    }

    private func stopElapsedTimer() {
        elapsedTimer?.cancel()
        elapsedTimer = nil
    }
}
