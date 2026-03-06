import SwiftUI
import CoreText

@main
struct MacAgentApp: App {
    @StateObject private var agentViewModel = AgentViewModel()
    @StateObject private var monitoringViewModel = MonitoringViewModel()

    init() {
        registerOrbitronFont()
    }

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
        .windowToolbarStyle(.unified(showsTitle: false))
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

    /// 启动时显式注册 Orbitron 字体，确保 NSFont/CTFont 能正确加载（避免回退到 PingFang）
    private func registerOrbitronFont() {
        let url = Bundle.main.url(forResource: "Orbitron-Variable", withExtension: "ttf", subdirectory: "Fonts")
            ?? Bundle.main.url(forResource: "Orbitron-Variable", withExtension: "ttf")
            ?? Bundle.main.resourceURL?.appendingPathComponent("Fonts/Orbitron-Variable.ttf")
        guard let fontURL = url, FileManager.default.fileExists(atPath: fontURL.path) else { return }
        let urls = [fontURL] as CFArray
        CTFontManagerRegisterFontURLs(urls, .process, true) { _, _ in true }
    }
}
