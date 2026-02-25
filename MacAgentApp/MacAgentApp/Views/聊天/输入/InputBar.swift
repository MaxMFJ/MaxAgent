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
            
            HStack(spacing: 10) {
                Button(action: sendAutonomousTask) {
                    Image(systemName: "robot")
                        .font(.system(size: 20, weight: .medium))
                        .foregroundColor(canSend ? .orange : Color.primary.opacity(0.5))
                        .frame(width: 36, height: 36)
                        .background(canSend ? Color.orange.opacity(0.15) : Color.clear)
                        .clipShape(Circle())
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(!canSend && !viewModel.isLoading)
                .help("自主执行：自动选择本地/远程模型 (⌘⇧↵)")
                .keyboardShortcut(.return, modifiers: [.command, .shift])
                
                Button(action: viewModel.isLoading ? { viewModel.stopTask() } : sendMessage) {
                    Image(systemName: viewModel.isLoading ? "stop.circle.fill" : "arrow.up.circle.fill")
                        .font(.system(size: 22))
                        .foregroundColor(viewModel.isLoading ? .red : (canSend ? .accentColor : Color.primary.opacity(0.5)))
                        .frame(width: 36, height: 36)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(!canSend && !viewModel.isLoading)
                .help(viewModel.isLoading ? "终止任务" : "发送消息 (⌘↵)")
                .keyboardShortcut(.return, modifiers: .command)
            }
            .fixedSize(horizontal: true, vertical: false)
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
