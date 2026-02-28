import SwiftUI
#if os(macOS)
import AppKit
#endif

struct ContentView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @StateObject private var processManager = ProcessManager.shared
    @State private var showRestartAlert = false
    @Environment(\.openWindow) private var openWindow
    
    var body: some View {
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
        .frame(minWidth: 800, minHeight: 500)
        .toolbar {
            // 左侧：服务状态 + 系统消息铃铛
            ToolbarItem(placement: .navigation) {
                HStack(spacing: 8) {
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
                    
                    // 系统消息入口（铃铛），点击展开/收起系统消息面板
                    NotificationBellButton()
                        .environmentObject(viewModel)
                }
            }
            
            ToolbarItemGroup(placement: .primaryAction) {
                Button(action: { openWindow(id: "monitoring") }) {
                    Image(systemName: "chart.bar.xaxis")
                        .foregroundColor(Color(red: 0, green: 0.9, blue: 1.0).opacity(0.7))
                }
                .help("打开监控仪表板")

                Button(action: {
                    withAnimation {
                        viewModel.showToolPanel.toggle()
                    }
                }) {
                    Image(systemName: "sidebar.right")
                        .foregroundColor(viewModel.showToolPanel ? Color(red: 0, green: 0.9, blue: 1.0) : Color(red: 0, green: 0.9, blue: 1.0).opacity(0.5))
                }
                .help(viewModel.showToolPanel ? "隐藏工具面板" : "显示工具面板")
                
                Button(action: { viewModel.showSettings = true }) {
                    Image(systemName: "gear")
                        .foregroundColor(Color(red: 0, green: 0.9, blue: 1.0).opacity(0.7))
                }
                .help("设置")
            }
        }
        .navigationTitle("Chow Duck")
        .toolbarBackground(Color(red: 0.04, green: 0.04, blue: 0.08).opacity(0.85), for: .windowToolbar)
        .toolbarColorScheme(.dark, for: .windowToolbar)
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

struct ServiceStatusIndicator: View {
    let label: String
    let isRunning: Bool
    let onTap: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 4) {
                Circle()
                    .fill(isRunning ? CyberColor.green : CyberColor.red)
                    .frame(width: 8, height: 8)
                    .shadow(color: (isRunning ? CyberColor.green : CyberColor.red).opacity(0.5), radius: 4)
                Text(label)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(CyberColor.textPrimary)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
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
