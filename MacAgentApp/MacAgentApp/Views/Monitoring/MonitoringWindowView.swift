import SwiftUI

struct MonitoringWindowView: View {
    @EnvironmentObject var agentViewModel: AgentViewModel
    @StateObject private var vm = MonitoringViewModel()
    @State private var selectedTab = 0

    var body: some View {
        ZStack {
            // Layered background: deep dark + hex grid
            CyberColor.bg0.ignoresSafeArea()
            HexGridPattern().ignoresSafeArea()

            VStack(spacing: 0) {
                // ── Top bar ────────────────────────────────────────────────
                HStack(spacing: 0) {
                    // Brand mark（有趣：AI 工作时脉动）
                    HStack(spacing: 6) {
                        Image(systemName: "brain.head.profile")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(vm.isStreamingLLM ? CyberColor.purple : CyberColor.cyan)
                            .shadow(color: (vm.isStreamingLLM ? CyberColor.purple : CyberColor.cyan).opacity(0.8), radius: vm.isStreamingLLM ? 6 : 4)
                        Text("AI 监控中心")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(CyberColor.textPrimary)
                        if vm.isStreamingLLM {
                            Text("· 思考中")
                                .font(.system(size: 10))
                                .foregroundColor(CyberColor.purple)
                        }
                    }
                    .padding(.leading, 16)

                    Spacer()

                    // Tabs
                    HStack(spacing: 2) {
                        CyberTabButton(title: "EXEC", icon: "timeline.selection.left", tag: 0, selected: $selectedTab)
                        CyberTabButton(title: "SYS",  icon: "chart.bar.fill",          tag: 1, selected: $selectedTab)
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
                    case 0: ExecutionTimelineView().environmentObject(vm)
                    case 1: SystemStatusDashboardView().environmentObject(vm)
                    case 2: HistoryAnalysisView().environmentObject(vm)
                    case 3: LogStreamView().environmentObject(vm)
                    default: ExecutionTimelineView().environmentObject(vm)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)

                // ── Status bar ─────────────────────────────────────────────
                CyberStatusBar(vm: vm)
            }
        }
        .frame(minWidth: 900, minHeight: 580)
        .onAppear {
            vm.subscribeToAgentViewModel(agentViewModel)
            vm.startPolling()
        }
        .onDisappear { vm.stopPolling() }
    }
}

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
                    .font(.system(size: 11, weight: .semibold))
                Text(title)
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
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
                    .font(.system(size: 9, weight: .semibold, design: .monospaced))
                    .foregroundColor(vm.healthInfo.backendHealthy ? CyberColor.green : CyberColor.red)
                    .tracking(1)
            }
            .padding(.horizontal, 12)

            cyberDivider()

            // WS connections
            HStack(spacing: 4) {
                Image(systemName: "wifi")
                    .font(.system(size: 9))
                    .foregroundColor(CyberColor.cyanDim)
                Text("\(vm.healthInfo.wsConnectionCount) CONN")
                    .font(.system(size: 9, design: .monospaced))
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
                        .font(.system(size: 9, weight: .semibold, design: .monospaced))
                        .foregroundColor(CyberColor.purple)
                        .tracking(1)
                }
                .padding(.horizontal, 12)
                cyberDivider()
            }

            // Model
            Text(vm.healthInfo.llmModel.isEmpty || vm.healthInfo.llmModel == "--"
                 ? "MODEL: N/A" : "MDL: \(vm.healthInfo.llmModel)")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(CyberColor.textSecond)
                .lineLimit(1)
                .padding(.horizontal, 12)

            Spacer()

            // Last update
            if let last = vm.lastPolledAt {
                Text("UPD \(last, style: .relative)")
                    .font(.system(size: 9, design: .monospaced))
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
