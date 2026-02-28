import SwiftUI

// MARK: - Tab2: 系统运行状态看板 (Cyberpunk)

struct SystemStatusDashboardView: View {
    @EnvironmentObject var vm: MonitoringViewModel

    let columns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                // AI 活动趋势（有趣的小图表）
                ActivitySparklineCard()
                    .environmentObject(vm)

                // 服务健康总览（全宽）
                ServiceHealthCard()
                    .environmentObject(vm)

                LazyVGrid(columns: columns, spacing: 14) {
                    LLMInfoCard()
                        .environmentObject(vm)

                    ConnectionStatsCard()
                        .environmentObject(vm)

                    LocalLLMCard()
                        .environmentObject(vm)

                    ModelSelectorCard()
                        .environmentObject(vm)
                }

                // 向量记忆状态（全宽）
                MemoryStatusCard()
                    .environmentObject(vm)
            }
            .padding(16)
        }
    }
}

// MARK: - AI 活动趋势卡片（迷你图表 + 动态感）

private struct ActivitySparklineCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var sparklineValues: [Double] {
        let hist = vm.tokenHistory
        guard !hist.isEmpty, let maxVal = hist.max(), maxVal > 0 else {
            return [0.2, 0.4, 0.6, 0.5, 0.8, 0.7, 1.0]
        }
        return hist.map { min(1, Double($0) / Double(maxVal)) }
    }

    var body: some View {
        CyberCard(glowColor: vm.isStreamingLLM ? CyberColor.purple : CyberColor.cyan, padding: 12) {
            HStack(spacing: 16) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        if vm.isStreamingLLM {
                            AIThinkingBrain(isActive: true, nodeCount: 6)
                                .frame(width: 24, height: 24)
                        } else {
                            Image(systemName: "chart.line.uptrend.xyaxis")
                                .font(.system(size: 20))
                                .foregroundColor(CyberColor.cyan)
                        }
                        Text(vm.isStreamingLLM ? "AI 正在思考" : "活动趋势")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(CyberColor.textPrimary)
                    }
                    Text(vm.isStreamingLLM ? "神经网络活跃中..." : "Token 消耗随时间变化")
                        .font(.system(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                }

                MiniSparkLineChart(values: sparklineValues, color: vm.isStreamingLLM ? CyberColor.purple : CyberColor.cyan, height: 44)
                    .frame(maxWidth: .infinity)
            }
        }
    }
}

// MARK: - 服务健康总览

private struct ServiceHealthCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        CyberCard(glowColor: CyberColor.cyan, padding: 14) {
            HStack(spacing: 0) {
                ServiceDotItem(
                    label: "后端服务",
                    icon: "server.rack",
                    ok: vm.healthInfo.backendHealthy
                )
                cyberDivider()
                ServiceDotItem(
                    label: "WebSocket",
                    icon: "wifi",
                    ok: vm.healthInfo.wsConnectionCount > 0
                )
                cyberDivider()
                ServiceDotItem(
                    label: "向量库",
                    icon: "cylinder.split.1x2",
                    ok: vm.memoryStatus.embeddingModelLoaded
                )
                cyberDivider()
                ServiceDotItem(
                    label: "本地LLM",
                    icon: "house.fill",
                    ok: vm.localLLMInfo.available || vm.localLLMInfo.ollamaServerRunning || vm.localLLMInfo.lmStudioServerRunning
                )
                cyberDivider()
                ServiceDotItem(
                    label: "EvoMap",
                    icon: "arrow.triangle.2.circlepath",
                    ok: vm.healthInfo.evomapStatus == "connected"
                )
            }
            .frame(maxWidth: .infinity)
        }
    }

    private func cyberDivider() -> some View {
        Rectangle()
            .fill(CyberColor.border)
            .frame(width: 1, height: 44)
            .padding(.horizontal, 12)
    }
}

private struct ServiceDotItem: View {
    let label: String
    let icon: String
    let ok: Bool

    var body: some View {
        VStack(spacing: 6) {
            ZStack(alignment: .bottomTrailing) {
                Image(systemName: icon)
                    .font(.system(size: 22))
                    .foregroundColor(ok ? CyberColor.cyan : CyberColor.textSecond.opacity(0.4))
                NeonDot(color: ok ? CyberColor.green : CyberColor.red, size: 5)
            }
            CyberLabel(text: label, color: CyberColor.textSecond, size: 9)
        }
        .frame(maxWidth: .infinity)
    }
}

// MARK: - LLM 信息卡片

private struct LLMInfoCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var providerIcon: String {
        switch vm.healthInfo.llmProvider.lowercased() {
        case "openai": return "cpu.chip.fill"
        case "deepseek": return "sparkles"
        case "anthropic": return "a.circle.fill"
        case "ollama", "lmstudio": return "house.fill"
        default: return "questionmark.circle"
        }
    }

    var body: some View {
        CyberCard(glowColor: CyberColor.purple, padding: 12) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Image(systemName: providerIcon)
                        .font(.caption)
                        .foregroundColor(CyberColor.purple)
                    CyberLabel(text: vm.healthInfo.llmProvider.uppercased(),
                               color: CyberColor.purple, size: 9)
                }

                Text(vm.healthInfo.llmModel)
                    .font(.system(size: 13, weight: .semibold, design: .monospaced))
                    .foregroundColor(CyberColor.textPrimary)
                    .lineLimit(2)

                HStack(spacing: 4) {
                    NeonDot(color: vm.healthInfo.backendHealthy ? CyberColor.green : CyberColor.red, size: 4)
                    Text(vm.healthInfo.backendHealthy ? "已连接" : "未连接")
                        .font(.system(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

// MARK: - 连接状态

private struct ConnectionStatsCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        CyberCard(glowColor: CyberColor.cyan, padding: 12) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text("\(vm.healthInfo.wsConnectionCount)")
                        .font(.system(size: 34, weight: .bold, design: .monospaced))
                        .foregroundColor(CyberColor.cyan)
                        .contentTransition(.numericText())
                        .animation(.spring(), value: vm.healthInfo.wsConnectionCount)
                    Text("个连接")
                        .font(.caption)
                        .foregroundColor(CyberColor.textSecond)
                }

                ForEach(vm.healthInfo.wsConnectionsByType.sorted(by: { $0.key < $1.key }), id: \.key) { key, val in
                    HStack {
                        Text(key == "mac" ? "Mac" : key == "ios" ? "iOS" : key)
                            .font(.system(size: 10))
                            .foregroundColor(CyberColor.textSecond)
                        Spacer()
                        Text("\(val)")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(CyberColor.cyanDim)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

// MARK: - 本地 LLM 卡片

private struct LocalLLMCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        CyberCard(glowColor: CyberColor.green, padding: 12) {
            VStack(alignment: .leading, spacing: 6) {
                CyberLabel(text: "本地模型", color: CyberColor.green, size: 9)
                LocalLLMRow(
                    name: "Ollama",
                    available: vm.localLLMInfo.ollamaAvailable,
                    serverRunning: vm.localLLMInfo.ollamaServerRunning,
                    model: vm.localLLMInfo.ollamaModel
                )
                LocalLLMRow(
                    name: "LM Studio",
                    available: vm.localLLMInfo.lmStudioAvailable,
                    serverRunning: vm.localLLMInfo.lmStudioServerRunning,
                    model: vm.localLLMInfo.lmStudioModel
                )
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct LocalLLMRow: View {
    let name: String
    let available: Bool
    let serverRunning: Bool
    let model: String

    var dotColor: Color {
        if available { return CyberColor.green }
        if serverRunning { return CyberColor.orange }
        return CyberColor.textSecond.opacity(0.3)
    }

    var statusText: String {
        if available { return model.isEmpty ? "已就绪" : model }
        if serverRunning { return "运行中（无模型）" }
        return "未运行"
    }

    var body: some View {
        HStack(spacing: 6) {
            NeonDot(color: dotColor, size: 4)
            Text(name)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(CyberColor.textPrimary)
            Spacer()
            Text(statusText)
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(serverRunning ? CyberColor.textPrimary : CyberColor.textSecond)
                .lineLimit(1)
        }
    }
}

// MARK: - 模型选择统计

private struct ModelSelectorCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var info: ModelSelectorInfo { vm.modelSelectorInfo }

    var body: some View {
        CyberCard(glowColor: CyberColor.orange, padding: 12) {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    CyberLabel(text: "总决策次数", color: CyberColor.textSecond, size: 9)
                    Spacer()
                    Text("\(info.totalSelections)")
                        .font(.system(size: 12, weight: .bold, design: .monospaced))
                        .foregroundColor(CyberColor.orange)
                }

                if info.totalSelections > 0 {
                    VStack(alignment: .leading, spacing: 3) {
                        HStack {
                            Text("本地").font(.system(size: 9)).foregroundColor(CyberColor.green)
                            Spacer()
                            Text("远程").font(.system(size: 9)).foregroundColor(CyberColor.cyan)
                        }
                        GeometryReader { geo in
                            HStack(spacing: 0) {
                                Rectangle()
                                    .fill(CyberColor.green)
                                    .frame(width: geo.size.width * info.localRatio)
                                Rectangle()
                                    .fill(CyberColor.cyan)
                                    .frame(maxWidth: .infinity)
                            }
                            .clipShape(RoundedRectangle(cornerRadius: 3))
                        }
                        .frame(height: 8)
                        .animation(.easeInOut, value: info.localRatio)

                        HStack {
                            Text("\(Int(info.localRatio * 100))%")
                                .font(.system(size: 9)).foregroundColor(CyberColor.green)
                            Spacer()
                            Text("\(100 - Int(info.localRatio * 100))%")
                                .font(.system(size: 9)).foregroundColor(CyberColor.cyan)
                        }
                    }
                }

                HStack {
                    StatMiniItem(label: "本地成功率", value: "\(Int(info.localSuccessRate * 100))%", color: CyberColor.green)
                    Spacer()
                    StatMiniItem(label: "云端成功率", value: "\(Int(info.remoteSuccessRate * 100))%", color: CyberColor.cyan)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct StatMiniItem: View {
    let label: String
    let value: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.system(size: 9)).foregroundColor(CyberColor.textSecond)
            Text(value).font(.system(size: 11, weight: .semibold)).foregroundColor(color)
        }
    }
}

// MARK: - 向量记忆状态

private struct MemoryStatusCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        CyberCard(glowColor: CyberColor.purple, padding: 14) {
            HStack(spacing: 20) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        NeonDot(color: vm.memoryStatus.embeddingModelLoaded ? CyberColor.green : CyberColor.orange, size: 5)
                        Text(vm.memoryStatus.embeddingModelLoaded ? "BGE 模型已加载" : "BGE 模型加载中")
                            .font(.system(size: 10))
                            .foregroundColor(CyberColor.textSecond)
                    }

                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Text("\(vm.memoryStatus.totalMemories)")
                            .font(.system(size: 28, weight: .bold, design: .monospaced))
                            .foregroundColor(CyberColor.purple)
                        Text("条记忆")
                            .font(.caption)
                            .foregroundColor(CyberColor.textSecond)
                    }
                }

                Spacer()

                if !vm.memoryStatus.sessionSummary.isEmpty {
                    VStack(alignment: .leading, spacing: 3) {
                        CyberLabel(text: "会话分布", color: CyberColor.textSecond, size: 9)
                        ForEach(vm.memoryStatus.sessionSummary.sorted(by: { $0.key < $1.key }).prefix(4), id: \.key) { key, count in
                            HStack {
                                Text(key.count > 12 ? String(key.prefix(12)) + "…" : key)
                                    .font(.system(size: 9, design: .monospaced))
                                    .foregroundColor(CyberColor.textSecond)
                                Spacer()
                                Text("\(count)")
                                    .font(.system(size: 9, design: .monospaced))
                                    .foregroundColor(CyberColor.purpleDim)
                            }
                        }
                    }
                    .frame(maxWidth: 180)
                }
            }
        }
    }
}
