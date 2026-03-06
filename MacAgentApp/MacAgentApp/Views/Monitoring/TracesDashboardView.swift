import SwiftUI

// MARK: - Tab TRACE: 执行轨迹与 Token 消耗看板 (Cyberpunk)

struct TracesDashboardView: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        if vm.isLoadingTraces && vm.traceList.isEmpty {
            EmptyTracesLoadingView()
        } else if vm.traceList.isEmpty {
            EmptyTracesView()
                .environmentObject(vm)
        } else {
            HSplitView {
                TraceListPanel()
                    .environmentObject(vm)
                    .frame(minWidth: 320)

                TraceDetailPanel()
                    .environmentObject(vm)
                    .frame(minWidth: 400)
            }
        }
    }
}

// MARK: - 空状态：加载中

private struct EmptyTracesLoadingView: View {
    var body: some View {
        ZStack {
            FloatingParticlesView(particleCount: 12)
            VStack(spacing: 16) {
                AIThinkingBrain(isActive: true, nodeCount: 8)
                    .frame(width: 60, height: 60)
                ProgressView()
                    .scaleEffect(0.8)
                    .colorMultiply(CyberColor.cyan)
                Text("正在加载 Trace 列表...")
                    .font(CyberFont.body(size: 12))
                    .foregroundColor(CyberColor.textSecond)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - 空状态：无 Trace

private struct EmptyTracesView: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        ZStack {
            FloatingParticlesView(particleCount: 14)
            VStack(spacing: 18) {
                Image(systemName: "waveform.path.ecg")
                    .font(CyberFont.display(size: 48))
                    .foregroundColor(CyberColor.cyan.opacity(0.7))
                Text("暂无执行轨迹")
                    .font(CyberFont.body(size: 18, weight: .semibold))
                    .foregroundColor(CyberColor.textPrimary)
                Text("完成自主任务后，这里会展示执行轨迹与 Token 消耗")
                    .font(CyberFont.body(size: 13))
                    .foregroundColor(CyberColor.textSecond)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
                Button(action: { Task { await vm.fetchTraces() } }) {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.clockwise")
                        Text("刷新")
                            .font(CyberFont.body(size: 11, weight: .semibold))
                    }
                    .foregroundColor(CyberColor.bg0)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(CyberColor.cyan)
                    .cornerRadius(6)
                }
                .buttonStyle(.plain)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - 左侧：Trace 列表

private struct TraceListPanel: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                CyberLabel(text: "Trace 列表", color: CyberColor.cyan, size: 11)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                Spacer()
                if vm.isPolling {
                    ProgressView()
                        .scaleEffect(0.6)
                        .colorMultiply(CyberColor.cyan)
                        .padding(.trailing, 8)
                }
                Button(action: { Task { await vm.fetchTraces() } }) {
                    Image(systemName: "arrow.clockwise")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(CyberColor.cyan)
                }
                .buttonStyle(.plain)
                .padding(.trailing, 12)
            }
            .background(CyberColor.bg1)
            .overlay(Rectangle().fill(CyberColor.border).frame(height: 1), alignment: .bottom)

            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(vm.traceList) { item in
                        TraceListRow(
                            item: item,
                            isSelected: vm.selectedTraceTaskId == item.taskId
                        ) {
                            vm.selectTrace(item.taskId)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                    }
                }
                .padding(.vertical, 8)
            }
        }
    }
}

private struct TraceListRow: View {
    let item: TraceListItem
    let isSelected: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "waveform.path.ecg")
                    .font(CyberFont.body(size: 14))
                    .foregroundColor(isSelected ? CyberColor.cyan : CyberColor.textSecond)
                    .frame(width: 24, alignment: .center)

                VStack(alignment: .leading, spacing: 4) {
                    Text(shortTaskId(item.taskId))
                        .font(CyberFont.mono(size: 11, weight: .semibold))
                        .foregroundColor(isSelected ? CyberColor.cyan : CyberColor.textPrimary)
                        .lineLimit(1)

                    HStack(spacing: 8) {
                        Label("\(item.spanCount) spans", systemImage: "list.bullet")
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(CyberColor.textSecond)
                        Label(formatBytes(item.sizeBytes), systemImage: "doc")
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(CyberColor.textSecond)
                    }

                    Text(formatMtime(item.mtime))
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond.opacity(0.8))
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                if isSelected {
                    Image(systemName: "chevron.right")
                        .font(CyberFont.body(size: 10, weight: .semibold))
                        .foregroundColor(CyberColor.cyan)
                }
            }
            .padding(.vertical, 8)
            .padding(.horizontal, 10)
            .background(isSelected ? CyberColor.bgHighlight : CyberColor.bg1)
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(isSelected ? CyberColor.cyan.opacity(0.5) : CyberColor.border, lineWidth: 1)
            )
            .cornerRadius(6)
        }
        .buttonStyle(.plain)
    }

    private func shortTaskId(_ id: String) -> String {
        id.count > 20 ? String(id.prefix(18)) + "…" : id
    }

    private func formatBytes(_ bytes: Int) -> String {
        if bytes < 1024 { return "\(bytes)B" }
        if bytes < 1024 * 1024 { return String(format: "%.1fKB", Double(bytes) / 1024) }
        return String(format: "%.1fMB", Double(bytes) / (1024 * 1024))
    }

    private func formatMtime(_ ts: Double) -> String {
        let date = Date(timeIntervalSince1970: ts)
        return date.formatted(.dateTime.month(.abbreviated).day().hour().minute())
    }
}

// MARK: - 右侧：Trace 摘要 + Span 时间线

private struct TraceDetailPanel: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        VStack(spacing: 0) {
            if let taskId = vm.selectedTraceTaskId {
                if vm.isLoadingTraces && vm.selectedTraceSummary == nil {
                    TraceDetailLoadingView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 14) {
                            TraceSummaryCard(summary: vm.selectedTraceSummary, taskId: taskId)
                            TraceSpansTimeline(spans: vm.selectedTraceSpans)
                        }
                        .padding(16)
                    }
                }
            } else {
                TraceDetailPlaceholder()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(CyberColor.bg0)
    }
}

private struct TraceDetailLoadingView: View {
    var body: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(0.9)
                .colorMultiply(CyberColor.cyan)
            Text("加载 Trace 详情...")
                .font(CyberFont.body(size: 12))
                .foregroundColor(CyberColor.textSecond)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct TraceDetailPlaceholder: View {
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "arrow.left.circle")
                .font(CyberFont.display(size: 32))
                .foregroundColor(CyberColor.cyan.opacity(0.5))
            Text("选择左侧 Trace 查看详情")
                .font(CyberFont.body(size: 13))
                .foregroundColor(CyberColor.textSecond)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Trace 摘要卡片

private struct TraceSummaryCard: View {
    let summary: TraceSummaryData?
    let taskId: String

    var body: some View {
        CyberCard(glowColor: CyberColor.cyan, padding: 14) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 8) {
                    NeonDot(color: (summary?.exists ?? false) ? CyberColor.green : CyberColor.orange, size: 6)
                    Text("TASK: \(shortId(taskId))")
                        .font(CyberFont.mono(size: 11, weight: .bold))
                        .foregroundColor(CyberColor.textPrimary)
                }

                if let s = summary, s.exists {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                        TraceStatBox(label: "Prompt", value: formatK(s.tokens.prompt), color: CyberColor.cyan)
                        TraceStatBox(label: "Completion", value: formatK(s.tokens.completion), color: CyberColor.purple)
                        TraceStatBox(label: "Total", value: formatK(s.tokens.total), color: CyberColor.orange)
                        TraceStatBox(label: "Spans", value: "\(s.totalSpans)", color: CyberColor.textSecond)
                        TraceStatBox(label: "Avg Latency", value: s.latency.count > 0 ? "\(Int(s.latency.avgMs))ms" : "--", color: CyberColor.green)
                        TraceStatBox(
                            label: "工具成功率",
                            value: toolSuccessRate(s),
                            color: toolSuccessColor(s)
                        )
                    }

                    if let dur = s.timeline.durationS, dur > 0 {
                        HStack(spacing: 6) {
                            Image(systemName: "clock")
                                .font(CyberFont.mono(size: 10))
                                .foregroundColor(CyberColor.textSecond)
                            Text("总耗时: \(String(format: "%.1f", dur))s")
                                .font(CyberFont.mono(size: 10))
                                .foregroundColor(CyberColor.textSecond)
                        }
                    }

                    if !s.recentErrors.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            CyberLabel(text: "最近错误", color: CyberColor.red, size: 9)
                            ForEach(s.recentErrors.prefix(3), id: \.self) { err in
                                Text(err)
                                    .font(CyberFont.mono(size: 9))
                                    .foregroundColor(CyberColor.red.opacity(0.9))
                                    .lineLimit(2)
                            }
                        }
                        .padding(.top, 4)
                    }
                } else {
                    Text("Trace 不存在或加载失败")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(CyberColor.textSecond)
                }
            }
        }
    }

    private func shortId(_ id: String) -> String {
        id.count > 24 ? String(id.prefix(22)) + "…" : id
    }

    private func formatK(_ n: Int) -> String {
        n >= 1000 ? String(format: "%.1fk", Double(n) / 1000) : "\(n)"
    }

    private func toolSuccessRate(_ s: TraceSummaryData) -> String {
        let total = s.toolCalls.success + s.toolCalls.failure
        guard total > 0 else { return "--" }
        return "\(Int(Double(s.toolCalls.success) / Double(total) * 100))%"
    }

    private func toolSuccessColor(_ s: TraceSummaryData) -> Color {
        let total = s.toolCalls.success + s.toolCalls.failure
        guard total > 0 else { return CyberColor.textSecond }
        let rate = Double(s.toolCalls.success) / Double(total)
        if rate >= 0.9 { return CyberColor.green }
        if rate >= 0.6 { return CyberColor.orange }
        return CyberColor.red
    }
}

private struct TraceStatBox: View {
    let label: String
    let value: String
    let color: Color

    var body: some View {
        VStack(spacing: 3) {
            Text(value)
                .font(CyberFont.mono(size: 14, weight: .bold))
                .foregroundColor(color)
            Text(label)
                .font(CyberFont.mono(size: 9))
                .foregroundColor(CyberColor.textSecond)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(CyberColor.bg2.opacity(0.6))
        .cornerRadius(6)
    }
}

// MARK: - Span 时间线

private struct TraceSpansTimeline: View {
    let spans: [TraceSpanItem]

    var body: some View {
        CyberCard(glowColor: CyberColor.purple, padding: 12) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    CyberLabel(text: "Span 时间线", color: CyberColor.purple, size: 10)
                    Spacer()
                    Text("\(spans.count) 条")
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond)
                }

                if spans.isEmpty {
                    Text("暂无 span 数据")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(CyberColor.textSecond)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 24)
                } else {
                    ScrollView {
                        LazyVStack(spacing: 6) {
                            ForEach(spans) { span in
                                SpanRow(span: span)
                            }
                        }
                    }
                    .frame(maxHeight: 320)
                }
            }
        }
    }
}

private struct SpanRow: View {
    let span: TraceSpanItem

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            SpanTypeIcon(type: span.type)
                .frame(width: 28, alignment: .center)

            VStack(alignment: .leading, spacing: 2) {
                Text(span.detail)
                    .font(CyberFont.mono(size: 10))
                    .foregroundColor(CyberColor.textPrimary)
                    .lineLimit(2)

                HStack(spacing: 8) {
                    if let lat = span.latencyMs, lat > 0 {
                        Text("\(Int(lat))ms")
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(CyberColor.cyanDim)
                    }
                    if let ok = span.success {
                        HStack(spacing: 3) {
                            Image(systemName: ok ? "checkmark.circle.fill" : "xmark.circle.fill")
                                .font(CyberFont.mono(size: 9))
                            Text(ok ? "成功" : "失败")
                                .font(CyberFont.mono(size: 9))
                        }
                        .foregroundColor(ok ? CyberColor.green : CyberColor.red)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 8)
        .background(CyberColor.bg2.opacity(0.5))
        .cornerRadius(5)
        .overlay(
            RoundedRectangle(cornerRadius: 5)
                .stroke(CyberColor.border.opacity(0.5), lineWidth: 0.5)
        )
    }
}

private struct SpanTypeIcon: View {
    let type: String

    var body: some View {
        let (icon, color) = iconAndColor
        Image(systemName: icon)
            .font(CyberFont.body(size: 14))
            .foregroundColor(color)
    }

    private var iconAndColor: (String, Color) {
        switch type.lowercased() {
        case "llm":
            return ("brain.head.profile", CyberColor.purple)
        case "tool":
            return ("wrench.and.screwdriver", CyberColor.cyan)
        case "step":
            return ("arrow.right.circle", CyberColor.orange)
        default:
            return ("circle.fill", CyberColor.textSecond)
        }
    }
}
