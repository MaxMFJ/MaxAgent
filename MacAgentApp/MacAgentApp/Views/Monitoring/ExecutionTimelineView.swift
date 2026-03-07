import SwiftUI

// MARK: - Tab1: AI 执行过程可视化 (Cyberpunk + Neural Stream)

struct ExecutionTimelineView: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        if !vm.hasAnyTaskData {
            EmptyTimelineView()
        } else {
            HSplitView {
                // 左侧：任务列表 + 视图切换
                TaskListSidebar()
                    .environmentObject(vm)
                    .frame(minWidth: 200, maxWidth: 260)

                // 中间：执行时间轴
                TimelineScrollView()
                    .environmentObject(vm)
                    .frame(minWidth: 320)

                // 右侧：Neural Stream 面板 + 仪表盘
                VStack(spacing: 0) {
                    if _showNeuralStream {
                        NeuralStreamPanel(text: _neuralStreamText, isActive: _isStreaming)
                            .frame(minHeight: 120, maxHeight: 200)
                            .transition(.opacity.combined(with: .move(edge: .top)))
                    }
                    TimelineSidebar()
                        .environmentObject(vm)
                        .frame(maxWidth: .infinity)
                }
                .frame(minWidth: 200, maxWidth: 260)
            }
        }
    }

    private var _showNeuralStream: Bool { _isStreaming || !_neuralStreamText.isEmpty }
    private var _isStreaming: Bool {
        vm.isStreamingLLM || vm.currentTaskData?.isStreamingLLM == true
    }
    private var _neuralStreamText: String {
        vm.currentTaskData?.llmStreamingText ?? vm.llmStreamingText
    }
}

// MARK: - 左侧任务列表

private struct TaskListSidebar: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        VStack(spacing: 0) {
            // 视图模式切换
            HStack(spacing: 8) {
                Picker("", selection: $vm.viewMode) {
                    Text("单任务").tag(MonitoringViewModel.ExecutionViewMode.single)
                    Text("全部").tag(MonitoringViewModel.ExecutionViewMode.all)
                }
                .pickerStyle(.segmented)
                .labelsHidden()
            }
            .padding(12)

            Rectangle().fill(CyberColor.border).frame(height: 1)

            // 任务列表（优先用 tasks，否则用 activeTaskList）
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 4) {
                    if !vm.tasks.isEmpty {
                        ForEach(Array(vm.tasks.values).sorted { ($0.lastUpdated) > ($1.lastUpdated) }) { data in
                            TaskListRow(
                                data: data,
                                isSelected: vm.selectedTaskId == data.id,
                                onClick: { vm.selectedTaskId = data.id }
                            )
                        }
                    } else if !vm.activeTaskList.isEmpty {
                        ForEach(vm.activeTaskList) { item in
                            ActiveTaskListRow(
                                item: item,
                                isSelected: vm.selectedTaskId == item.taskId,
                                onClick: { vm.selectedTaskId = item.taskId }
                            )
                        }
                    } else {
                        Text("暂无任务")
                            .font(CyberFont.mono(size: 10))
                            .foregroundColor(CyberColor.textSecond)
                            .padding(12)
                    }
                }
                .padding(8)
            }
        }
        .background(CyberColor.bg1)
    }
}

private struct TaskListRow: View {
    let data: TaskMonitorData
    let isSelected: Bool
    let onClick: () -> Void

    var body: some View {
        Button(action: onClick) {
            HStack(spacing: 8) {
                _statusDot
                VStack(alignment: .leading, spacing: 2) {
                    Text((data.taskProgress?.taskDescription ?? data.id).prefix(30).description + ((data.taskProgress?.taskDescription ?? "").count > 30 ? "…" : ""))
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textPrimary)
                        .lineLimit(2)
                    Text("\(data.actionLogs.count) 步")
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond)
                }
                Spacer()
            }
            .padding(8)
            .background(isSelected ? CyberColor.cyan.opacity(0.15) : Color.clear)
            .cornerRadius(6)
        }
        .buttonStyle(.plain)
    }

    private var _statusDot: some View {
        let color: Color = {
            switch data.taskProgress?.status {
            case .running: return CyberColor.orange
            case .completed: return CyberColor.green
            case .failed: return CyberColor.red
            default: return CyberColor.textSecond
            }
        }()
        return Circle()
            .fill(color)
            .frame(width: 6, height: 6)
    }
}

private struct ActiveTaskListRow: View {
    let item: ActiveTaskItem
    let isSelected: Bool
    let onClick: () -> Void

    var body: some View {
        Button(action: onClick) {
            HStack(spacing: 8) {
                Circle()
                    .fill(item.status == "running" ? CyberColor.orange : CyberColor.textSecond)
                    .frame(width: 6, height: 6)
                Text((item.description.isEmpty ? item.taskId : item.description).prefix(30).description + (item.description.count > 30 ? "…" : ""))
                    .font(CyberFont.mono(size: 10))
                    .foregroundColor(CyberColor.textPrimary)
                    .lineLimit(2)
                Spacer()
            }
            .padding(8)
            .background(isSelected ? CyberColor.cyan.opacity(0.15) : Color.clear)
            .cornerRadius(6)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Neural Stream Panel（AI 正在输出 - 打字光标 + 动态边框）

private struct NeuralStreamPanel: View {
    let text: String
    let isActive: Bool

    var body: some View {
        CyberCard(glowColor: isActive ? CyberColor.purple : CyberColor.purpleDim, padding: 10) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    if isActive {
                        AIThinkingBrain(isActive: true, nodeCount: 8)
                            .frame(width: 28, height: 28)
                    } else {
                        NeonDot(color: CyberColor.purple, size: 5)
                    }
                    CyberLabel(text: "AI 正在输出", color: CyberColor.purple, size: 9)
                    if isActive {
                        HStack(spacing: 3) {
                            Text("●")
                                .font(CyberFont.mono(size: 8))
                                .foregroundColor(CyberColor.green)
                            Text("LIVE")
                                .font(CyberFont.mono(size: 8, weight: .bold))
                                .foregroundColor(CyberColor.purple)
                        }
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(CyberColor.purple.opacity(0.3))
                        .cornerRadius(3)
                    }
                }

                ScrollView {
                    HStack(alignment: .top, spacing: 2) {
                        Text(text.isEmpty ? (isActive ? "AI 正在思考..." : "等待输出") : text)
                            .font(CyberFont.mono(size: 11))
                            .foregroundColor(text.isEmpty ? CyberColor.textSecond.opacity(0.6) : CyberColor.textPrimary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .textSelection(.enabled)
                        if isActive {
                            TypingCursor(color: CyberColor.purple)
                        }
                    }
                    .padding(4)
                }
                .frame(maxHeight: .infinity)
            }
        }
        .padding(8)
    }
}

// MARK: - 空状态（有趣：浮动粒子 + AI 待机动画）

private struct EmptyTimelineView: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        ZStack {
            FloatingParticlesView(particleCount: 16)

            VStack(spacing: 20) {
                ZStack {
                    AIThinkingBrain(isActive: true, nodeCount: 10)
                        .frame(width: 80, height: 80)
                    Image(systemName: "brain.head.profile")
                        .font(CyberFont.display(size: 36))
                        .foregroundColor(CyberColor.cyan.opacity(0.6))
                }

                Text("AI 随时待命")
                    .font(CyberFont.body(size: 18, weight: .semibold))
                    .foregroundColor(CyberColor.textPrimary)

                Text("启动一个自主任务，看 AI 如何一步步完成任务")
                    .font(CyberFont.body(size: 13))
                    .foregroundColor(CyberColor.textSecond)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - 时间轴列表

private struct TimelineScrollView: View {
    @EnvironmentObject var vm: MonitoringViewModel
    @State private var autoScroll = true

    private var _progress: TaskProgress? {
        vm.viewMode == .single ? vm.currentTaskData?.taskProgress : nil
    }
    private var _elapsed: Int {
        vm.viewMode == .single ? (vm.currentTaskData?.taskElapsedSeconds ?? vm.taskElapsedSeconds) : 0
    }
    private var _logs: [ActionLogEntry] {
        if vm.viewMode == .all {
            return vm.mergedActionLogs.map { $0.2 }
        }
        return vm.currentTaskData?.actionLogs ?? vm.actionLogs
    }

    var body: some View {
        VStack(spacing: 0) {
            if let progress = _progress ?? vm.taskProgress {
                TaskHeaderBar(progress: progress, elapsed: _elapsed)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                Rectangle()
                    .fill(CyberColor.border)
                    .frame(height: 1)
            }

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        if vm.viewMode == .all {
                            ForEach(vm.mergedActionLogs, id: \.2.id) { item in
                                TimelineStepRow(entry: item.2, taskLabel: item.1)
                                    .id(item.2.id)
                            }
                        } else {
                            ForEach(_logs) { entry in
                                TimelineStepRow(entry: entry, taskLabel: nil)
                                    .id(entry.id)
                            }
                        }
                    }
                    .padding(.vertical, 8)
                }
                .onChange(of: _logs.count) {
                    if autoScroll, let last = _logs.last {
                        withAnimation(.easeOut(duration: 0.3)) {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }
            }

            HStack {
                Spacer()
                Toggle("自动滚动", isOn: $autoScroll)
                    .toggleStyle(.checkbox)
                    .font(CyberFont.mono(size: 10))
                    .foregroundColor(CyberColor.textSecond)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 6)
            .background(CyberColor.bg1)
        }
    }
}

// MARK: - 任务头部状态条（AI 工作中：脉动 + 完成时庆祝）

private struct TaskHeaderBar: View {
    let progress: TaskProgress
    let elapsed: Int

    var statusColor: Color {
        switch progress.status {
        case .running: return CyberColor.orange
        case .completed: return CyberColor.green
        case .failed: return CyberColor.red
        }
    }

    var statusLabel: String {
        switch progress.status {
        case .running: return "AI 正在执行"
        case .completed: return "已完成"
        case .failed: return "已失败"
        }
    }

    var body: some View {
        HStack(spacing: 8) {
            if progress.status == .running {
                HStack(spacing: 4) {
                    PulsingDot(color: CyberColor.orange)
                    AIThinkingBrain(isActive: true, nodeCount: 6)
                        .frame(width: 20, height: 20)
                }
            } else if progress.status == .completed {
                Image(systemName: "checkmark.circle.fill")
                    .font(CyberFont.display(size: 20))
                    .foregroundColor(CyberColor.green)
            } else {
                NeonDot(color: statusColor, size: 4)
            }
            CyberLabel(text: statusLabel, color: statusColor, size: 10)

            Text(progress.taskDescription)
                .font(CyberFont.mono(size: 11))
                .foregroundColor(CyberColor.textPrimary)
                .lineLimit(1)

            Spacer()

            Text("\(progress.successfulActions)/\(progress.totalActions) 步")
                .font(CyberFont.mono(size: 10))
                .foregroundColor(CyberColor.textSecond)

            Text(formatElapsed(elapsed))
                .font(CyberFont.mono(size: 10))
                .foregroundColor(CyberColor.textSecond)
        }
    }

    private func formatElapsed(_ s: Int) -> String {
        if s < 60 { return "\(s)s" }
        return "\(s / 60)m\(s % 60)s"
    }
}

// MARK: - 脉冲动画点

struct PulsingDot: View {
    let color: Color
    @State private var scale: CGFloat = 1.0

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 8, height: 8)
            .scaleEffect(scale)
            .shadow(color: color.opacity(0.6), radius: 3)
            .onAppear {
                withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) {
                    scale = 1.4
                }
            }
    }
}

// MARK: - 时间轴单条

private struct TimelineStepRow: View {
    let entry: ActionLogEntry
    var taskLabel: String? = nil

    var statusColor: Color {
        switch entry.status {
        case .success: return CyberColor.green
        case .failed: return CyberColor.red
        case .executing: return CyberColor.orange
        case .pending: return CyberColor.textSecond
        }
    }

    var statusIcon: String {
        switch entry.status {
        case .success: return "checkmark.circle.fill"
        case .failed: return "xmark.circle.fill"
        case .executing: return "arrow.triangle.2.circlepath"
        case .pending: return "circle.dotted"
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            VStack(spacing: 0) {
                ZStack {
                    if entry.status == .executing {
                        SpinnerDot()
                    } else {
                        Image(systemName: statusIcon)
                            .font(CyberFont.body(size: 14))
                            .foregroundColor(statusColor)
                    }
                }
                .frame(width: 28, height: 28)

                Rectangle()
                    .fill(CyberColor.border.opacity(0.5))
                    .frame(width: 2)
                    .frame(maxHeight: .infinity)
            }
            .frame(width: 36)

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    if let label = taskLabel, !label.isEmpty {
                        Text(label)
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(CyberColor.cyan)
                            .lineLimit(1)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 2)
                            .background(CyberColor.cyan.opacity(0.2))
                            .cornerRadius(3)
                    }
                    Text(entry.actionType == "llm_request" ? "LLM" : "步骤 \(entry.iteration)")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                    Text(entry.actionType == "llm_request" ? "远端 LLM 请求" : entry.actionType)
                        .font(CyberFont.body(size: 11, weight: .semibold))
                        .foregroundColor(entry.actionType == "llm_request" ? CyberColor.cyan : CyberColor.textPrimary)
                    Spacer()
                    Text(entry.timestamp, style: .time)
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                }

                if !entry.reasoning.isEmpty {
                    Text(entry.reasoning)
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                        .lineLimit(3)
                }

                if let output = entry.output, !output.isEmpty {
                    DisclosureGroup {
                        Text(output)
                            .font(CyberFont.mono(size: 10))
                            .foregroundColor(CyberColor.textPrimary)
                            .padding(6)
                            .background(CyberColor.bg2)
                            .cornerRadius(4)
                            .overlay(RoundedRectangle(cornerRadius: 4).stroke(CyberColor.border, lineWidth: 1))
                    } label: {
                        Text("查看输出")
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(CyberColor.cyan)
                    }
                }

                if let error = entry.error, !error.isEmpty {
                    HStack(spacing: 4) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(CyberColor.red)
                            .font(CyberFont.body(size: 10))
                        Text(error)
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(CyberColor.red)
                            .lineLimit(2)
                    }
                }
            }
            .padding(.leading, 8)
            .padding(.trailing, 16)
            .padding(.bottom, 16)
        }
        .padding(.horizontal, 8)
    }
}

// MARK: - 旋转图标

private struct SpinnerDot: View {
    @State private var rotating = false

    var body: some View {
        Image(systemName: "arrow.triangle.2.circlepath")
            .font(CyberFont.body(size: 14))
            .foregroundColor(CyberColor.orange)
            .rotationEffect(.degrees(rotating ? 360 : 0))
            .onAppear {
                withAnimation(.linear(duration: 1).repeatForever(autoreverses: false)) {
                    rotating = true
                }
            }
    }
}

// MARK: - 右侧仪表盘

private struct TimelineSidebar: View {
    @EnvironmentObject var vm: MonitoringViewModel

    private var _data: TaskMonitorData? { vm.currentTaskData }

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                TokenGaugeMeter(
                    usage: _data?.sessionTokenUsage ?? vm.sessionTokenUsage,
                    tokenHistory: _data?.tokenHistory ?? vm.tokenHistory
                )

                Rectangle().fill(CyberColor.border).frame(height: 1)

                IterationCounter(iteration: _data?.currentIteration ?? vm.currentIteration)

                Rectangle().fill(CyberColor.border).frame(height: 1)

                ModelSelectionCard(
                    modelType: _data?.selectedModelType ?? vm.selectedModelType,
                    reason: _data?.selectedModelReason ?? vm.selectedModelReason,
                    complexity: _data?.taskComplexity ?? vm.taskComplexity
                )

                if let progress = _data?.taskProgress ?? vm.taskProgress, progress.totalActions > 0 {
                    Rectangle().fill(CyberColor.border).frame(height: 1)
                    SuccessRateGauge(
                        rate: progress.totalActions > 0 ? Double(progress.successfulActions) / Double(progress.totalActions) : 0,
                        success: progress.successfulActions,
                        failed: progress.failedActions
                    )
                }

                Spacer()
            }
            .padding(12)
        }
        .background(CyberColor.bg1)
    }
}

// MARK: - Token 仪表盘（含迷你折线图）

private struct TokenGaugeMeter: View {
    let usage: TokenUsage
    var tokenHistory: [Int] = []
    private let maxTokens = 128_000

    var ratio: Double { min(Double(usage.totalTokens) / Double(maxTokens), 1.0) }

    var gaugeColor: Color {
        if ratio > 0.8 { return CyberColor.red }
        if ratio > 0.5 { return CyberColor.orange }
        return CyberColor.cyan
    }

    var sparklineValues: [Double] {
        guard !tokenHistory.isEmpty, let maxVal = tokenHistory.max(), maxVal > 0 else {
            return [0, 0.3, 0.5, 0.7, 1.0]
        }
        return tokenHistory.map { min(1, Double($0) / Double(maxVal)) }
    }

    var body: some View {
        CyberCard(glowColor: gaugeColor, padding: 10) {
            VStack(spacing: 6) {
                CyberLabel(text: "Token 消耗趋势", color: CyberColor.textSecond, size: 9)

                ZStack {
                    Circle()
                        .stroke(CyberColor.border, lineWidth: 6)
                    Circle()
                        .trim(from: 0, to: ratio)
                        .stroke(gaugeColor, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                        .animation(.easeInOut(duration: 0.5), value: ratio)
                        .shadow(color: gaugeColor.opacity(0.4), radius: 2)

                    VStack(spacing: 1) {
                        Text("\(formatK(usage.totalTokens))")
                            .font(CyberFont.mono(size: 16, weight: .bold))
                            .foregroundColor(gaugeColor)
                        Text("tokens")
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(CyberColor.textSecond)
                    }
                }
                .frame(width: 80, height: 80)

                MiniSparkLineChart(values: sparklineValues, color: gaugeColor, height: 28)

                HStack(spacing: 12) {
                    VStack(spacing: 1) {
                        Text("\(formatK(usage.promptTokens))")
                            .font(CyberFont.mono(size: 10))
                            .foregroundColor(CyberColor.cyanDim)
                        Text("输入").font(CyberFont.mono(size: 8)).foregroundColor(CyberColor.textSecond)
                    }
                    VStack(spacing: 1) {
                        Text("\(formatK(usage.completionTokens))")
                            .font(CyberFont.mono(size: 10))
                            .foregroundColor(CyberColor.greenDim)
                        Text("输出").font(CyberFont.mono(size: 8)).foregroundColor(CyberColor.textSecond)
                    }
                }
            }
            .frame(maxWidth: .infinity)
        }
    }

    private func formatK(_ n: Int) -> String {
        n >= 1000 ? String(format: "%.1fk", Double(n) / 1000) : "\(n)"
    }
}

// MARK: - 迭代计数器

private struct IterationCounter: View {
    let iteration: Int

    var body: some View {
        CyberStatBox(label: "当前轮次", value: "\(iteration)", color: CyberColor.cyan)
    }
}

// MARK: - 模型选择卡片

private struct ModelSelectionCard: View {
    let modelType: String?
    let reason: String?
    let complexity: Int

    var isLocal: Bool { modelType?.lowercased() == "local" }

    var body: some View {
        CyberCard(glowColor: isLocal ? CyberColor.green : CyberColor.cyan, padding: 10) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Image(systemName: isLocal ? "house.fill" : "cloud.fill")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(isLocal ? CyberColor.green : CyberColor.cyan)
                    CyberLabel(text: isLocal ? "本地模型" : "云端模型",
                               color: isLocal ? CyberColor.green : CyberColor.cyan, size: 9)
                }

                VStack(alignment: .leading, spacing: 3) {
                    CyberLabel(text: "复杂度", color: CyberColor.textSecond, size: 9)
                    CyberBar(ratio: Double(complexity) / 10, color: complexityColor, height: 5)
                    Text("\(complexity)/10")
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond)
                }

                if let r = reason, !r.isEmpty {
                    Text(r)
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                        .lineLimit(4)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var complexityColor: Color {
        if complexity >= 7 { return CyberColor.red }
        if complexity >= 4 { return CyberColor.orange }
        return CyberColor.green
    }
}

// MARK: - 成功率

private struct SuccessRateGauge: View {
    let rate: Double
    let success: Int
    let failed: Int

    var rateColor: Color {
        rate >= 0.7 ? CyberColor.green : rate >= 0.4 ? CyberColor.orange : CyberColor.red
    }

    var body: some View {
        CyberStatBox(
            label: "本次成功率",
            value: "\(Int(rate * 100))%",
            color: rateColor,
            subLabel: "✓\(success) ✗\(failed)"
        )
    }
}
