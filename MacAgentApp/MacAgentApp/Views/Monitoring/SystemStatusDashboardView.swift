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

                // 熔断器状态（全宽）
                CircuitBreakerCard()
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
                                .font(CyberFont.display(size: 20))
                                .foregroundColor(CyberColor.cyan)
                        }
                        Text(vm.isStreamingLLM ? "AI 正在思考" : "活动趋势")
                            .font(CyberFont.body(size: 12, weight: .semibold))
                            .foregroundColor(CyberColor.textPrimary)
                    }
                    Text(vm.isStreamingLLM ? "神经网络活跃中..." : "Token 消耗随时间变化")
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                }

                MiniSparkLineChart(values: sparklineValues, color: vm.isStreamingLLM ? CyberColor.purple : CyberColor.cyan, height: 44)
                    .frame(maxWidth: .infinity)
            }
        }
    }
}

// MARK: - 深度健康检查总览 (/health/deep — 8 子系统)

private struct ServiceHealthCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    private static let subsystemMeta: [String: (icon: String, label: String)] = [
        "llm":          ("brain.head.profile", "LLM"),
        "disk":         ("internaldrive",      "磁盘"),
        "memory":       ("memorychip",         "内存"),
        "vector_db":    ("cylinder.split.1x2", "向量库"),
        "tools":        ("wrench.and.screwdriver", "工具"),
        "task_tracker": ("list.bullet.clipboard", "任务"),
        "traces":       ("waveform.path.ecg",  "Traces"),
        "evomap":       ("arrow.triangle.2.circlepath", "EvoMap"),
    ]

    // 排序键：保证显示顺序一致
    private static let subsystemOrder = ["llm", "disk", "memory", "vector_db", "tools", "task_tracker", "traces", "evomap"]

    var body: some View {
        CyberCard(glowColor: overallGlow, padding: 14) {
            VStack(alignment: .leading, spacing: 10) {
                // 顶部状态行
                HStack(spacing: 8) {
                    NeonDot(color: vm.deepHealth.healthy ? CyberColor.green : CyberColor.red, size: 6)
                    Text(vm.deepHealth.healthy ? "系统健康" : "检测到异常")
                        .font(CyberFont.body(size: 12, weight: .bold))
                        .foregroundColor(vm.deepHealth.healthy ? CyberColor.green : CyberColor.red)
                    Spacer()
                    if vm.deepHealth.checkDurationMs > 0 {
                        Text(String(format: "%.0fms", vm.deepHealth.checkDurationMs))
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(CyberColor.textSecond)
                    }
                    Text(vm.deepHealth.serverStatus.uppercased())
                        .font(CyberFont.mono(size: 9, weight: .semibold))
                        .foregroundColor(CyberColor.cyanDim)
                        .tracking(1)
                }

                // 8 子系统网格
                let columns = [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())]
                LazyVGrid(columns: columns, spacing: 8) {
                    ForEach(Self.subsystemOrder, id: \.self) { key in
                        if let check = vm.deepHealth.checks.first(where: { $0.id == key }) {
                            let meta = Self.subsystemMeta[key] ?? ("questionmark.circle", key)
                            SubsystemCell(check: check, icon: meta.icon, label: meta.label)
                        }
                    }
                }

                // 失败的 required 子系统警告
                if !vm.deepHealth.requiredFailed.isEmpty {
                    HStack(spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(CyberFont.body(size: 11))
                            .foregroundColor(CyberColor.red)
                        Text("关键失败: \(vm.deepHealth.requiredFailed.joined(separator: ", "))")
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(CyberColor.red)
                    }
                    .padding(.top, 2)
                }
            }
        }
    }

    private var overallGlow: Color {
        vm.deepHealth.healthy ? CyberColor.green : CyberColor.red
    }
}

private struct SubsystemCell: View {
    let check: DeepHealthCheck
    let icon: String
    let label: String

    @State private var showDetail = false

    var body: some View {
        VStack(spacing: 5) {
            ZStack(alignment: .bottomTrailing) {
                Image(systemName: icon)
                    .font(CyberFont.display(size: 20))
                    .foregroundColor(check.ok ? CyberColor.cyan : CyberColor.red.opacity(0.8))
                NeonDot(color: check.ok ? CyberColor.green : CyberColor.red, size: 4)
            }
            Text(label)
                .font(CyberFont.mono(size: 9, weight: .semibold))
                .foregroundColor(CyberColor.textSecond)
                .tracking(0.5)
            if check.required {
                Text("必需")
                    .font(CyberFont.body(size: 7, weight: .bold))
                    .foregroundColor(CyberColor.orange)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 1)
                    .background(CyberColor.orange.opacity(0.15))
                    .cornerRadius(3)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
        .background(check.ok ? CyberColor.bg2.opacity(0.5) : CyberColor.red.opacity(0.08))
        .cornerRadius(6)
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(check.ok ? CyberColor.border : CyberColor.red.opacity(0.3), lineWidth: 0.5)
        )
        .onTapGesture { showDetail.toggle() }
        .popover(isPresented: $showDetail) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    NeonDot(color: check.ok ? CyberColor.green : CyberColor.red, size: 5)
                    Text(check.id.uppercased())
                        .font(CyberFont.mono(size: 11, weight: .bold))
                        .foregroundColor(CyberColor.textPrimary)
                }
                Text(check.detail)
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(CyberColor.textSecond)
                    .lineLimit(5)
                if let lat = check.latencyMs, lat > 0 {
                    Text("延迟: \(String(format: "%.1f", lat))ms")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.cyanDim)
                }
                Text(check.required ? "必需子系统" : "可选子系统")
                    .font(CyberFont.mono(size: 9))
                    .foregroundColor(check.required ? CyberColor.orange : CyberColor.textSecond)
            }
            .padding(12)
            .frame(minWidth: 200)
            .background(CyberColor.bg1)
        }
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
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(CyberColor.purple)
                    CyberLabel(text: vm.healthInfo.llmProvider.uppercased(),
                               color: CyberColor.purple, size: 9)
                }

                Text(vm.healthInfo.llmModel)
                    .font(CyberFont.mono(size: 13, weight: .semibold))
                    .foregroundColor(CyberColor.textPrimary)
                    .lineLimit(2)

                HStack(spacing: 4) {
                    NeonDot(color: vm.healthInfo.backendHealthy ? CyberColor.green : CyberColor.red, size: 4)
                    Text(vm.healthInfo.backendHealthy ? "已连接" : "未连接")
                        .font(CyberFont.body(size: 10))
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
                        .font(CyberFont.mono(size: 34, weight: .bold))
                        .foregroundColor(CyberColor.cyan)
                        .contentTransition(.numericText())
                        .animation(.spring(), value: vm.healthInfo.wsConnectionCount)
                    Text("个连接")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(CyberColor.textSecond)
                }

                ForEach(vm.healthInfo.wsConnectionsByType.sorted(by: { $0.key < $1.key }), id: \.key) { key, val in
                    HStack {
                        Text(key == "mac" ? "Mac" : key == "ios" ? "iOS" : key)
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(CyberColor.textSecond)
                        Spacer()
                        Text("\(val)")
                            .font(CyberFont.mono(size: 10))
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
                .font(CyberFont.body(size: 10, weight: .semibold))
                .foregroundColor(CyberColor.textPrimary)
            Spacer()
            Text(statusText)
                .font(CyberFont.mono(size: 10))
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
                        .font(CyberFont.mono(size: 12, weight: .bold))
                        .foregroundColor(CyberColor.orange)
                }

                if info.totalSelections > 0 {
                    VStack(alignment: .leading, spacing: 3) {
                        HStack {
                            Text("本地").font(CyberFont.mono(size: 9)).foregroundColor(CyberColor.green)
                            Spacer()
                            Text("远程").font(CyberFont.mono(size: 9)).foregroundColor(CyberColor.cyan)
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
                                .font(CyberFont.mono(size: 9)).foregroundColor(CyberColor.green)
                            Spacer()
                            Text("\(100 - Int(info.localRatio * 100))%")
                                .font(CyberFont.mono(size: 9)).foregroundColor(CyberColor.cyan)
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
            Text(label).font(CyberFont.mono(size: 9)).foregroundColor(CyberColor.textSecond)
            Text(value).font(CyberFont.body(size: 11, weight: .semibold)).foregroundColor(color)
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
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(CyberColor.textSecond)
                    }

                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Text("\(vm.memoryStatus.totalMemories)")
                            .font(CyberFont.mono(size: 28, weight: .bold))
                            .foregroundColor(CyberColor.purple)
                        Text("条记忆")
                            .font(CyberFont.body(size: 11))
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
                                    .font(CyberFont.mono(size: 9))
                                    .foregroundColor(CyberColor.textSecond)
                                Spacer()
                                Text("\(count)")
                                    .font(CyberFont.mono(size: 9))
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

// MARK: - 熔断器状态

private struct CircuitBreakerCard: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        CyberCard(glowColor: CyberColor.orange, padding: 14) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "bolt.trianglebadge.exclamationmark.fill")
                        .font(.system(size: 12))
                        .foregroundColor(CyberColor.orange)
                    Text("LLM 熔断器")
                        .font(CyberFont.body(size: 11, weight: .semibold))
                        .foregroundColor(CyberColor.textPrimary)
                    Spacer()
                }

                if vm.circuitBreakers.isEmpty {
                    Text("无活跃断路器")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                } else {
                    ForEach(Array(vm.circuitBreakers.enumerated()), id: \.offset) { _, cb in
                        CircuitBreakerRow(cb: cb)
                    }
                }
            }
        }
    }
}

private struct CircuitBreakerRow: View {
    let cb: [String: Any]

    private var name: String { cb["name"] as? String ?? "unknown" }
    private var state: String { cb["state"] as? String ?? "closed" }
    private var failureCount: Int { cb["failure_count"] as? Int ?? 0 }
    private var totalTrips: Int { cb["total_trips"] as? Int ?? 0 }
    private var threshold: Int { cb["failure_threshold"] as? Int ?? 5 }

    private var stateColor: Color {
        switch state {
        case "closed": return CyberColor.green
        case "open": return CyberColor.red
        case "half_open": return CyberColor.orange
        default: return CyberColor.textSecond
        }
    }

    private var stateLabel: String {
        switch state {
        case "closed": return "正常"
        case "open": return "熔断"
        case "half_open": return "恢复中"
        default: return state.uppercased()
        }
    }

    var body: some View {
        HStack(spacing: 10) {
            NeonDot(color: stateColor, size: 6)
            Text(name)
                .font(CyberFont.mono(size: 10))
                .foregroundColor(CyberColor.textPrimary)
            Text(stateLabel)
                .font(CyberFont.mono(size: 9, weight: .bold))
                .foregroundColor(stateColor)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(stateColor.opacity(0.15))
                .cornerRadius(3)
            Spacer()
            VStack(alignment: .trailing, spacing: 1) {
                Text("失败 \(failureCount)/\(threshold)")
                    .font(CyberFont.mono(size: 9))
                    .foregroundColor(failureCount > 0 ? CyberColor.orange : CyberColor.textSecond)
                Text("熔断 \(totalTrips) 次")
                    .font(CyberFont.mono(size: 9))
                    .foregroundColor(totalTrips > 0 ? CyberColor.red : CyberColor.textSecond)
            }
        }
    }
}
