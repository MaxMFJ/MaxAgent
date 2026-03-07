import SwiftUI
#if os(macOS)
import AppKit
#endif

struct MonitoringWindowView: View {
    @EnvironmentObject var agentViewModel: AgentViewModel
    @EnvironmentObject var vm: MonitoringViewModel
    @State private var selectedTab = 0

    var body: some View {
        ZStack {
            // Layered background: deep dark + hex grid
            CyberColor.bg0.ignoresSafeArea()
            HexGridPattern().ignoresSafeArea()

            VStack(spacing: 0) {
                // ── Top bar ────────────────────────────────────────────────
                HStack(spacing: 0) {
                    // 窗口控制按钮
                    MonitoringWindowTrafficLights()
                        .padding(.leading, 12)

                    // Brand mark（有趣：AI 工作时脉动）
                    HStack(spacing: 6) {
                        Image(systemName: "brain.head.profile")
                            .font(CyberFont.display(size: 14, weight: .bold))
                            .foregroundColor(vm.isStreamingLLM ? CyberColor.purple : CyberColor.cyan)
                            .shadow(color: (vm.isStreamingLLM ? CyberColor.purple : CyberColor.cyan).opacity(0.8), radius: vm.isStreamingLLM ? 6 : 4)
                        Text("AI 监控中心")
                            .font(CyberFont.display(size: 12, weight: .bold))
                            .foregroundColor(CyberColor.textPrimary)
                        if vm.isStreamingLLM {
                            Text("· 思考中")
                                .font(CyberFont.body(size: 10))
                                .foregroundColor(CyberColor.purple)
                        }
                    }
                    .padding(.leading, 16)

                    Spacer()

                    // Tabs
                    HStack(spacing: 2) {
                        CyberTabButton(title: "LIVE", icon: "waveform.path",            tag: 6, selected: $selectedTab)
                        CyberTabButton(title: "EXEC", icon: "play.circle", tag: 0, selected: $selectedTab)
                        CyberTabButton(title: "SYS",  icon: "chart.bar.fill",          tag: 1, selected: $selectedTab)
                        CyberTabButton(title: "STATS", icon: "chart.pie.fill",          tag: 4, selected: $selectedTab)
                        CyberTabButton(title: "TRACE", icon: "waveform.path.ecg",       tag: 5, selected: $selectedTab)
                        CyberTabButton(title: "HIST", icon: "clock.arrow.circlepath",  tag: 2, selected: $selectedTab)
                        CyberTabButton(title: "LOGS", icon: "list.bullet.rectangle",   tag: 3, selected: $selectedTab)
                    }
                    .padding(.trailing, 12)
                }
                .padding(.vertical, 8)
                .background(CyberColor.bg1)
                .overlay(
                    Rectangle()
                        .fill(
                            LinearGradient(
                                colors: [CyberColor.cyan.opacity(0.5), CyberColor.purple.opacity(0.3)],
                                startPoint: .leading, endPoint: .trailing
                            )
                        )
                        .frame(height: 1),
                    alignment: .bottom
                )

                // ── Content ────────────────────────────────────────────────
                Group {
                    switch selectedTab {
                    case 6: AgentLiveView().environmentObject(vm)
                    case 0: ExecutionTimelineView().environmentObject(vm)
                    case 1: SystemStatusDashboardView().environmentObject(vm)
                    case 2: HistoryAnalysisView().environmentObject(vm)
                    case 3: LogStreamView().environmentObject(vm)
                    case 4: UsageStatisticsView().environmentObject(vm)
                    case 5: TracesDashboardView().environmentObject(vm)
                    default: AgentLiveView().environmentObject(vm)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)

                // ── Status bar ─────────────────────────────────────────────
                CyberStatusBar(vm: vm)
            }
        }
        .frame(minWidth: 900, minHeight: 580)
        .background(MonitoringWindowButtonHider())
        .onAppear {
            vm.subscribeToAgentViewModel(agentViewModel)
            vm.startPolling()
        }
        .onDisappear { vm.stopPolling() }
    }
}

// MARK: - 窗口控制按钮（监控仪表板）

#if os(macOS)
/// 隐藏监控窗口的系统默认交通灯
private struct MonitoringWindowButtonHider: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let v = NSView()
        DispatchQueue.main.async {
            v.window?.standardWindowButton(.closeButton)?.isHidden = true
            v.window?.standardWindowButton(.miniaturizeButton)?.isHidden = true
            v.window?.standardWindowButton(.zoomButton)?.isHidden = true
        }
        return v
    }
    func updateNSView(_ nsView: NSView, context: Context) {
        nsView.window?.standardWindowButton(.closeButton)?.isHidden = true
        nsView.window?.standardWindowButton(.miniaturizeButton)?.isHidden = true
        nsView.window?.standardWindowButton(.zoomButton)?.isHidden = true
    }
}

private struct MonitoringWindowTrafficLights: View {
    var body: some View {
        HStack(spacing: 8) {
            MonitoringTrafficLightButton(color: .red) {
                NSApplication.shared.keyWindow?.close()
            }
            .help("关闭")
            MonitoringTrafficLightButton(color: .yellow) {
                NSApplication.shared.keyWindow?.miniaturize(nil)
            }
            .help("最小化")
            MonitoringTrafficLightButton(color: .green) {
                NSApplication.shared.keyWindow?.zoom(nil)
            }
            .help("放大")
        }
    }
}

private struct MonitoringTrafficLightButton: View {
    let color: Color
    let action: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            Circle()
                .fill(color.opacity(isHovered ? 1 : 0.85))
                .frame(width: 12, height: 12)
                .overlay(
                    Circle()
                        .stroke(Color.white.opacity(0.3), lineWidth: 0.5)
                )
        }
        .buttonStyle(.plain)
        .onHover { isHovered = $0 }
    }
}
#endif

// MARK: - Cyber Tab Button

private struct CyberTabButton: View {
    let title: String
    let icon: String
    let tag: Int
    @Binding var selected: Int

    var isSelected: Bool { selected == tag }

    var body: some View {
        Button(action: { selected = tag }) {
                    HStack(spacing: 5) {
                Image(systemName: icon)
                    .font(CyberFont.display(size: 11, weight: .semibold))
                Text(title)
                    .font(CyberFont.display(size: 11, weight: .semibold))
                    .tracking(1)
            }
            .foregroundColor(isSelected ? CyberColor.bg0 : CyberColor.textSecond)
            .padding(.horizontal, 14)
            .padding(.vertical, 6)
            .background(
                Group {
                    if isSelected {
                        LinearGradient(
                            colors: [CyberColor.cyan, CyberColor.cyan.opacity(0.7)],
                            startPoint: .topLeading, endPoint: .bottomTrailing
                        )
                        .shadow(color: CyberColor.cyan.opacity(0.5), radius: 6)
                    } else {
                        Color.clear
                    }
                }
            )
            .cornerRadius(5)
            .overlay(
                RoundedRectangle(cornerRadius: 5)
                    .stroke(isSelected ? CyberColor.cyan.opacity(0.0) : CyberColor.border, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .animation(.easeInOut(duration: 0.15), value: isSelected)
    }
}

// MARK: - Cyber Status Bar

private struct CyberStatusBar: View {
    @ObservedObject var vm: MonitoringViewModel

    var body: some View {
        HStack(spacing: 0) {
            // Backend status
            HStack(spacing: 5) {
                NeonDot(color: vm.healthInfo.backendHealthy ? CyberColor.green : CyberColor.red, size: 5)
                Text(vm.healthInfo.backendHealthy ? "ONLINE" : "OFFLINE")
                    .font(CyberFont.mono(size: 9, weight: .semibold))
                    .foregroundColor(vm.healthInfo.backendHealthy ? CyberColor.green : CyberColor.red)
                    .tracking(1)
            }
            .padding(.horizontal, 12)

            cyberDivider()

            // WS connections
            HStack(spacing: 4) {
                Image(systemName: "wifi")
                    .font(CyberFont.mono(size: 9))
                    .foregroundColor(CyberColor.cyanDim)
                Text("\(vm.healthInfo.wsConnectionCount) CONN")
                    .font(CyberFont.mono(size: 9))
                    .foregroundColor(CyberColor.textSecond)
                    .tracking(1)
            }
            .padding(.horizontal, 12)

            cyberDivider()

            // LLM streaming indicator
            if vm.isStreamingLLM {
                HStack(spacing: 4) {
                    NeonDot(color: CyberColor.purple, size: 5)
                        Text("NEURAL STREAM")
                        .font(CyberFont.mono(size: 9, weight: .semibold))
                        .foregroundColor(CyberColor.purple)
                        .tracking(1)
                }
                .padding(.horizontal, 12)
                cyberDivider()
            }

            // Model
                Text(vm.healthInfo.llmModel.isEmpty || vm.healthInfo.llmModel == "--"
                 ? "MODEL: N/A" : "MDL: \(vm.healthInfo.llmModel)")
                .font(CyberFont.mono(size: 9))
                .foregroundColor(CyberColor.textSecond)
                .lineLimit(1)
                .padding(.horizontal, 12)

            Spacer()

            // Last update
            if let last = vm.lastPolledAt {
                Text("UPD \(last, style: .relative)")
                    .font(CyberFont.mono(size: 9))
                    .foregroundColor(CyberColor.textSecond.opacity(0.6))
                    .padding(.trailing, 8)
            }

            if vm.isPolling {
                ProgressView()
                    .scaleEffect(0.45)
                    .frame(width: 12, height: 12)
                    .colorMultiply(CyberColor.cyan)
                    .padding(.trailing, 12)
            }
        }
        .frame(height: 26)
        .background(CyberColor.bg1)
        .overlay(
            Rectangle()
                .fill(CyberColor.cyan.opacity(0.25))
                .frame(height: 1),
            alignment: .top
        )
    }

    private func cyberDivider() -> some View {
        Rectangle()
            .fill(CyberColor.border)
            .frame(width: 1, height: 14)
    }
}
