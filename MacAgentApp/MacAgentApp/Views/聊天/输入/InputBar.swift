import SwiftUI
import AppKit

struct InputBar: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @FocusState private var isFocused: Bool
    
    var body: some View {
        HStack(alignment: .bottom, spacing: 12) {
            CustomTextEditor(
                text: $viewModel.inputText,
                placeholder: "输入消息... (Enter 发送, Shift+Enter 换行)",
                onSubmit: sendMessage
            )
            .frame(minHeight: 36, maxHeight: 120)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(20)
            
            HStack(spacing: 8) {
                Button(action: sendAutonomousTask) {
                    Image(systemName: "robot")
                        .font(.title2)
                        .foregroundColor(canSend ? .orange : .secondary)
                }
                .buttonStyle(.plain)
                .disabled(!canSend && !viewModel.isLoading)
                .help("自主执行模式 (⌘⇧↵)")
                .keyboardShortcut(.return, modifiers: [.command, .shift])
                
                Button(action: viewModel.isLoading ? { viewModel.stopTask() } : sendMessage) {
                    Image(systemName: viewModel.isLoading ? "stop.circle.fill" : "arrow.up.circle.fill")
                        .font(.title)
                        .foregroundColor(viewModel.isLoading ? .red : (canSend ? .accentColor : .secondary))
                }
                .buttonStyle(.plain)
                .disabled(!canSend && !viewModel.isLoading)
                .help(viewModel.isLoading ? "终止任务" : "发送消息 (⌘↵)")
                .keyboardShortcut(.return, modifiers: .command)
            }
        }
        .padding()
        .background(Color(NSColor.windowBackgroundColor))
    }
    
    private var canSend: Bool {
        !viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && 
        !viewModel.isLoading &&
        viewModel.isConnected
    }
    
    private func sendMessage() {
        guard canSend else { return }
        viewModel.sendMessage()
    }
    
    private func sendAutonomousTask() {
        guard canSend else { return }
        viewModel.sendAutonomousTask()
    }
}
