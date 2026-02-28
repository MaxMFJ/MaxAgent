import SwiftUI

@main
struct MacAgentApp: App {
    @StateObject private var agentViewModel = AgentViewModel()
    @StateObject private var monitoringViewModel = MonitoringViewModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(agentViewModel)
                .frame(minWidth: 900, minHeight: 600)
                .onAppear {
                    monitoringViewModel.subscribeToAgentViewModel(agentViewModel)
                }
        }
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified(showsTitle: true))
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("新建对话") {
                    agentViewModel.newConversation()
                }
                .keyboardShortcut("n", modifiers: .command)
            }

            CommandGroup(after: .appSettings) {
                Button("设置...") {
                    agentViewModel.showSettings = true
                }
                .keyboardShortcut(",", modifiers: .command)
            }
        }

        // 监控仪表板窗口
        WindowGroup("监控仪表板", id: "monitoring") {
            MonitoringWindowView()
                .environmentObject(agentViewModel)
                .environmentObject(monitoringViewModel)
        }
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified(showsTitle: true))
        .defaultSize(width: 920, height: 600)

        Settings {
            SettingsView()
                .environmentObject(agentViewModel)
        }
    }
}
