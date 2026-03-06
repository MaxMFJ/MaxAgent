import SwiftUI

/// /context 上下文可视化面板
struct ContextVisualizationView: View {
    @EnvironmentObject var viewModel: AgentViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // 刷新栏
            HStack {
                Image(systemName: "chart.bar.xaxis")
                    .foregroundColor(CyberColor.cyan)
                Text("上下文概览")
                    .font(CyberFont.body(size: 13, weight: .semibold))
                Spacer()
                Button {
                    Task { await viewModel.loadContext() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.borderless)
                .disabled(viewModel.isLoadingContext)
            }
            .padding(12)
            .background(Color(NSColor.controlBackgroundColor).opacity(0.5))

            Divider()

            if viewModel.isLoadingContext {
                ProgressView("加载中…").frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if viewModel.contextData.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "viewfinder")
                        .font(.largeTitle).foregroundColor(.secondary)
                    Text("暂无上下文数据")
                        .font(CyberFont.body(size: 12)).foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        contextTokenSection
                        contextActiveTasksSection
                        contextModelSection
                        contextPhaseSection
                        contextSnapshotSection
                        contextMCPSection
                    }
                    .padding(16)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear {
            Task { await viewModel.loadContext() }
        }
    }

    // MARK: - Sections

    @ViewBuilder
    private var contextTokenSection: some View {
        if let tokenInfo = viewModel.contextData["token_usage"] as? [String: Any] {
            contextCard(title: "Token 用量", icon: "number.circle") {
                let used = tokenInfo["used"] as? Int ?? 0
                let limit = tokenInfo["limit"] as? Int ?? 0
                let pct = limit > 0 ? Double(used) / Double(limit) : 0
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text("\(used.formatted()) / \(limit.formatted())")
                            .font(.system(size: 12, design: .monospaced))
                        Spacer()
                        Text(String(format: "%.1f%%", pct * 100))
                            .font(CyberFont.body(size: 11))
                            .foregroundColor(pct > 0.8 ? .red : .secondary)
                    }
                    ProgressView(value: pct)
                        .accentColor(pct > 0.8 ? .red : CyberColor.cyan)
                }
            }
        }
    }

    @ViewBuilder
    private var contextActiveTasksSection: some View {
        if let activeTasks = viewModel.contextData["active_tasks"] as? [[String: Any]], !activeTasks.isEmpty {
            contextCard(title: "活跃任务 (\(activeTasks.count))", icon: "list.bullet.clipboard") {
                ForEach(activeTasks.indices, id: \.self) { i in
                    let task = activeTasks[i]
                    HStack {
                        Circle()
                            .fill(taskStatusColor(task["status"] as? String ?? ""))
                            .frame(width: 6, height: 6)
                        Text(task["task_id"] as? String ?? "—")
                            .font(.system(size: 11, design: .monospaced))
                        Spacer()
                        Text(task["status"] as? String ?? "")
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(.secondary)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var contextModelSection: some View {
        if let modelStats = viewModel.contextData["model_routing"] as? [String: Any] {
            contextCard(title: "模型路由统计", icon: "cpu") {
                ForEach(["fast", "strong", "cheap"], id: \.self) { tier in
                    if let count = modelStats[tier] as? Int {
                        HStack {
                            Text(tierIcon(tier))
                            Text(tierName(tier))
                                .font(CyberFont.body(size: 12))
                            Spacer()
                            Text("\(count) 次")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundColor(.secondary)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var contextPhaseSection: some View {
        if let phaseStats = viewModel.contextData["phase_stats"] as? [String: Any] {
            contextCard(title: "执行阶段统计", icon: "chart.pie") {
                ForEach(["gather", "act", "verify"], id: \.self) { phase in
                    if let count = phaseStats[phase] as? Int {
                        HStack {
                            Text(phaseIcon(phase))
                            Text(phaseName(phase))
                                .font(CyberFont.body(size: 12))
                            Spacer()
                            Text("\(count)")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundColor(.secondary)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var contextSnapshotSection: some View {
        if let snaps = viewModel.contextData["snapshots"] as? [String: Any] {
            contextCard(title: "快照统计", icon: "clock.arrow.circlepath") {
                let total = snaps["total"] as? Int ?? 0
                let applied = snaps["applied"] as? Int ?? 0
                HStack {
                    Text("总快照: \(total)")
                        .font(CyberFont.body(size: 12))
                    Spacer()
                    Text("已回滚: \(applied)")
                        .font(CyberFont.body(size: 12))
                        .foregroundColor(applied > 0 ? .green : .secondary)
                }
            }
        }
    }

    @ViewBuilder
    private var contextMCPSection: some View {
        if let mcpInfo = viewModel.contextData["mcp"] as? [String: Any] {
            contextCard(title: "MCP 状态", icon: "network") {
                let serverCount = mcpInfo["server_count"] as? Int ?? 0
                let toolCount = mcpInfo["tool_count"] as? Int ?? 0
                HStack {
                    Text("服务器: \(serverCount)")
                        .font(CyberFont.body(size: 12))
                    Spacer()
                    Text("工具: \(toolCount)")
                        .font(CyberFont.body(size: 12))
                        .foregroundColor(toolCount > 0 ? CyberColor.cyan : .secondary)
                }
            }
        }
    }

    // MARK: - Helpers

    private func contextCard<Content: View>(title: String, icon: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .foregroundColor(CyberColor.cyan)
                    .font(.system(size: 12))
                Text(title)
                    .font(CyberFont.body(size: 12, weight: .semibold))
            }
            content()
        }
        .padding(12)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
    }

    private func taskStatusColor(_ status: String) -> Color {
        switch status {
        case "running": return .green
        case "completed": return CyberColor.cyan
        case "failed": return .red
        default: return .orange
        }
    }

    private func tierIcon(_ tier: String) -> String {
        switch tier {
        case "fast": return "⚡"
        case "strong": return "💪"
        case "cheap": return "💰"
        default: return "🤖"
        }
    }

    private func tierName(_ tier: String) -> String {
        switch tier {
        case "fast": return "快速 (Fast)"
        case "strong": return "强力 (Strong)"
        case "cheap": return "经济 (Cheap)"
        default: return tier
        }
    }

    private func phaseIcon(_ phase: String) -> String {
        switch phase {
        case "gather": return "🔍"
        case "act": return "⚡"
        case "verify": return "✔️"
        default: return "🔄"
        }
    }

    private func phaseName(_ phase: String) -> String {
        switch phase {
        case "gather": return "Gather（收集）"
        case "act": return "Act（执行）"
        case "verify": return "Verify（验证）"
        default: return phase
        }
    }
}
