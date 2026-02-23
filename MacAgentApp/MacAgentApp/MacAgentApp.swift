import SwiftUI

@main
struct MacAgentApp: App {
    @StateObject private var agentViewModel = AgentViewModel()
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(agentViewModel)
                .frame(minWidth: 900, minHeight: 600)
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
        
        Settings {
            SettingsView()
                .environmentObject(agentViewModel)
        }
    }
}
