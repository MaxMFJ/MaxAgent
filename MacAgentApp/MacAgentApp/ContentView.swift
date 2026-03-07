import SwiftUI
#if os(macOS)
import AppKit
#endif

struct ContentView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @StateObject private var processManager = ProcessManager.shared
    @State private var showRestartAlert = false
    
    var body: some View {
        VStack(spacing: 0) {
            // 自定义顶部栏（无系统边框，完全自控样式）
            CustomToolbarView(processManager: processManager)
                .environmentObject(viewModel)
            
            HSplitView {
                // 左侧边栏
                SidebarView()
                    .frame(minWidth: 200, idealWidth: 250, maxWidth: 300)
                
                // 中间聊天区域
                ChatView()
                    .frame(minWidth: 400)
                
                // 右侧工具面板（可隐藏）
                if viewModel.showToolPanel {
                    ToolPanelView()
                        .frame(minWidth: 250, idealWidth: 300, maxWidth: 400)
                }
                
                // 系统消息面板（可隐藏）
                if viewModel.showSystemMessages {
                    SystemMessageView()
                        .environmentObject(viewModel)
                        .frame(minWidth: 280, idealWidth: 360, maxWidth: 420)
                }
            }
        }
        .frame(minWidth: 800, minHeight: 500)
        .toolbar(.hidden, for: .windowToolbar)
        .navigationTitle("")
        .background(WindowButtonHider())
        .sheet(isPresented: $viewModel.showSettings) {
            SettingsView()
        }
        .alert("重启应用", isPresented: $showRestartAlert) {
            Button("确定") {
                restartApp()
            }
        } message: {
            Text("后端设置已更改，即将重启应用以生效。")
        }
        .onReceive(NotificationCenter.default.publisher(for: .backendSettingDidChange)) { _ in
            showRestartAlert = true
        }
        .onAppear {
            viewModel.connect()
            processManager.checkServicesStatus()
            
            // 设置后端启动后的回调
            processManager.onBackendStarted = { [weak viewModel] in
                // 延迟一秒后重新连接，确保后端完全启动
                Task {
                    try? await Task.sleep(nanoseconds: 1_500_000_000)
                    await MainActor.run {
                        viewModel?.connect()
                    }
                }
            }
        }
    }
    
    /// 重新启动当前 App（用于后端设置更改后恢复，避免用户误以为程序关闭）
    private func restartApp() {
#if os(macOS)
        let path = Bundle.main.bundlePath
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        proc.arguments = ["-n", path]
        try? proc.run()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            NSApplication.shared.terminate(nil)
        }
#endif
    }
}

/// 自定义窗口控制按钮（关闭、最小化、放大）
private struct WindowTrafficLightButtons: View {
    var body: some View {
#if os(macOS)
        HStack(spacing: 8) {
            TrafficLightButton(color: .red) {
                NSApplication.shared.keyWindow?.close()
            }
            .help("关闭")
            TrafficLightButton(color: .yellow) {
                NSApplication.shared.keyWindow?.miniaturize(nil)
            }
            .help("最小化")
            TrafficLightButton(color: .green) {
                NSApplication.shared.keyWindow?.zoom(nil)
            }
            .help("放大")
        }
        .padding(.trailing, 12)
#endif
    }
}

#if os(macOS)
/// 隐藏系统默认交通灯，使用自定义按钮
private struct WindowButtonHider: NSViewRepresentable {
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

private struct TrafficLightButton: View {
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

/// 自定义顶部栏：无系统边框，完全自控样式
private struct CustomToolbarView: View {
    @ObservedObject var processManager: ProcessManager
    @EnvironmentObject var viewModel: AgentViewModel
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        HStack {
            // 左侧：窗口控制 + 服务状态 + 铃铛
            HStack(spacing: 10) {
                WindowTrafficLightButtons()
                ServiceStatusIndicator(
                    label: "后端",
                    isRunning: processManager.isBackendRunning,
                    onTap: {
                        if processManager.isBackendRunning {
                            processManager.stopBackend()
                        } else {
                            processManager.startBackend()
                        }
                    }
                )
                ServiceStatusIndicator(
                    label: "Ollama",
                    isRunning: processManager.isOllamaRunning,
                    onTap: {
                        if processManager.isOllamaRunning {
                            processManager.stopOllama()
                        } else {
                            processManager.startOllama()
                        }
                    }
                )
                NotificationBellButton()
                    .environmentObject(viewModel)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            // 中间：标题
            ChowDuckTitleView()
                .frame(maxWidth: .infinity, alignment: .center)

            // 右侧：监控、工具面板、设置
            HStack(spacing: 8) {
                ToolbarIconButton(systemName: "chart.bar.xaxis", color: CyberColor.cyan.opacity(0.7)) {
                    openWindow(id: "monitoring")
                }
                .help("打开监控仪表板")

                ToolbarIconButton(
                    systemName: "sidebar.right",
                    color: viewModel.showToolPanel ? CyberColor.cyan : CyberColor.cyan.opacity(0.5)
                ) {
                    withAnimation { viewModel.showToolPanel.toggle() }
                }
                .help(viewModel.showToolPanel ? "隐藏工具面板" : "显示工具面板")

                ToolbarIconButton(systemName: "gear", color: CyberColor.cyan.opacity(0.7)) {
                    viewModel.showSettings = true
                }
                .help("设置")
            }
            .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .frame(minHeight: 52)
        .background(CyberColor.bg0.opacity(0.85))
        .buttonStyle(.plain)
    }
}

/// 程序标题：霓虹发光 + 呼吸动画（官网 Chow Duck 赛博朋克效果，无边框）
private struct ChowDuckTitleView: View {
    @State private var breathePhase = false

    var body: some View {
        Text("Chow Duck")
            .font(CyberFont.display(size: 20, weight: .bold))
            .foregroundStyle(CyberColor.textPrimary)
            .tracking(1.5)
            .shadow(color: CyberColor.cyan.opacity(breathePhase ? 0.95 : 0.55), radius: breathePhase ? 10 : 5)
            .shadow(color: CyberColor.cyan.opacity(breathePhase ? 0.8 : 0.4), radius: breathePhase ? 22 : 14)
            .shadow(color: CyberColor.cyan.opacity(breathePhase ? 0.5 : 0.25), radius: breathePhase ? 40 : 26)
            .animation(.easeInOut(duration: 1.5).repeatForever(autoreverses: true), value: breathePhase)
            .onAppear { breathePhase = true }
    }
}

/// 顶部栏图标按钮：统一尺寸与点击区域
private struct ToolbarIconButton: View {
    let systemName: String
    let color: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 17, weight: .medium))
                .foregroundColor(color)
                .frame(width: 36, height: 36)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

struct ServiceStatusIndicator: View {
    let label: String
    let isRunning: Bool
    let onTap: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 6) {
                Circle()
                    .fill(isRunning ? CyberColor.green : CyberColor.red)
                    .frame(width: 10, height: 10)
                    .shadow(color: (isRunning ? CyberColor.green : CyberColor.red).opacity(0.5), radius: 4)
                Text(label)
                    .font(CyberFont.mono(size: 12))
                    .foregroundColor(CyberColor.textPrimary)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(CyberColor.bg2)
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(CyberColor.border, lineWidth: 0.5)
            )
            .cornerRadius(6)
        }
        .buttonStyle(.plain)
        .help(isRunning ? "点击停止 \(label)" : "点击启动 \(label)")
    }
}

#Preview {
    ContentView()
        .environmentObject(AgentViewModel())
}
