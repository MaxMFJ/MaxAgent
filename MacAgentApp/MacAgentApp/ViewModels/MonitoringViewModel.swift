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

// MARK: - 深度健康检查数据模型（/health/deep）

struct DeepHealthCheck: Identifiable {
    let id: String          // 子系统名称 (llm, disk, memory, vector_db, tools, task_tracker, traces, evomap)
    let ok: Bool
    let required: Bool
    let detail: String
    let latencyMs: Double?  // 仅 LLM 有
}

struct DeepHealthData {
    var healthy: Bool = false
    var requiredFailed: [String] = []
    var checks: [DeepHealthCheck] = []
    var checkDurationMs: Double = 0
    var serverStatus: String = "normal"
    var timestamp: Double = 0
}

// MARK: - Traces 数据模型

struct TraceListItem: Identifiable {
    let id: String          // task_id
    let taskId: String
    let sizeBytes: Int
    let mtime: Double
    let spanCount: Int
}

struct TraceSummaryData {
    var taskId: String = ""
    var exists: Bool = false
    var totalSpans: Int = 0
    var typeCounts: [String: Int] = [:]
    var tokens: TraceTokenSummary = TraceTokenSummary()
    var latency: TraceLatencyStats = TraceLatencyStats()
    var toolCalls: TraceToolCallStats = TraceToolCallStats()
    var timeline: TraceTimelineData = TraceTimelineData()
    var recentErrors: [String] = []
}

struct TraceTokenSummary {
    var prompt: Int = 0
    var completion: Int = 0
    var total: Int = 0
}

struct TraceLatencyStats {
    var count: Int = 0
    var minMs: Double = 0
    var maxMs: Double = 0
    var avgMs: Double = 0
    var p90Ms: Double = 0
}

struct TraceToolCallStats {
    var success: Int = 0
    var failure: Int = 0
}

struct TraceTimelineData {
    var firstTs: Double? = nil
    var lastTs: Double? = nil
    var durationS: Double? = nil
}

struct TraceSpanItem: Identifiable {
    let id = UUID()
    let type: String
    let ts: Double
    let latencyMs: Double?
    let success: Bool?
    let detail: String          // 简短描述
    let rawJSON: [String: Any]  // 完整 span 数据
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

// MARK: - 多任务监控数据（按 task_id 分桶）

struct TaskMonitorData: Identifiable {
    let id: String
    var taskProgress: TaskProgress?
    var actionLogs: [ActionLogEntry]
    var llmStreamingText: String
    var isStreamingLLM: Bool
    var sessionTokenUsage: TokenUsage
    var currentIteration: Int
    var selectedModelType: String?
    var selectedModelReason: String?
    var taskComplexity: Int
    var taskElapsedSeconds: Int
    var tokenHistory: [Int]
    var sourceSession: String
    var taskType: String
    var lastUpdated: Date

    // MARK: - 执行者（Actor）信息
    /// 执行者类型："main" / "local_duck" / "remote_duck"
    var workerType: String
    /// 执行者 ID："main" 或 duck_id
    var workerId: String
    /// 执行者显示标签："主Agent" / "Duck[xxx]"
    var workerLabel: String

    init(taskId: String, sourceSession: String, taskType: String,
         workerType: String = "main", workerId: String = "main", workerLabel: String = "主Agent") {
        self.id = taskId
        self.taskProgress = nil
        self.actionLogs = []
        self.llmStreamingText = ""
        self.isStreamingLLM = false
        self.sessionTokenUsage = TokenUsage()
        self.currentIteration = 0
        self.selectedModelType = nil
        self.selectedModelReason = nil
        self.taskComplexity = 0
        self.taskElapsedSeconds = 0
        self.tokenHistory = []
        self.sourceSession = sourceSession
        self.taskType = taskType
        self.workerType = workerType
        self.workerId = workerId
        self.workerLabel = workerLabel
        self.lastUpdated = Date()
    }
}

/// 来自 /monitor/active-tasks 的任务摘要
struct ActiveTaskItem: Identifiable {
    let id: String
    let taskId: String
    let sessionId: String
    let taskType: String
    let description: String
    let status: String
    let createdAt: Double
    let finishedAt: Double?
    // 执行者信息（当 taskType == "duck" 时填充）
    let workerType: String?
    let workerId: String?
    let workerLabel: String?
}

// MARK: - MonitoringViewModel

@MainActor
class MonitoringViewModel: ObservableObject {

    // MARK: Tab1 - 多任务执行过程
    @Published var tasks: [String: TaskMonitorData] = [:]
    @Published var selectedTaskId: String?
    @Published var viewMode: ExecutionViewMode = .single  // .single 单任务 | .all 全部合并
    @Published var activeTaskList: [ActiveTaskItem] = []
    @Published var isLoadingActiveTasks: Bool = false

    // MARK: 兼容旧逻辑（无多任务数据时回退）
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

    enum ExecutionViewMode: String, CaseIterable {
        case single = "single"
        case all = "all"
    }

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

    // MARK: Tab6 - 深度健康 + Traces
    @Published var deepHealth: DeepHealthData = DeepHealthData()
    @Published var traceList: [TraceListItem] = []
    @Published var selectedTraceSummary: TraceSummaryData? = nil
    @Published var selectedTraceSpans: [TraceSpanItem] = []
    @Published var isLoadingTraces: Bool = false
    @Published var selectedTraceTaskId: String? = nil

    // MARK: 私有
    private var cancellables = Set<AnyCancellable>()
    private var pollingTask: Task<Void, Never>?
    private var historyRefreshTask: Task<Void, Never>?
    private var elapsedTimer: Task<Void, Never>?
    private var multiTaskElapsedTimer: Task<Void, Never>?
    private var nextLogIndex: Int = 0
    private var baseURL: String { "http://127.0.0.1:\(PortConfiguration.shared.backendPort)" }

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

    /// 当前选中任务的监控数据（多任务模式）
    var currentTaskData: TaskMonitorData? {
        if let id = selectedTaskId, let t = tasks[id] { return t }
        if let running = tasks.values.first(where: { $0.taskProgress?.status == .running }) { return running }
        return tasks.values.max(by: { $0.lastUpdated < $1.lastUpdated })
    }

    /// 全部视图下合并的时间轴（按时间排序，带任务标签）
    var mergedActionLogs: [(taskId: String, taskDesc: String, entry: ActionLogEntry)] {
        var result: [(String, String, ActionLogEntry)] = []
        for (tid, data) in tasks {
            let desc = data.taskProgress?.taskDescription ?? tid.prefix(8).description
            for entry in data.actionLogs {
                result.append((tid, String(desc), entry))
            }
        }
        result.sort { $0.2.timestamp < $1.2.timestamp }
        return result
    }

    /// 是否有任何任务数据可展示
    var hasAnyTaskData: Bool {
        !tasks.isEmpty || !actionLogs.isEmpty || taskProgress != nil
    }

    private static func buildParamsSummary(actionType: String, params: [String: Any]) -> String? {
        let t = actionType.lowercased()
        if t.contains("run_shell") || t.contains("shell") {
            if let cmd = params["command"] as? String, !cmd.isEmpty {
                return cmd.count > 80 ? String(cmd.prefix(77)) + "…" : cmd
            }
        }
        if t.contains("read_file") || t.contains("write_file") || t.contains("delete_file") {
            if let path = params["path"] as? String, !path.isEmpty { return path }
        }
        if t.contains("call_tool") {
            if let name = params["tool_name"] as? String, !name.isEmpty {
                if let args = params["args"] as? [String: Any], let action = args["action"] as? String {
                    return "\(name) action=\(action)"
                }
                return name
            }
        }
        if t.contains("create_and_run") {
            if let code = params["code"] as? String, !code.isEmpty {
                return code.count > 60 ? String(code.prefix(57)) + "…" : code
            }
        }
        if let path = params["path"] as? String, !path.isEmpty { return path }
        if let cmd = params["command"] as? String, !cmd.isEmpty { return cmd }
        return nil
    }

    // MARK: - 多任务 monitor_event 处理

    func applyMonitorEvent(taskId: String, sourceSession: String, event: [String: Any]) {
        let taskType = event["task_type"] as? String ?? "autonomous"

        // 提取执行者（actor）信息（由后端注入到 inner event）
        let workerType = event["_worker_type"] as? String ?? "main"
        let workerId = event["_worker_id"] as? String ?? "main"
        let workerLabel = event["_worker_label"] as? String ?? "主Agent"

        if tasks[taskId] == nil {
            tasks[taskId] = TaskMonitorData(
                taskId: taskId,
                sourceSession: sourceSession,
                taskType: taskType,
                workerType: workerType,
                workerId: workerId,
                workerLabel: workerLabel
            )
            if selectedTaskId == nil { selectedTaskId = taskId }
        }
        guard var data = tasks[taskId] else { return }
        data.lastUpdated = Date()
        // 更新 actor 信息（Duck 可能在任务进行中首次出现）
        if workerType != "main" {
            data.workerType = workerType
            data.workerId = workerId
            data.workerLabel = workerLabel
        }

        guard let eventType = event["type"] as? String else { tasks[taskId] = data; return }

        switch eventType {
        case "task_start":
            let taskDesc = event["task"] as? String ?? ""
            data.taskProgress = TaskProgress(
                id: taskId,
                taskDescription: taskDesc,
                status: .running,
                currentIteration: 0,
                totalActions: 0,
                successfulActions: 0,
                failedActions: 0,
                startTime: Date()
            )
            data.taskElapsedSeconds = 0

        case "llm_request_start":
            data.isStreamingLLM = true
            let provider = event["provider"] as? String ?? "unknown"
            let model = event["model"] as? String ?? ""
            let iteration = event["iteration"] as? Int ?? 0
            let llmId = "llm_\(iteration)_\(taskId)"
            let logEntry = ActionLogEntry(
                actionId: llmId,
                actionType: "llm_request",
                reasoning: "请求 \(provider)/\(model)",
                status: .executing,
                output: nil,
                error: nil,
                timestamp: Date(),
                iteration: iteration
            )
            data.actionLogs.append(logEntry)

        case "llm_request_end":
            data.isStreamingLLM = false
            let iteration = event["iteration"] as? Int ?? 0
            let latencyMs = event["latency_ms"] as? Int ?? 0
            let usage = event["usage"] as? [String: Any] ?? [:]
            let error = event["error"] as? String
            let llmId = "llm_\(iteration)_\(taskId)"
            if let index = data.actionLogs.firstIndex(where: { $0.actionId == llmId }) {
                let pt = usage["prompt_tokens"] as? Int ?? 0
                let ct = usage["completion_tokens"] as? Int ?? 0
                var out = "延迟: \(latencyMs)ms | 输入: \(pt) tokens | 输出: \(ct) tokens"
                if let err = error, !err.isEmpty { out += " | 错误: \(err)" }
                let e = data.actionLogs[index]
                data.actionLogs[index] = ActionLogEntry(
                    actionId: llmId,
                    actionType: "llm_request",
                    reasoning: e.reasoning,
                    status: error != nil ? .failed : .success,
                    output: out,
                    error: error,
                    timestamp: e.timestamp,
                    iteration: iteration,
                    paramsSummary: e.paramsSummary
                )
            }

        case "action_plan":
            let action = event["action"] as? [String: Any] ?? [:]
            let iteration = event["iteration"] as? Int ?? 0
            data.currentIteration = iteration
            let actionType = action["action_type"] as? String ?? "unknown"
            let reasoning = action["reasoning"] as? String ?? ""
            let actionId = (action["action_id"] as? String ?? UUID().uuidString)
            let params = action["params"] as? [String: Any] ?? [:]
            let paramsSummary = Self.buildParamsSummary(actionType: actionType, params: params)
            let logEntry = ActionLogEntry(
                actionId: "\(taskId)_\(actionId)",
                actionType: actionType,
                reasoning: reasoning,
                status: .pending,
                output: nil,
                error: nil,
                timestamp: Date(),
                iteration: iteration,
                paramsSummary: paramsSummary
            )
            data.actionLogs.append(logEntry)

        case "action_executing":
            let actionId = event["action_id"] as? String ?? ""
            let fullId = "\(taskId)_\(actionId)"
            if let index = data.actionLogs.firstIndex(where: { $0.actionId == fullId }) {
                let e = data.actionLogs[index]
                data.actionLogs[index] = ActionLogEntry(
                    actionId: fullId,
                    actionType: e.actionType,
                    reasoning: e.reasoning,
                    status: .executing,
                    output: nil,
                    error: nil,
                    timestamp: e.timestamp,
                    iteration: e.iteration,
                    paramsSummary: e.paramsSummary
                )
            } else if let index = data.actionLogs.firstIndex(where: { $0.actionId == actionId }) {
                let e = data.actionLogs[index]
                data.actionLogs[index] = ActionLogEntry(
                    actionId: e.actionId,
                    actionType: e.actionType,
                    reasoning: e.reasoning,
                    status: .executing,
                    output: nil,
                    error: nil,
                    timestamp: e.timestamp,
                    iteration: e.iteration,
                    paramsSummary: e.paramsSummary
                )
            }

        case "action_result":
            let actionId = event["action_id"] as? String ?? ""
            let success = event["success"] as? Bool ?? false
            let output = event["output"] as? String
            let error = event["error"] as? String
            let fullId = "\(taskId)_\(actionId)"
            var actionType = "unknown"
            if let index = data.actionLogs.firstIndex(where: { $0.actionId == fullId }) {
                actionType = data.actionLogs[index].actionType
                let e = data.actionLogs[index]
                data.actionLogs[index] = ActionLogEntry(
                    actionId: fullId,
                    actionType: actionType,
                    reasoning: e.reasoning,
                    status: success ? .success : .failed,
                    output: output,
                    error: error,
                    timestamp: e.timestamp,
                    iteration: e.iteration,
                    paramsSummary: e.paramsSummary
                )
            } else if let index = data.actionLogs.firstIndex(where: { $0.actionId == actionId }) {
                actionType = data.actionLogs[index].actionType
                let e = data.actionLogs[index]
                data.actionLogs[index] = ActionLogEntry(
                    actionId: e.actionId,
                    actionType: actionType,
                    reasoning: e.reasoning,
                    status: success ? .success : .failed,
                    output: output,
                    error: error,
                    timestamp: e.timestamp,
                    iteration: e.iteration,
                    paramsSummary: e.paramsSummary
                )
            }
            if var p = data.taskProgress {
                if success {
                    p.successfulActions += 1
                } else {
                    p.failedActions += 1
                }
                p.totalActions = p.successfulActions + p.failedActions
                data.taskProgress = p
            }

        case "task_complete":
            let success: Bool
            if let s = event["success"] as? Bool {
                success = s
            } else if let status = event["status"] as? String {
                success = (status == "completed")
            } else {
                success = false
            }
            let summary = event["summary"] as? String ?? ""
            data.taskProgress?.status = success ? .completed : .failed
            data.taskProgress?.endTime = Date()
            data.taskProgress?.summary = summary
            data.isStreamingLLM = false

        case "task_stopped", "error":
            data.taskProgress?.status = .failed
            data.taskProgress?.endTime = Date()
            data.isStreamingLLM = false
            if let err = event["error"] as? String, !err.isEmpty {
                data.taskProgress?.summary = err
            } else if let msg = event["message"] as? String, !msg.isEmpty {
                data.taskProgress?.summary = msg
            }

        case "tool_call":
            // Chat 模式：工具调用开始
            let toolName = event["tool_name"] as? String ?? "unknown"
            let toolArgs = event["tool_args"] as? [String: Any] ?? [:]
            let paramsSummary = Self.buildParamsSummary(actionType: toolName, params: toolArgs)
            let actionId = "\(taskId)_tool_\(UUID().uuidString)"
            let logEntry = ActionLogEntry(
                actionId: actionId,
                actionType: toolName,
                reasoning: "调用 \(toolName)",
                status: .executing,
                output: nil,
                error: nil,
                timestamp: Date(),
                iteration: data.currentIteration,
                paramsSummary: paramsSummary
            )
            data.actionLogs.append(logEntry)

        case "tool_result":
            // Chat 模式：工具调用结果
            let toolName = event["tool_name"] as? String ?? "unknown"
            let success = event["success"] as? Bool ?? false
            let result = event["result"] as? String
            if let index = data.actionLogs.lastIndex(where: { $0.actionType == toolName && ($0.status == .executing || $0.status == .pending) }) {
                let e = data.actionLogs[index]
                data.actionLogs[index] = ActionLogEntry(
                    actionId: e.actionId,
                    actionType: toolName,
                    reasoning: e.reasoning,
                    status: success ? .success : .failed,
                    output: result,
                    error: success ? nil : result,
                    timestamp: e.timestamp,
                    iteration: e.iteration,
                    paramsSummary: e.paramsSummary
                )
            } else {
                let actionId = "\(taskId)_tool_\(UUID().uuidString)"
                let logEntry = ActionLogEntry(
                    actionId: actionId,
                    actionType: toolName,
                    reasoning: "调用 \(toolName)",
                    status: success ? .success : .failed,
                    output: result,
                    error: success ? nil : result,
                    timestamp: Date(),
                    iteration: data.currentIteration,
                    paramsSummary: nil
                )
                data.actionLogs.append(logEntry)
            }
            if var p = data.taskProgress {
                if success { p.successfulActions += 1 } else { p.failedActions += 1 }
                p.totalActions = p.successfulActions + p.failedActions
                data.taskProgress = p
            }

        default:
            break
        }

        tasks[taskId] = data
        _evictOldTasks()
        if data.taskProgress?.status == .running {
            _startMultiTaskElapsedTimer()
        }
    }

    private func _evictOldTasks() {
        // 截断每个任务的 actionLogs，避免无限增长导致 UI 卡顿
        let maxLogsPerTask = 200
        for (id, var data) in tasks {
            if data.actionLogs.count > maxLogsPerTask {
                data.actionLogs = Array(data.actionLogs.suffix(maxLogsPerTask))
                tasks[id] = data
            }
        }
        let finished = tasks.filter { $0.value.taskProgress?.status != .running }
        if finished.count > 20 {
            let sorted = finished.sorted { ($0.value.lastUpdated) < ($1.value.lastUpdated) }
            for (id, _) in sorted.prefix(finished.count - 20) {
                tasks.removeValue(forKey: id)
                if selectedTaskId == id { selectedTaskId = tasks.keys.first }
            }
        }
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
                    await fetchDeepHealth()
                    await fetchTraces()
                    await fetchActiveTasks()
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
        _stopMultiTaskElapsedTimer()
    }

    private func _startMultiTaskElapsedTimer() {
        _stopMultiTaskElapsedTimer()
        multiTaskElapsedTimer = Task {
            while !Task.isCancelled {
                let hasRunning = tasks.values.contains { $0.taskProgress?.status == .running }
                if hasRunning {
                    for (id, var data) in tasks {
                        if data.taskProgress?.status == .running, let start = data.taskProgress?.startTime {
                            data.taskElapsedSeconds = Int(Date().timeIntervalSince(start))
                            tasks[id] = data
                        }
                    }
                }
                try? await Task.sleep(nanoseconds: 1_000_000_000)
            }
        }
    }

    private func _stopMultiTaskElapsedTimer() {
        multiTaskElapsedTimer?.cancel()
        multiTaskElapsedTimer = nil
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

    // MARK: - Deep Health 拉取

    private func fetchDeepHealth() async {
        guard let url = URL(string: "\(baseURL)/health/deep") else { return }
        do {
            let (data, _) = try await httpSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                var dh = DeepHealthData()
                dh.healthy = json["healthy"] as? Bool ?? false
                dh.requiredFailed = json["required_failed"] as? [String] ?? []
                dh.checkDurationMs = json["check_duration_ms"] as? Double ?? 0
                dh.serverStatus = json["server_status"] as? String ?? "unknown"
                dh.timestamp = json["ts"] as? Double ?? 0

                if let checks = json["checks"] as? [String: [String: Any]] {
                    dh.checks = checks.map { key, val in
                        DeepHealthCheck(
                            id: key,
                            ok: val["ok"] as? Bool ?? false,
                            required: val["required"] as? Bool ?? false,
                            detail: val["detail"] as? String ?? "",
                            latencyMs: val["latency_ms"] as? Double
                        )
                    }.sorted { $0.id < $1.id }
                }
                deepHealth = dh
            }
        } catch {}
    }

    // MARK: - Traces 拉取

    func fetchTraces() async {
        guard let url = URL(string: "\(baseURL)/traces?limit=50") else { return }
        do {
            let (data, _) = try await httpSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let list = json["traces"] as? [[String: Any]] {
                traceList = list.compactMap { d -> TraceListItem? in
                    guard let taskId = d["task_id"] as? String else { return nil }
                    return TraceListItem(
                        id: taskId,
                        taskId: taskId,
                        sizeBytes: d["size_bytes"] as? Int ?? 0,
                        mtime: d["mtime"] as? Double ?? 0,
                        spanCount: d["span_count"] as? Int ?? 0
                    )
                }
            }
        } catch {}
    }

    func fetchActiveTasks() async {
        guard let url = URL(string: "\(baseURL)/monitor/active-tasks?recent_seconds=300") else { return }
        isLoadingActiveTasks = true
        defer { isLoadingActiveTasks = false }
        do {
            let (data, _) = try await httpSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let list = json["tasks"] as? [[String: Any]] {
                activeTaskList = list.compactMap { d -> ActiveTaskItem? in
                    guard let taskId = d["task_id"] as? String else { return nil }
                    return ActiveTaskItem(
                        id: taskId,
                        taskId: taskId,
                        sessionId: d["session_id"] as? String ?? "",
                        taskType: d["task_type"] as? String ?? "autonomous",
                        description: d["description"] as? String ?? "",
                        status: d["status"] as? String ?? "unknown",
                        createdAt: d["created_at"] as? Double ?? 0,
                        finishedAt: d["finished_at"] as? Double,
                        workerType: d["worker_type"] as? String,
                        workerId: d["worker_id"] as? String,
                        workerLabel: d["worker_label"] as? String
                    )
                }
            }
        } catch {}
    }

    func fetchTraceSummary(taskId: String) async {
        guard let url = URL(string: "\(baseURL)/traces/\(taskId)") else { return }
        isLoadingTraces = true
        defer { isLoadingTraces = false }
        do {
            let (data, _) = try await httpSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                var s = TraceSummaryData()
                s.taskId = json["task_id"] as? String ?? taskId
                s.exists = json["exists"] as? Bool ?? false
                s.totalSpans = json["total_spans"] as? Int ?? 0
                s.typeCounts = json["type_counts"] as? [String: Int] ?? [:]

                if let tok = json["tokens"] as? [String: Any] {
                    s.tokens.prompt = tok["prompt"] as? Int ?? 0
                    s.tokens.completion = tok["completion"] as? Int ?? 0
                    s.tokens.total = tok["total"] as? Int ?? 0
                }
                if let lat = json["latency"] as? [String: Any] {
                    s.latency.count = lat["count"] as? Int ?? 0
                    s.latency.minMs = lat["min_ms"] as? Double ?? 0
                    s.latency.maxMs = lat["max_ms"] as? Double ?? 0
                    s.latency.avgMs = lat["avg_ms"] as? Double ?? 0
                    s.latency.p90Ms = lat["p90_ms"] as? Double ?? 0
                }
                if let tc = json["tool_calls"] as? [String: Any] {
                    s.toolCalls.success = tc["success"] as? Int ?? 0
                    s.toolCalls.failure = tc["failure"] as? Int ?? 0
                }
                if let tl = json["timeline"] as? [String: Any] {
                    s.timeline.firstTs = tl["first_ts"] as? Double
                    s.timeline.lastTs = tl["last_ts"] as? Double
                    s.timeline.durationS = tl["duration_s"] as? Double
                }
                s.recentErrors = json["recent_errors"] as? [String] ?? []
                selectedTraceSummary = s
            }
        } catch {}
    }

    func fetchTraceSpans(taskId: String, offset: Int = 0, limit: Int = 200) async {
        guard let url = URL(string: "\(baseURL)/traces/\(taskId)/spans?offset=\(offset)&limit=\(limit)") else { return }
        isLoadingTraces = true
        defer { isLoadingTraces = false }
        do {
            let (data, _) = try await httpSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let spans = json["spans"] as? [[String: Any]] {
                selectedTraceSpans = spans.map { d in
                    let spanType = d["type"] as? String ?? "unknown"
                    let ts = d["ts"] as? Double ?? 0
                    let latMs = d["latency_ms"] as? Double ?? d["duration_ms"] as? Double
                    let success = d["success"] as? Bool

                    // 构建简短描述
                    var desc = ""
                    if spanType == "llm" {
                        let model = d["model"] as? String ?? ""
                        let usage = d["usage"] as? [String: Any]
                        let totalTok = usage?["total_tokens"] as? Int ?? d["total_tokens"] as? Int ?? 0
                        desc = "\(model) • \(totalTok)t"
                    } else if spanType == "tool" {
                        let toolName = d["tool"] as? String ?? d["name"] as? String ?? ""
                        desc = toolName
                    } else if spanType == "step" {
                        let action = d["action_type"] as? String ?? ""
                        desc = action
                    } else {
                        desc = d["message"] as? String ?? d["detail"] as? String ?? spanType
                    }
                    if let err = d["error"] as? String, !err.isEmpty {
                        desc += " ⚠️ \(String(err.prefix(60)))"
                    }

                    return TraceSpanItem(
                        type: spanType,
                        ts: ts,
                        latencyMs: latMs,
                        success: success,
                        detail: desc,
                        rawJSON: d
                    )
                }
            }
        } catch {}
    }

    func selectTrace(_ taskId: String) {
        selectedTraceTaskId = taskId
        Task {
            await fetchTraceSummary(taskId: taskId)
            await fetchTraceSpans(taskId: taskId)
        }
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
