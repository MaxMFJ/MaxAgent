import SwiftUI

// MARK: - Tab5: 用户平台统计 (Cyberpunk)

struct UsageStatisticsView: View {
    @EnvironmentObject var vm: MonitoringViewModel

    let columns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                // 总览卡片（全宽）
                UsageOverviewCard()
                    .environmentObject(vm)

                LazyVGrid(columns: columns, spacing: 14) {
                    // 请求趋势
                    RequestTrendCard()
                        .environmentObject(vm)

                    // Token 使用趋势
                    TokenTrendCard()
                        .environmentObject(vm)

                    // 模型 Token 消耗分布
                    ModelConsumptionCard()
                        .environmentObject(vm)

                    // 模型调用排行
                    ModelCallRankingCard()
                        .environmentObject(vm)
                }

                // 消耗趋势（全宽）
                ConsumptionTrendCard()
                    .environmentObject(vm)
            }
            .padding(16)
        }
    }
}

// MARK: - 总览卡片

private struct UsageOverviewCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        CyberCard(glowColor: CyberColor.cyan) {
            VStack(alignment: .leading, spacing: 10) {
                CyberLabel(text: "Usage Overview", color: CyberColor.cyan)

                HStack(spacing: 16) {
                    StatCell(label: "总请求", value: "\(vm.usageOverview.totalRequests)", color: CyberColor.cyan)
                    StatCell(label: "成功", value: "\(vm.usageOverview.successCount)", color: CyberColor.green)
                    StatCell(label: "总 Tokens", value: formatTokens(vm.usageOverview.totalTokens), color: CyberColor.purple)
                    StatCell(label: "输入 Tokens", value: formatTokens(vm.usageOverview.totalPromptTokens), color: CyberColor.orange)
                    StatCell(label: "输出 Tokens", value: formatTokens(vm.usageOverview.totalCompletionTokens), color: CyberColor.yellow)
                    Spacer()
                    StatCell(label: "RPM", value: String(format: "%.1f", vm.usageOverview.avgRPM), color: CyberColor.cyan)
                    StatCell(label: "TPM", value: formatTokens(Int(vm.usageOverview.avgTPM)), color: CyberColor.purple)
                }
            }
        }
    }

    private func formatTokens(_ count: Int) -> String {
        if count >= 1_000_000 { return String(format: "%.1fM", Double(count) / 1_000_000) }
        if count >= 1_000 { return String(format: "%.1fK", Double(count) / 1_000) }
        return "\(count)"
    }
}

private struct StatCell: View {
    let label: String
    let value: String
    let color: Color

    var body: some View {
        VStack(spacing: 3) {
            Text(value)
                .font(CyberFont.mono(size: 18, weight: .bold))
                .foregroundColor(color)
                .shadow(color: color.opacity(0.5), radius: 4)
            Text(label)
                .font(CyberFont.mono(size: 9, weight: .medium))
                .foregroundColor(CyberColor.textSecond)
        }
    }
}

// MARK: - 请求趋势

private struct RequestTrendCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        CyberCard(glowColor: CyberColor.cyan) {
            VStack(alignment: .leading, spacing: 8) {
                CyberLabel(text: "Request Trend (RPM)", color: CyberColor.cyan, size: 9)
                if vm.usageOverview.rpmHistory.isEmpty {
                    emptyChart
                } else {
                    MiniSparkLineChart(
                        values: normalize(vm.usageOverview.rpmHistory),
                        color: CyberColor.cyan,
                        height: 48
                    )
                }
            }
        }
    }

    private var emptyChart: some View {
        Text("暂无数据")
            .font(CyberFont.mono(size: 10))
            .foregroundColor(CyberColor.textSecond)
            .frame(height: 48)
            .frame(maxWidth: .infinity)
    }

    private func normalize(_ values: [Double]) -> [Double] {
        guard let maxVal = values.max(), maxVal > 0 else { return values.map { _ in 0 } }
        return values.map { $0 / maxVal }
    }
}

// MARK: - Token 使用趋势

private struct TokenTrendCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        CyberCard(glowColor: CyberColor.purple) {
            VStack(alignment: .leading, spacing: 8) {
                CyberLabel(text: "Token Trend (TPM)", color: CyberColor.purple, size: 9)
                if vm.usageOverview.tpmHistory.isEmpty {
                    emptyChart
                } else {
                    MiniSparkLineChart(
                        values: normalize(vm.usageOverview.tpmHistory),
                        color: CyberColor.purple,
                        height: 48
                    )
                }
            }
        }
    }

    private var emptyChart: some View {
        Text("暂无数据")
            .font(CyberFont.mono(size: 10))
            .foregroundColor(CyberColor.textSecond)
            .frame(height: 48)
            .frame(maxWidth: .infinity)
    }

    private func normalize(_ values: [Double]) -> [Double] {
        guard let maxVal = values.max(), maxVal > 0 else { return values.map { _ in 0 } }
        return values.map { $0 / maxVal }
    }
}

// MARK: - 模型 Token 消耗分布

private struct ModelConsumptionCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        CyberCard(glowColor: CyberColor.orange) {
            VStack(alignment: .leading, spacing: 8) {
                CyberLabel(text: "Model Token Distribution", color: CyberColor.orange, size: 9)

                if vm.modelAnalysis.consumptionDistribution.isEmpty {
                    Text("暂无数据")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                        .frame(maxWidth: .infinity, minHeight: 60)
                } else {
                    VStack(spacing: 4) {
                        ForEach(vm.modelAnalysis.consumptionDistribution.prefix(6)) { item in
                            BarRow(label: item.model, value: item.tokens, maxValue: maxTokens, color: CyberColor.orange)
                        }
                    }
                }
            }
        }
    }

    private var maxTokens: Int {
        vm.modelAnalysis.consumptionDistribution.map(\.tokens).max() ?? 1
    }
}

// MARK: - 模型调用排行

private struct ModelCallRankingCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        CyberCard(glowColor: CyberColor.green) {
            VStack(alignment: .leading, spacing: 8) {
                CyberLabel(text: "Model Call Ranking", color: CyberColor.green, size: 9)

                if vm.modelAnalysis.callRanking.isEmpty {
                    Text("暂无数据")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                        .frame(maxWidth: .infinity, minHeight: 60)
                } else {
                    VStack(spacing: 4) {
                        ForEach(vm.modelAnalysis.callRanking.prefix(6)) { item in
                            BarRow(label: item.model, value: item.count, maxValue: maxCalls, color: CyberColor.green)
                        }
                    }
                }
            }
        }
    }

    private var maxCalls: Int {
        vm.modelAnalysis.callRanking.map(\.count).max() ?? 1
    }
}

// MARK: - 消耗趋势（全宽）

private struct ConsumptionTrendCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        CyberCard(glowColor: CyberColor.yellow) {
            VStack(alignment: .leading, spacing: 8) {
                CyberLabel(text: "Consumption Trend", color: CyberColor.yellow, size: 9)

                if vm.modelAnalysis.consumptionTrend.isEmpty {
                    Text("暂无数据")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                        .frame(maxWidth: .infinity, minHeight: 48)
                } else {
                    let values = vm.modelAnalysis.consumptionTrend.map { Double($0.tokens) }
                    MiniSparkLineChart(
                        values: normalize(values),
                        color: CyberColor.yellow,
                        height: 48
                    )
                }
            }
        }
    }

    private func normalize(_ values: [Double]) -> [Double] {
        guard let maxVal = values.max(), maxVal > 0 else { return values.map { _ in 0 } }
        return values.map { $0 / maxVal }
    }
}

// MARK: - 条形行

private struct BarRow: View {
    let label: String
    let value: Int
    let maxValue: Int
    let color: Color

    private var ratio: CGFloat {
        maxValue > 0 ? CGFloat(value) / CGFloat(maxValue) : 0
    }

    var body: some View {
        HStack(spacing: 6) {
            Text(label)
                .font(CyberFont.mono(size: 10, weight: .medium))
                .foregroundColor(CyberColor.textPrimary)
                .lineLimit(1)
                .frame(width: 100, alignment: .trailing)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(CyberColor.bg2)
                    RoundedRectangle(cornerRadius: 2)
                        .fill(color.opacity(0.6))
                        .frame(width: geo.size.width * ratio)
                        .shadow(color: color.opacity(0.4), radius: 4)
                }
            }
            .frame(height: 10)

            Text(formatNumber(value))
                .font(CyberFont.mono(size: 9, weight: .semibold))
                .foregroundColor(color)
                .frame(width: 50, alignment: .trailing)
        }
        .frame(height: 14)
    }

    private func formatNumber(_ n: Int) -> String {
        if n >= 1_000_000 { return String(format: "%.1fM", Double(n) / 1_000_000) }
        if n >= 1_000 { return String(format: "%.1fK", Double(n) / 1_000) }
        return "\(n)"
    }
}
