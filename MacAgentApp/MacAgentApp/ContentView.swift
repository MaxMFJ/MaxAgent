import SwiftUI

struct ContentView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @StateObject private var processManager = ProcessManager.shared
    
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
        }
        .frame(minWidth: 800, minHeight: 500)
        .toolbar {
            // 服务状态指示器
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
                }
            }
            
            ToolbarItemGroup(placement: .primaryAction) {
                Button(action: { 
                    withAnimation {
                        viewModel.showToolPanel.toggle()
                    }
                }) {
                    Image(systemName: "sidebar.right")
                        .foregroundColor(viewModel.showToolPanel ? .accentColor : .secondary)
                }
                .help(viewModel.showToolPanel ? "隐藏工具面板" : "显示工具面板")
                
                Button(action: { viewModel.showSettings = true }) {
                    Image(systemName: "gear")
                }
                .help("设置")
            }
        }
        .navigationTitle("MacAgent")
        .sheet(isPresented: $viewModel.showSettings) {
            SettingsView()
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
}

struct ServiceStatusIndicator: View {
    let label: String
    let isRunning: Bool
    let onTap: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 4) {
                Circle()
                    .fill(isRunning ? Color.green : Color.red)
                    .frame(width: 8, height: 8)
                Text(label)
                    .font(.caption)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Color(NSColor.controlBackgroundColor))
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
