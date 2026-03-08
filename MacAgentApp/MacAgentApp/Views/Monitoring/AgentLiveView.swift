import SwiftUI

// MARK: - Agent Live — Cyberdeck Terminal（赛博朋克神经接口风格，单一设计）

struct AgentLiveView: View {
    @EnvironmentObject var vm: MonitoringViewModel

    private var taskList: [TaskMonitorData] {
        Array(Array(vm.tasks.values)
            .sorted { ($0.lastUpdated) > ($1.lastUpdated) }
            .prefix(4))
    }

    private var isMultiTask: Bool {
        vm.tasks.count >= 2
    }

    var body: some View {
        if isMultiTask {
            MultiTaskLiveView(tasks: taskList, executionLogs: vm.executionLogs)
        } else {
            SingleTaskLiveView()
                .environmentObject(vm)
        }
    }
}

// MARK: - 单任务 Live（原有逻辑）

private struct SingleTaskLiveView: View {
    @EnvironmentObject var vm: MonitoringViewModel

    private var isThinking: Bool {
        vm.isStreamingLLM || vm.currentTaskData?.isStreamingLLM == true
    }

    private var lastActionType: String? {
        let logs = vm.currentTaskData?.actionLogs ?? vm.actionLogs
        return logs.last(where: { $0.actionType != "llm_request" })?.actionType
    }

    private var displayTool: String? {
        vm.recentToolCalls.last?.name ?? lastActionType
    }

    private var actionLogs: [ActionLogEntry] {
        vm.currentTaskData?.actionLogs ?? vm.actionLogs
    }

    private var currentIteration: Int {
        vm.currentTaskData?.currentIteration ?? vm.currentIteration
    }

    private var taskProgress: TaskProgress? {
        vm.currentTaskData?.taskProgress ?? vm.taskProgress
    }

    private var llmStreamingText: String {
        vm.currentTaskData?.llmStreamingText ?? vm.llmStreamingText
    }

    var body: some View {
        CyberdeckTerminalView(
            isThinking: isThinking,
            lastToolCall: vm.recentToolCalls.last,
            displayTool: displayTool,
            actionLogs: actionLogs,
            currentIteration: currentIteration,
            taskProgress: taskProgress,
            llmStreamingText: llmStreamingText,
            executionLogs: vm.executionLogs,
            compact: false
        )
    }
}

// MARK: - 多任务并行展示（方案 B：分栏 + 可折叠）

private struct MultiTaskLiveView: View {
    let tasks: [TaskMonitorData]
    let executionLogs: [ExecutionLogEntry]

    /// 已折叠的任务 ID（折叠后仅显示为顶部按钮，点击可再次展开）
    @State private var collapsedTaskIds: Set<String> = []

    private var expandedTasks: [TaskMonitorData] {
        tasks.filter { !collapsedTaskIds.contains($0.id) }
    }

    var body: some View {
        VStack(spacing: 0) {
            // 顶部：标题 + 任务名称按钮（点击切换展开/折叠）
            VStack(spacing: 0) {
                HStack(spacing: 8) {
                    Text("LIVE")
                        .font(CyberFont.mono(size: 10, weight: .bold))
                        .foregroundColor(CyberColor.cyan)
                    Text("·")
                        .foregroundColor(CyberColor.textSecond.opacity(0.6))
                    Text("\(tasks.count) 任务")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                    Spacer()
                }
                .padding(.vertical, 6)

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(tasks) { task in
                            TaskTabButton(
                                task: task,
                                isExpanded: !collapsedTaskIds.contains(task.id),
                                onTap: { collapsedTaskIds.formSymmetricDifference([task.id]) }
                            )
                        }
                    }
                    .padding(.horizontal, 4)
                }
                .frame(height: 28)
            }
            .background(CyberColor.bg1.opacity(0.8))

            Rectangle().fill(CyberColor.border).frame(height: 1)

            // 分栏：仅展示展开的任务
            if expandedTasks.isEmpty {
                VStack(spacing: 8) {
                    Text("点击上方任务名称展开")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond.opacity(0.6))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                HStack(spacing: 0) {
                    ForEach(expandedTasks) { task in
                        TaskLiveColumn(data: task, executionLogs: executionLogs)
                            .frame(maxWidth: .infinity)
                        if task.id != expandedTasks.last?.id {
                            Rectangle().fill(CyberColor.border).frame(width: 1)
                        }
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .onAppear {
            _autoCollapseStoppedTasks()
        }
        .onChange(of: tasks.map { "\($0.id):\($0.taskProgress.flatMap { $0.status.rawValue } ?? "")" }) { _, _ in
            _autoCollapseStoppedTasks()
        }
    }

    /// 已停止的任务自动折叠，避免占用展示位
    private func _autoCollapseStoppedTasks() {
        var updated = collapsedTaskIds
        for task in tasks {
            if task.taskProgress?.status != .running && task.taskProgress?.status != nil {
                updated.insert(task.id)
            }
        }
        collapsedTaskIds = updated
    }
}

// MARK: - 任务标签按钮（顶部，点击切换展开/折叠）

private struct TaskTabButton: View {
    let task: TaskMonitorData
    let isExpanded: Bool
    let onTap: () -> Void

    private var labelText: String {
        let desc = task.taskProgress?.taskDescription ?? String(task.id.prefix(8))
        let statusStr: String
        if let s = task.taskProgress?.status {
            switch s {
            case .running: statusStr = "运行中"
            case .completed: statusStr = "已完成"
            case .failed: statusStr = "失败"
            }
        } else {
            statusStr = "--"
        }
        return "\(String(desc.prefix(16)))\(desc.count > 16 ? "…" : "") (\(statusStr))"
    }

    private var statusColor: Color {
        switch task.taskProgress?.status {
        case .running: return actorAccentColor
        case .completed: return CyberColor.green
        case .failed: return CyberColor.red
        default: return CyberColor.textSecond
        }
    }

    /// Duck 任务用橙色，RPA 用紫色，主 Agent 用青色
    private var actorAccentColor: Color {
        switch task.workerType {
        case "local_duck", "remote_duck": return CyberColor.purple
        case "runbook": return CyberColor.orange
        default: return CyberColor.cyan
        }
    }

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 4) {
                // Duck / RPA 任务显示小图标
                if task.workerType != "main" {
                    Image(systemName: task.workerType.contains("duck") ? "bird" : "doc.text.fill")
                        .font(.system(size: 8))
                        .foregroundColor(actorAccentColor)
                }
                Text(labelText)
                    .font(CyberFont.mono(size: 9))
                    .foregroundColor(isExpanded ? actorAccentColor : statusColor)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(
                RoundedRectangle(cornerRadius: 4)
                    .fill(isExpanded ? actorAccentColor.opacity(0.15) : CyberColor.bg1.opacity(0.6))
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(isExpanded ? actorAccentColor.opacity(0.5) : CyberColor.border.opacity(0.5), lineWidth: 1)
                    )
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - 单任务分栏（紧凑终端）

private struct TaskLiveColumn: View {
    let data: TaskMonitorData
    let executionLogs: [ExecutionLogEntry]

    private var displayTool: String? {
        data.actionLogs.last(where: { $0.actionType != "llm_request" })?.actionType
    }

    var body: some View {
        CyberdeckTerminalView(
            isThinking: data.isStreamingLLM,
            lastToolCall: nil,
            displayTool: displayTool,
            actionLogs: data.actionLogs,
            currentIteration: data.currentIteration,
            taskProgress: data.taskProgress,
            llmStreamingText: data.llmStreamingText,
            executionLogs: executionLogs,
            compact: true,
            taskLabel: taskLabelText
        )
    }

    private var taskLabelText: String {
        let desc = data.taskProgress?.taskDescription ?? String(data.id.prefix(8))
        let statusStr: String
        if let s = data.taskProgress?.status {
            switch s {
            case .running: statusStr = "运行中"
            case .completed: statusStr = "已完成"
            case .failed: statusStr = "失败"
            }
        } else {
            statusStr = "--"
        }
        // 在标题中插入执行者标签（Duck[xxx] 或主 Agent）
        let actorPrefix = data.workerType != "main" ? "\(data.workerLabel) · " : ""
        return "\(actorPrefix)\(String(desc.prefix(16)))\(desc.count > 16 ? "…" : "") (\(statusStr))"
    }
}

// MARK: - Cyberdeck Terminal 主视图

private struct CyberdeckTerminalView: View {
    let isThinking: Bool
    let lastToolCall: ToolCall?
    let displayTool: String?
    let actionLogs: [ActionLogEntry]
    let currentIteration: Int
    let taskProgress: TaskProgress?
    let llmStreamingText: String
    let executionLogs: [ExecutionLogEntry]
    var compact: Bool = false
    var taskLabel: String? = nil

    var body: some View {
        GeometryReader { geo in
            let pad: CGFloat = compact ? 12 : 16
            let contentW = geo.size.width - (compact ? 16 : 32)
            let contentH = geo.size.height - (compact ? 16 : 32)
            ZStack {
                // 1. 背景：双层网格（一层向左上快移，一层向右下慢移）
                CyberdeckBackground(size: CGSize(width: contentW, height: contentH))

                // 2. 终端内容
                VStack(alignment: .leading, spacing: compact ? 4 : 8) {
                    if let label = taskLabel {
                        Text(label)
                            .font(CyberFont.mono(size: compact ? 8 : 9))
                            .foregroundColor(CyberColor.cyan.opacity(0.9))
                            .lineLimit(1)
                            .truncationMode(.tail)
                    }
                    TerminalHeader(isThinking: isThinking, displayTool: displayTool, currentIteration: currentIteration, taskProgress: taskProgress, compact: compact)
                    Spacer().frame(height: compact ? 4 : 8)
                    TerminalContent(
                        isThinking: isThinking,
                        lastToolCall: lastToolCall,
                        displayTool: displayTool,
                        actionLogs: actionLogs,
                        currentIteration: currentIteration,
                        taskProgress: taskProgress,
                        llmStreamingText: llmStreamingText,
                        executionLogs: executionLogs,
                        compact: compact
                    )
                    Spacer()
                }
                .padding(.horizontal, compact ? 12 : 24)
                .frame(width: contentW, height: contentH)

                // 4. 边框 + 角标（2077 风格）- 使用内容区尺寸
                ZStack(alignment: .topLeading) {
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(
                            isThinking ? CyberColor.purple : CyberColor.cyan,
                            lineWidth: 1
                        )
                        .opacity(isThinking ? 0.9 : 0.5)
                    CornerBrackets(size: CGSize(width: contentW, height: contentH), color: isThinking ? CyberColor.purple : CyberColor.cyan)
                }
                .frame(width: contentW, height: contentH)

                // 5. 状态脉动（思考时中心光晕）
                if isThinking {
                    Circle()
                        .fill(CyberColor.purple.opacity(0.08))
                        .frame(width: 120, height: 120)
                        .blur(radius: 30)
                        .position(x: contentW / 2, y: contentH / 2)
                }
            }
            .padding(compact ? 8 : 16)
        }
    }
}

// MARK: - 工具名 → 中文显示

private func toolDisplayName(_ raw: String?) -> String? {
    guard let t = raw?.lowercased() else { return nil }
    if t.contains("web_search") || t.contains("search") { return "网络搜索" }
    if t.contains("run_shell") || t.contains("shell") { return "终端" }
    if t.contains("create_and_run") { return "脚本" }
    if t.contains("read_file") || t.contains("write_file") || t.contains("list_directory") || t.contains("file") || t.contains("file_operations") { return "文件" }
    if t.contains("screenshot") { return "截图" }
    if t.contains("mail") { return "邮件" }
    if t.contains("call_tool") { return "工具调用" }
    return raw?.uppercased().replacingOccurrences(of: "_", with: " ") ?? nil
}

/// 从 ActionLogEntry 获取工具显示名（call_tool 时从 paramsSummary 解析）
private func toolDisplayNameForEntry(_ entry: ActionLogEntry) -> String {
    if entry.actionType == "call_tool", let ps = entry.paramsSummary, !ps.isEmpty {
        let first = ps.split(separator: " ").first.map(String.init) ?? ps
        return toolDisplayName(first) ?? first
    }
    return toolDisplayName(entry.actionType) ?? entry.actionType
}

// MARK: - 赛博朋克打字效果（病毒植入风格，快速逐字出现）

private struct CyberTypingText: View {
    let text: String
    var charDelayMs: Int = 18
    var useAdaptiveDelay: Bool = true  // 文本越长，单字延迟越短
    var showCursor: Bool = true
    var cursorColor: Color = CyberColor.cyan
    var textColor: Color = CyberColor.textPrimary
    var fontSize: CGFloat = 10
    @State private var visibleCount: Int = 0
    @State private var cursorBlink: Bool = false

    private var effectiveDelayMs: Int {
        guard useAdaptiveDelay, text.count > 0 else { return charDelayMs }
        // 文本越长越快：100字约10ms，200字约6ms，50字约18ms
        return max(4, min(charDelayMs, 28 - text.count / 8))
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            Text(String(text.prefix(visibleCount)))
                .font(CyberFont.mono(size: fontSize))
                .foregroundColor(textColor)
            if showCursor {
                Text("_")
                    .font(CyberFont.mono(size: fontSize))
                    .foregroundColor(cursorBlink ? cursorColor : cursorColor.opacity(0.4))
            }
        }
        .onAppear { startTyping() }
        .onChange(of: text) { _, _ in
            visibleCount = 0
            startTyping()
        }
        .onAppear { withAnimation(.easeInOut(duration: 0.4).repeatForever(autoreverses: true)) { cursorBlink = true } }
    }

    private func startTyping() {
        guard !text.isEmpty else { return }
        let delay = UInt64(effectiveDelayMs) * 1_000_000
        Task { @MainActor in
            for i in 0..<text.count {
                visibleCount = i + 1
                try? await Task.sleep(nanoseconds: delay)
            }
        }
    }
}

// MARK: - 角标（2077 风格 L 形装饰）

private struct CornerBrackets: View {
    let size: CGSize
    let color: Color
    var body: some View {
        let w: CGFloat = 20
        let t: CGFloat = 2
        let pad: CGFloat = 16
        Path { p in
            p.move(to: CGPoint(x: pad, y: pad)); p.addLine(to: CGPoint(x: pad + w, y: pad)); p.addLine(to: CGPoint(x: pad + w, y: pad + t))
            p.move(to: CGPoint(x: pad, y: pad)); p.addLine(to: CGPoint(x: pad, y: pad + w)); p.addLine(to: CGPoint(x: pad + t, y: pad + w))
            p.move(to: CGPoint(x: size.width - pad, y: pad)); p.addLine(to: CGPoint(x: size.width - pad - w, y: pad)); p.addLine(to: CGPoint(x: size.width - pad - w, y: pad + t))
            p.move(to: CGPoint(x: size.width - pad, y: pad)); p.addLine(to: CGPoint(x: size.width - pad, y: pad + w)); p.addLine(to: CGPoint(x: size.width - pad - t, y: pad + w))
            p.move(to: CGPoint(x: pad, y: size.height - pad)); p.addLine(to: CGPoint(x: pad + w, y: size.height - pad)); p.addLine(to: CGPoint(x: pad + w, y: size.height - pad - t))
            p.move(to: CGPoint(x: pad, y: size.height - pad)); p.addLine(to: CGPoint(x: pad, y: size.height - pad - w)); p.addLine(to: CGPoint(x: pad + t, y: size.height - pad - w))
            p.move(to: CGPoint(x: size.width - pad, y: size.height - pad)); p.addLine(to: CGPoint(x: size.width - pad - w, y: size.height - pad)); p.addLine(to: CGPoint(x: size.width - pad - w, y: size.height - pad - t))
            p.move(to: CGPoint(x: size.width - pad, y: size.height - pad)); p.addLine(to: CGPoint(x: size.width - pad, y: size.height - pad - w)); p.addLine(to: CGPoint(x: size.width - pad - t, y: size.height - pad - w))
        }
        .stroke(color, lineWidth: 1)
        .opacity(0.7)
    }
}

// MARK: - 网格背景（ bounded 绘制防 CPU 爆满 + 30fps）

private struct CyberdeckBackground: View {
    let size: CGSize

    var body: some View {
        ZStack {
            Color.black.opacity(0.6)
            DualAnimatedGridView()
        }
        .frame(width: size.width, height: size.height)
    }
}

/// 单层网格：从左上向右下缓慢移动。offset 取模 + 仅绘制可见区域，避免 CPU 100%。
private struct DualAnimatedGridView: View {
    private let gridSize: CGFloat = 24
    private let lineColor = CyberColor.cyan.opacity(0.12)
    private let accentLineColor = CyberColor.cyan.opacity(0.22)

    var body: some View {
        TimelineView(.animation(minimumInterval: 1/30)) { ctx in
            let t = ctx.date.timeIntervalSinceReferenceDate
            // offset 取模，保证绘制数量有界
            let offset = CGFloat((t * 4).truncatingRemainder(dividingBy: Double(gridSize)))
            GridLayer(
                offset: offset,
                gridSize: gridSize,
                lineColor: lineColor.opacity(0.8),
                accentLineColor: accentLineColor.opacity(0.8)
            )
        }
        .opacity(0.7)
    }
}

/// 仅绘制可见范围内的网格线，迭代次数有界，避免 offset 过大时 CPU 爆满。
private struct GridLayer: View {
    let offset: CGFloat
    let gridSize: CGFloat
    let lineColor: Color
    let accentLineColor: Color

    var body: some View {
        Canvas { ctx, canvasSize in
            let w = canvasSize.width
            let h = canvasSize.height
            let kMinX = Int(ceil((-gridSize - offset) / gridSize))
            let kMaxX = Int(floor((w + gridSize - offset) / gridSize))
            for k in stride(from: kMinX, through: kMaxX, by: 1) {
                let x = offset + CGFloat(k) * gridSize
                let isAccent = (k % 2) == 0
                ctx.stroke(
                    Path { p in
                        p.move(to: CGPoint(x: x, y: 0))
                        p.addLine(to: CGPoint(x: x, y: h))
                    },
                    with: .color(isAccent ? accentLineColor : lineColor),
                    lineWidth: 0.5
                )
            }
            let kMinY = Int(ceil((-gridSize - offset) / gridSize))
            let kMaxY = Int(floor((h + gridSize - offset) / gridSize))
            for k in stride(from: kMinY, through: kMaxY, by: 1) {
                let y = offset + CGFloat(k) * gridSize
                let isAccent = (k % 2) == 0
                ctx.stroke(
                    Path { p in
                        p.move(to: CGPoint(x: 0, y: y))
                        p.addLine(to: CGPoint(x: w, y: y))
                    },
                    with: .color(isAccent ? accentLineColor : lineColor),
                    lineWidth: 0.5
                )
            }
        }
    }
}

// MARK: - 终端头部

private struct TerminalHeader: View {
    let isThinking: Bool
    let displayTool: String?
    let currentIteration: Int
    let taskProgress: TaskProgress?
    var compact: Bool = false

    var body: some View {
        let sz: CGFloat = compact ? 8 : 9
        VStack(alignment: .leading, spacing: compact ? 4 : 6) {
            HStack(spacing: compact ? 6 : 12) {
                Text("MACAGENT")
                    .font(CyberFont.mono(size: sz, weight: .bold))
                    .foregroundColor(CyberColor.cyan)
                Text("|")
                    .font(CyberFont.mono(size: sz))
                    .foregroundColor(CyberColor.textSecond.opacity(0.6))
                Text("NEURAL LINK")
                    .font(CyberFont.mono(size: sz))
                    .foregroundColor(CyberColor.textSecond)
                if isThinking {
                    Text("•")
                        .font(CyberFont.mono(size: sz + 1))
                        .foregroundColor(CyberColor.purple)
                    Text("ACTIVE")
                        .font(CyberFont.mono(size: sz))
                        .foregroundColor(CyberColor.purple)
                } else if displayTool != nil {
                    Text("•")
                        .font(CyberFont.mono(size: sz + 1))
                        .foregroundColor(CyberColor.orange)
                    Text("EXEC")
                        .font(CyberFont.mono(size: sz))
                        .foregroundColor(CyberColor.orange)
                }
            }
            if currentIteration > 0 || (taskProgress?.totalActions ?? 0) > 0 {
                HStack(spacing: compact ? 8 : 16) {
                    Text("ITER: \(currentIteration)")
                        .font(CyberFont.mono(size: sz))
                        .foregroundColor(CyberColor.textSecond.opacity(0.8))
                    if let p = taskProgress, p.totalActions > 0 {
                        Text("ACTIONS: \(p.successfulActions)/\(p.totalActions)")
                            .font(CyberFont.mono(size: sz))
                            .foregroundColor(CyberColor.green.opacity(0.9))
                    }
                }
            }
        }
    }
}

// MARK: - 终端内容

private struct TerminalContent: View {
    let isThinking: Bool
    let lastToolCall: ToolCall?
    let displayTool: String?
    let actionLogs: [ActionLogEntry]
    let currentIteration: Int
    let taskProgress: TaskProgress?
    let llmStreamingText: String
    let executionLogs: [ExecutionLogEntry]
    var compact: Bool = false

    private var commandLine: String {
        guard let t = displayTool else { return "" }
        return t.uppercased().replacingOccurrences(of: "_", with: " ")
    }

    private var argsPreview: String {
        guard let call = lastToolCall, !call.arguments.isEmpty else { return "" }
        let keys = ["command", "action", "path", "file_path", "url"]
        for k in keys {
            if let v = call.arguments[k] {
                let val = String(describing: v.value)
                return val.count > 50 ? String(val.prefix(47)) + "…" : val
            }
        }
        if let (_, v) = call.arguments.first {
            return String(describing: v.value)
        }
        return ""
    }

    private var terminalOutput: String? {
        guard let call = lastToolCall else { return nil }
        let n = call.name.lowercased()
        guard n.contains("terminal") || n.contains("exec") || n.contains("shell") || n.contains("run_") else { return nil }
        guard let out = call.result?.output, !out.isEmpty else { return nil }
        let lines = out.split(separator: "\n", omittingEmptySubsequences: false)
        let lastLines = Array(lines.suffix(5))
        var s = lastLines.joined(separator: "\n")
        if s.count > 200 { s = String(s.prefix(197)) + "…" }
        return s
    }

    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(alignment: .leading, spacing: compact ? 6 : 12) {
                if isThinking {
                    ThinkingBlock(llmStreamingText: llmStreamingText, currentIteration: currentIteration)
                } else if displayTool != nil {
                    ExecBlock(commandLine: commandLine, argsPreview: argsPreview, terminalOutput: terminalOutput, lastToolCall: lastToolCall, actionLogs: actionLogs, currentIteration: currentIteration)
                } else {
                    IdleBlock(taskProgress: taskProgress)
                }

                // 执行输出流（单任务模式；多任务时 executionLogs 为全局混合，暂不展示）
                if !compact && !executionLogs.isEmpty {
                    ExecutionStreamBlock(executionLogs: executionLogs)
                }

                // 动作日志（打字效果，大脑→[工具] 在对应 log 行内）
                if !actionLogs.isEmpty {
                    ActionLogBlock(actionLogs: actionLogs)
                }
            }
        }
        .frame(maxHeight: .infinity)
    }
}

// MARK: - 内联 大脑→[工具] 块（融合到终端输出）

private struct BrainToToolInlineBlock: View {
    let toolName: String

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "brain.head.profile")
                .font(.system(size: 12))
                .foregroundColor(CyberColor.cyan)
            TimelineView(.animation(minimumInterval: 0.08)) { ctx in
                let phase = (ctx.date.timeIntervalSinceReferenceDate * 2).truncatingRemainder(dividingBy: 1.0)
                Text("──")
                    .font(CyberFont.mono(size: 10))
                    .foregroundColor(CyberColor.orange.opacity(0.6 + phase * 0.4))
                Text("▶")
                    .font(CyberFont.mono(size: 9))
                    .foregroundColor(CyberColor.orange)
            }
            Text("[\(toolName)]")
                .font(CyberFont.mono(size: 10))
                .foregroundColor(CyberColor.orange)
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 8)
        .background(CyberColor.bg1.opacity(0.6))
        .cornerRadius(4)
    }
}

private struct IdleBlock: View {
    let taskProgress: TaskProgress?
    @State private var blink = false

    private var statusText: String {
        guard let p = taskProgress else { return "STANDBY" }
        switch p.status {
        case .running: return "STANDBY"
        case .completed: return "COMPLETED"
        case .failed: return "FAILED"
        }
    }

    private var statusColor: Color {
        guard let p = taskProgress else { return CyberColor.textSecond }
        switch p.status {
        case .running: return CyberColor.textSecond
        case .completed: return CyberColor.green
        case .failed: return CyberColor.red
        }
    }

    private var messageText: String {
        guard let p = taskProgress else { return "Awaiting task input..." }
        switch p.status {
        case .running: return "Awaiting task input..."
        case .completed:
            if let s = p.summary, !s.isEmpty { return String(s.prefix(120)) + (s.count > 120 ? "…" : "") }
            return "任务已完成"
        case .failed:
            if let s = p.summary, !s.isEmpty { return String(s.prefix(120)) + (s.count > 120 ? "…" : "") }
            return "任务执行失败"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 4) {
                Text(">")
                    .foregroundColor(CyberColor.cyan)
                Text(statusText)
                    .font(CyberFont.mono(size: 11))
                    .foregroundColor(statusColor)
                Text("_")
                    .font(CyberFont.mono(size: 11))
                    .foregroundColor(blink ? CyberColor.cyan : .clear)
            }
            if let p = taskProgress, !p.taskDescription.isEmpty {
                Text("[TASK] \(String(p.taskDescription.prefix(60)))\(p.taskDescription.count > 60 ? "…" : "")")
                    .font(CyberFont.mono(size: 10))
                    .foregroundColor(CyberColor.textSecond.opacity(0.8))
            }
            CyberTypingText(
                text: messageText,
                charDelayMs: 25,
                showCursor: false,
                textColor: (taskProgress?.status == .failed ? CyberColor.red : CyberColor.textSecond).opacity(0.8),
                fontSize: 10
            )
        }
        .onAppear { withAnimation(.easeInOut(duration: 0.6).repeatForever(autoreverses: true)) { blink = true } }
    }
}

private struct ThinkingBlock: View {
    let llmStreamingText: String
    let currentIteration: Int
    @State private var blink = false

    var body: some View {
        TimelineView(.animation(minimumInterval: 0.35)) { ctx in
            let dotCount = Int(ctx.date.timeIntervalSinceReferenceDate / 0.35) % 3
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 4) {
                    Text(">")
                        .foregroundColor(CyberColor.purple)
                    Text("PROCESSING")
                        .font(CyberFont.mono(size: 11))
                        .foregroundColor(CyberColor.purple)
                    Text(String(repeating: ".", count: dotCount + 1))
                        .font(CyberFont.mono(size: 11))
                        .foregroundColor(CyberColor.purple)
                    Text("_")
                        .font(CyberFont.mono(size: 11))
                        .foregroundColor(blink ? CyberColor.purple : .clear)
                }
                if currentIteration > 0 {
                    Text("Iteration #\(currentIteration) | Neural inference...")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond.opacity(0.7))
                } else {
                    Text("Neural inference in progress...")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond.opacity(0.7))
                }
                if !llmStreamingText.isEmpty {
                    Text(String(llmStreamingText.suffix(120)))
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.purple.opacity(0.6))
                        .lineLimit(3)
                        .truncationMode(.tail)
                }
            }
        }
        .onAppear { withAnimation(.easeInOut(duration: 0.5).repeatForever(autoreverses: true)) { blink = true } }
    }
}

private struct ExecBlock: View {
    let commandLine: String
    let argsPreview: String
    let terminalOutput: String?
    let lastToolCall: ToolCall?
    let actionLogs: [ActionLogEntry]
    let currentIteration: Int
    @State private var blink = false

    private var statusIcon: String {
        guard let call = lastToolCall else { return "circle" }
        if call.result == nil { return "arrow.triangle.2.circlepath" }
        return call.result!.success ? "checkmark.circle" : "xmark.circle"
    }

    private var statusColor: Color {
        guard let call = lastToolCall else { return CyberColor.orange }
        if call.result == nil { return CyberColor.orange }
        return call.result!.success ? CyberColor.green : CyberColor.red
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 4) {
                Text(">")
                    .foregroundColor(CyberColor.cyan)
                Text("EXECUTE")
                    .font(CyberFont.mono(size: 11))
                    .foregroundColor(CyberColor.cyan)
                Text(":")
                    .foregroundColor(CyberColor.cyan)
                CyberTypingText(
                    text: commandLine,
                    charDelayMs: 12,
                    showCursor: true,
                    cursorColor: CyberColor.cyan,
                    textColor: CyberColor.orange,
                    fontSize: 11
                )
                Image(systemName: statusIcon)
                    .font(.system(size: 10))
                    .foregroundColor(statusColor)
                Text("_")
                    .font(CyberFont.mono(size: 11))
                    .foregroundColor(blink ? CyberColor.cyan : .clear)
            }

            if currentIteration > 0 {
                Text("Iteration #\(currentIteration)")
                    .font(CyberFont.mono(size: 9))
                    .foregroundColor(CyberColor.textSecond.opacity(0.7))
            }

            if !argsPreview.isEmpty {
                CyberTypingText(
                    text: argsPreview,
                    charDelayMs: 14,
                    showCursor: false,
                    textColor: CyberColor.textSecond,
                    fontSize: 10
                )
            }

            if let out = terminalOutput {
                VStack(alignment: .leading, spacing: 4) {
                    Text("[OUTPUT]")
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond.opacity(0.8))
                    CyberTypingText(
                        text: out,
                        charDelayMs: 12,
                        showCursor: false,
                        textColor: CyberColor.green.opacity(0.95),
                        fontSize: 10
                    )
                }
                .padding(8)
                .background(CyberColor.bg1.opacity(0.8))
                .cornerRadius(6)
            }
        }
        .onAppear { withAnimation(.easeInOut(duration: 0.6).repeatForever(autoreverses: true)) { blink = true } }
    }
}

// MARK: - 执行输出流（病毒植入风格打字效果）

private struct ExecutionStreamBlock: View {
    let executionLogs: [ExecutionLogEntry]

    private var recentLogs: [ExecutionLogEntry] {
        Array(executionLogs.suffix(12))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("[STREAM]")
                .font(CyberFont.mono(size: 9))
                .foregroundColor(CyberColor.cyan.opacity(0.9))
            ForEach(recentLogs) { log in
                VStack(alignment: .leading, spacing: 4) {
                    // 大脑→[工具] 动画：每条 STREAM 日志对应一个工具执行
                    if let toolName = toolDisplayName(log.toolName) {
                        BrainToToolInlineBlock(toolName: toolName)
                    }
                    HStack(spacing: 6) {
                        Text(log.toolName.uppercased())
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(CyberColor.orange)
                        Text(log.level)
                            .font(CyberFont.mono(size: 8))
                            .foregroundColor(CyberColor.textSecond.opacity(0.6))
                    }
                    CyberTypingText(
                        text: log.message,
                        charDelayMs: 16,
                        showCursor: false,
                        textColor: log.level == "error" ? CyberColor.red.opacity(0.95) : CyberColor.green.opacity(0.95)
                    )
                    .lineLimit(6)
                    .truncationMode(.tail)
                }
                .padding(6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(CyberColor.bg1.opacity(0.7))
                .cornerRadius(4)
            }
        }
    }
}

// MARK: - 动作日志块（病毒植入风格打字效果）

private struct ActionLogBlock: View {
    let actionLogs: [ActionLogEntry]

    private var recentLogs: [ActionLogEntry] {
        let filtered = actionLogs.filter { $0.actionType != "llm_request" }
        return Array(filtered.suffix(8))
    }

    /// 当前「活跃」条目：正在执行或即将执行（pending 且为最近一条）
    private var activeEntryId: String? {
        let logs = Array(recentLogs.reversed())
        if let exec = logs.first(where: { $0.status == .executing }) { return exec.actionId }
        if let pend = logs.first(where: { $0.status == .pending }) { return pend.actionId }
        return nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("[LOG]")
                .font(CyberFont.mono(size: 9))
                .foregroundColor(CyberColor.textSecond.opacity(0.8))
            ForEach(Array(recentLogs.reversed()), id: \.actionId) { entry in
                VStack(alignment: .leading, spacing: 4) {
                    // 大脑→[工具] 动画：执行中或待执行（最近一条 pending）时显示
                    if entry.actionId == activeEntryId {
                        BrainToToolInlineBlock(toolName: toolDisplayNameForEntry(entry))
                    }
                    HStack(alignment: .top, spacing: 8) {
                        Text(statusSymbol(entry.status))
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(statusColor(entry.status))
                            .frame(width: 12, alignment: .leading)
                        Text(entry.actionType.uppercased().replacingOccurrences(of: "_", with: " "))
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(CyberColor.cyan.opacity(0.9))
                        if let ps = entry.paramsSummary, !ps.isEmpty {
                            Text("→")
                                .foregroundColor(CyberColor.textSecond.opacity(0.5))
                            CyberTypingText(
                                text: ps,
                                charDelayMs: 14,
                                showCursor: false,
                                textColor: CyberColor.orange.opacity(0.95)
                            )
                            .lineLimit(2)
                            .truncationMode(.tail)
                        }
                    }
                    if let out = entry.output, !out.isEmpty {
                        CyberTypingText(
                            text: out,
                            charDelayMs: 14,
                            showCursor: false,
                            textColor: CyberColor.green.opacity(0.9)
                        )
                        .lineLimit(4)
                        .truncationMode(.tail)
                        .padding(.leading, 20)
                    }
                    if let err = entry.error, !err.isEmpty {
                        CyberTypingText(
                            text: err,
                            charDelayMs: 14,
                            showCursor: false,
                            textColor: CyberColor.red.opacity(0.9)
                        )
                        .lineLimit(2)
                        .truncationMode(.tail)
                        .padding(.leading, 20)
                    }
                }
                .padding(6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(CyberColor.bg1.opacity(0.5))
                .cornerRadius(4)
            }
        }
    }

    private func statusSymbol(_ s: ActionLogEntry.ActionStatus) -> String {
        switch s {
        case .pending: return "○"
        case .executing: return "◐"
        case .success: return "✓"
        case .failed: return "✗"
        }
    }

    private func statusColor(_ s: ActionLogEntry.ActionStatus) -> Color {
        switch s {
        case .pending: return CyberColor.textSecond
        case .executing: return CyberColor.orange
        case .success: return CyberColor.green
        case .failed: return CyberColor.red
        }
    }
}
