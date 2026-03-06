import SwiftUI
import AppKit

struct InputBar: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @FocusState private var isFocused: Bool
    
    /// 输入框显示内容：语音输入时为识别结果，否则为输入文本
    private var displayText: Binding<String> {
        if viewModel.isVoiceInputActive {
            return Binding(
                get: { viewModel.voiceInputService.finalText + viewModel.voiceInputService.interimText },
                set: { _ in }
            )
        }
        return $viewModel.inputText
    }
    
    private var placeholder: String {
        if viewModel.isVoiceInputActive {
            return "正在听... 静音 \(Int(viewModel.sttSilenceSeconds)) 秒后自动发送"
        }
        return "输入消息... (Enter 发送, Shift+Enter 换行)"
    }
    
    var body: some View {
        HStack(alignment: .bottom, spacing: 12) {
            CustomTextEditor(
                text: displayText,
                placeholder: placeholder,
                onSubmit: onSubmit
            )
            .frame(minHeight: 36, maxHeight: 120)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(viewModel.isVoiceInputActive ? CyberColor.red.opacity(0.12) : CyberColor.bg2)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(CyberColor.cyan.opacity(0.25), lineWidth: 0.5)
            )
            .cornerRadius(12)
            
            HStack(spacing: 10) {
                // 语音输入
                Button(action: toggleVoiceInput) {
                    Image(systemName: viewModel.isVoiceInputActive ? "mic.fill" : "mic")
                        .font(CyberFont.body(size: 18, weight: .medium))
                        .foregroundColor(viewModel.isVoiceInputActive ? .red : (viewModel.isLoading ? CyberColor.textSecond.opacity(0.5) : CyberColor.cyan))
                        .frame(width: 36, height: 36)
                        .background(viewModel.isVoiceInputActive ? Color.red.opacity(0.15) : Color.clear)
                        .clipShape(Circle())
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(viewModel.isLoading)
                .help(viewModel.isVoiceInputActive ? "停止语音输入" : "语音输入（静音自动发送）")
                
                Button(action: sendAutonomousTask) {
                    HStack(spacing: 3) {
                        Image(systemName: "robot")
                            .font(CyberFont.body(size: 20, weight: .medium))
                        if viewModel.preferredModelTier != "auto" {
                            Text(tierShortName(viewModel.preferredModelTier))
                                .font(.system(size: 8, weight: .bold))
                                .foregroundColor(CyberColor.green)
                        }
                    }
                    .foregroundColor(canSend ? CyberColor.green : CyberColor.textSecond.opacity(0.5))
                    .frame(width: 36, height: 36)
                    .background(canSend ? CyberColor.green.opacity(0.15) : Color.clear)
                    .clipShape(Circle())
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(!canSend && !viewModel.isLoading)
                .help("自主执行：按住可选择模型层级 (⌘⇧↵)")
                .keyboardShortcut(.return, modifiers: [.command, .shift])
                .contextMenu {
                    Button("⚡ 自动选择（推荐）") { viewModel.preferredModelTier = "auto" }
                    Button("🔍 快速 Fast（本地/轻量）") { viewModel.preferredModelTier = "fast" }
                    Button("💪 强力 Strong（旗舰模型）") { viewModel.preferredModelTier = "strong" }
                    Button("💰 经济 Cheap（高性价比）") { viewModel.preferredModelTier = "cheap" }
                }
                
                Button(action: viewModel.isLoading ? { viewModel.stopTask() } : onSubmit) {
                    Image(systemName: viewModel.isLoading ? "stop.circle.fill" : "arrow.up.circle.fill")
                        .font(CyberFont.body(size: 22))
                        .foregroundColor(viewModel.isLoading ? CyberColor.red : (canSendOrVoice ? CyberColor.cyan : CyberColor.textSecond.opacity(0.5)))
                        .frame(width: 36, height: 36)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(!canSendOrVoice && !viewModel.isLoading)
                .help(viewModel.isLoading ? "终止任务" : (viewModel.isVoiceInputActive ? "发送当前识别结果" : "发送消息 (⌘↵)"))
                .keyboardShortcut(.return, modifiers: .command)
            }
            .fixedSize(horizontal: true, vertical: false)
        }
        .padding()
        .background(CyberColor.bg1)
    }
    
    private var canSend: Bool {
        !viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !viewModel.isLoading &&
        viewModel.isConnected
    }
    
    private var canSendOrVoice: Bool {
        if viewModel.isVoiceInputActive {
            let t = viewModel.voiceInputService.finalText + viewModel.voiceInputService.interimText
            return !t.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        return canSend
    }
    
    private func onSubmit() {
        if viewModel.isVoiceInputActive {
            viewModel.commitVoiceInput()
        } else {
            guard canSend else { return }
            viewModel.sendMessage()
        }
    }
    
    private func toggleVoiceInput() {
        if viewModel.isVoiceInputActive {
            viewModel.stopVoiceInput()
        } else {
            viewModel.startVoiceInput()
        }
    }
    
    private func sendMessage() {
        guard canSend else { return }
        viewModel.sendMessage()
    }
    
    private func sendAutonomousTask() {
        guard canSend else { return }
        viewModel.sendAutonomousTask()
    }

    private func tierShortName(_ tier: String) -> String {
        switch tier {
        case "fast": return "⚡"
        case "strong": return "💪"
        case "cheap": return "💰"
        default: return ""
        }
    }
}
