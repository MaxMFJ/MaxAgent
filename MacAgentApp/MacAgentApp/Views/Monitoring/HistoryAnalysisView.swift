import SwiftUI

// MARK: - Tab3: 历史任务分析 (Cyberpunk)

struct HistoryAnalysisView: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        if vm.isLoadingHistory && vm.episodes.isEmpty {
            ZStack {
                FloatingParticlesView(particleCount: 12)
                VStack(spacing: 16) {
                    AIThinkingBrain(isActive: true, nodeCount: 8)
                        .frame(width: 60, height: 60)
                    ProgressView()
                        .scaleEffect(0.8)
                        .colorMultiply(CyberColor.cyan)
                    Text("正在加载历史记录...")
                        .font(.system(size: 12))
                        .foregroundColor(CyberColor.textSecond)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if vm.episodes.isEmpty {
            EmptyHistoryView()
                .environmentObject(vm)
        } else {
            HSplitView {
                EpisodeListPanel()
                    .environmentObject(vm)
                    .frame(minWidth: 320)

                HistoryStatsPanel()
                    .environmentObject(vm)
                    .frame(minWidth: 260, maxWidth: 320)
            }
        }
    }
}

// MARK: - 空状态

private struct EmptyHistoryView: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        ZStack {
            FloatingParticlesView(particleCount: 14)
            VStack(spacing: 18) {
                Image(systemName: "trophy")
                    .font(.system(size: 48))
                    .foregroundColor(CyberColor.yellow.opacity(0.7))
                Text("还没有战绩")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(CyberColor.textPrimary)
                Text("完成几个自主任务，这里就会记录你的 AI 战绩")
                    .font(.system(size: 13))
                    .foregroundColor(CyberColor.textSecond)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
                Button(action: { Task { await vm.fetchHistory() } }) {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.clockwise")
                        Text("刷新")
                            .font(.system(size: 11, weight: .semibold))
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

// MARK: - 左侧：Episode 列表

private struct EpisodeListPanel: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                CyberLabel(text: "执行记录", color: CyberColor.cyan, size: 11)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                Spacer()
                if vm.isLoadingHistory {
                    ProgressView().scaleEffect(0.6).colorMultiply(CyberColor.cyan).padding(.trailing, 8)
                }
                Button(action: { Task { await vm.fetchHistory() } }) {
                    Image(systemName: "arrow.clockwise")
                        .font(.caption)
                        .foregroundColor(CyberColor.cyan)
                }
                .buttonStyle(.plain)
                .padding(.trailing, 12)
            }
            .background(CyberColor.bg1)
            .overlay(Rectangle().fill(CyberColor.border).frame(height: 1), alignment: .bottom)

            List(vm.episodes, selection: $vm.selectedEpisodeId) { ep in
                EpisodeRow(ep: ep)
                    .tag(ep.id)
                    .listRowBackground(CyberColor.bg1)
                    .listRowSeparatorTint(CyberColor.border)
            }
            .listStyle(.inset)
            .scrollContentBackground(.hidden)
        }
    }
}

private struct EpisodeRow: View {
    let ep: EpisodeRecord

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: ep.success ? "checkmark.circle.fill" : "xmark.circle.fill")
                .foregroundColor(ep.success ? CyberColor.green : CyberColor.red)
                .font(.system(size: 16))
                .padding(.top, 1)

            VStack(alignment: .leading, spacing: 3) {
                Text(ep.taskDescription)
                    .font(.system(size: 11, weight: .semibold))
                    .lineLimit(2)
                    .foregroundColor(CyberColor.textPrimary)

                HStack(spacing: 8) {
                    Label("\(ep.totalIterations) 轮", systemImage: "repeat")
                        .font(.system(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                    Label("\(formatK(ep.tokenUsage.totalTokens)) t", systemImage: "bolt.fill")
                        .font(.system(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                    if ep.executionTimeMs > 0 {
                        Label(formatMs(ep.executionTimeMs), systemImage: "clock")
                            .font(.system(size: 10))
                            .foregroundColor(CyberColor.textSecond)
                    }
                }

                if !ep.toolsUsed.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 4) {
                            ForEach(ep.toolsUsed.prefix(4), id: \.self) { tool in
                                Text(tool)
                                    .font(.system(size: 9))
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 2)
                                    .background(CyberColor.cyan.opacity(0.2))
                                    .foregroundColor(CyberColor.cyan)
                                    .cornerRadius(4)
                            }
                        }
                    }
                }

                Text(ep.createdAt, format: .dateTime.month(.abbreviated).day().hour().minute())
                    .font(.system(size: 10))
                    .foregroundColor(CyberColor.textSecond.opacity(0.8))
            }
        }
        .padding(.vertical, 6)
    }

    private func formatK(_ n: Int) -> String {
        n >= 1000 ? String(format: "%.1fk", Double(n) / 1000) : "\(n)"
    }

    private func formatMs(_ ms: Int) -> String {
        if ms < 1000 { return "\(ms)ms" }
        if ms < 60_000 { return "\(ms / 1000)s" }
        return "\(ms / 60_000)m\(ms % 60_000 / 1000)s"
    }
}

// MARK: - 右侧：统计面板

private struct HistoryStatsPanel: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var stats: ExecutionStatistics { vm.statistics }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                CyberLabel(text: "聚合统计", color: CyberColor.cyan, size: 11)
                    .padding(.top, 4)

                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                    BigStatCard(label: "总任务", value: "\(stats.totalTasks)", color: CyberColor.cyan)
                    BigStatCard(label: "成功率", value: "\(Int(stats.successRate * 100))%",
                                color: stats.successRate >= 0.7 ? CyberColor.green : stats.successRate >= 0.4 ? CyberColor.orange : CyberColor.red)
                    BigStatCard(label: "平均轮次", value: String(format: "%.1f", stats.avgIterations), color: CyberColor.purple)
                    BigStatCard(label: "均Token", value: formatK(stats.avgTokensPerTask), color: CyberColor.orange)
                }

                if !stats.toolRanking.isEmpty {
                    Rectangle().fill(CyberColor.border).frame(height: 1)

                    CyberLabel(text: "工具使用排行", color: CyberColor.textSecond, size: 9)

                    let maxCount = stats.toolRanking.first?.count ?? 1
                    ForEach(stats.toolRanking.prefix(10)) { item in
                        ToolRankRow(item: item, maxCount: maxCount)
                    }
                }
            }
            .padding(16)
        }
        .background(CyberColor.bg1)
    }

    private func formatK(_ n: Int) -> String {
        n >= 1000 ? String(format: "%.1fk", Double(n) / 1000) : "\(n)"
    }
}

private struct BigStatCard: View {
    let label: String
    let value: String
    let color: Color

    var body: some View {
        CyberCard(glowColor: color, padding: 12) {
            VStack(spacing: 3) {
                Text(value)
                    .font(.system(size: 22, weight: .bold, design: .monospaced))
                    .foregroundColor(color)
                CyberLabel(text: label, color: CyberColor.textSecond, size: 9)
            }
            .frame(maxWidth: .infinity)
        }
    }
}

private struct ToolRankRow: View {
    let item: ToolRankItem
    let maxCount: Int

    var body: some View {
        HStack(spacing: 8) {
            Text(displayName(item.tool))
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(CyberColor.textPrimary)
                .frame(width: 100, alignment: .leading)
                .lineLimit(1)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(CyberColor.bg2)
                    RoundedRectangle(cornerRadius: 3)
                        .fill(CyberColor.cyan)
                        .frame(width: geo.size.width * (Double(item.count) / Double(maxCount)))
                        .animation(.easeInOut(duration: 0.4), value: item.count)
                }
            }
            .frame(height: 12)

            Text("\(item.count)")
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(CyberColor.textSecond)
                .frame(width: 28, alignment: .trailing)
        }
    }

    private func displayName(_ name: String) -> String {
        let map: [String: String] = [
            "terminal": "terminal",
            "file_operations": "file",
            "screenshot": "screenshot",
            "web_search": "web_search",
            "browser": "browser",
            "app_control": "app",
            "system_info": "system",
        ]
        return map[name] ?? name
    }
}
