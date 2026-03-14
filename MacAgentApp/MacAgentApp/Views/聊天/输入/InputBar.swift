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
        return "输入消息... 可拖拽文件附加引用 (Enter 发送, Shift+Enter 换行)"
    }
    
    var body: some View {
        HStack(alignment: .bottom, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
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
                .onDrop(of: [.fileURL], isTargeted: nil) { providers in
                    handleFileDrop(providers: providers)
                }
                
                if !viewModel.attachedFilePaths.isEmpty {
                    HStack(spacing: 6) {
                        ForEach(viewModel.attachedFilePaths, id: \.self) { path in
                            HStack(spacing: 2) {
                                Image(systemName: "doc.fill")
                                    .font(.system(size: 10))
                                    .foregroundColor(CyberColor.cyan)
                                Text((path as NSString).lastPathComponent)
                                    .font(.system(size: 11))
                                    .foregroundColor(CyberColor.textSecond)
                                    .lineLimit(1)
                                Button(action: { viewModel.attachedFilePaths.removeAll { $0 == path } }) {
                                    Image(systemName: "xmark.circle.fill")
                                        .font(.system(size: 12))
                                        .foregroundColor(CyberColor.textSecond.opacity(0.7))
                                }
                                .buttonStyle(.plain)
                            }
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(CyberColor.bg2.opacity(0.8))
                            .cornerRadius(6)
                        }
                    }
                }
            }
            
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

    private func tierShortName(_ tier: String) -> String {
        switch tier {
        case "fast": return "⚡"
        case "strong": return "💪"
        case "cheap": return "💰"
        default: return ""
        }
    }
    
    private func handleFileDrop(providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            guard provider.hasItemConformingToTypeIdentifier("public.file-url") else { continue }
            provider.loadItem(forTypeIdentifier: "public.file-url", options: nil) { item, _ in
                guard let data = item as? Data,
                      let urlString = String(data: data, encoding: .utf8),
                      let url = URL(string: urlString) else { return }
                let path = url.path
                Task { @MainActor in
                    if !viewModel.attachedFilePaths.contains(path) {
                        viewModel.attachedFilePaths.append(path)
                    }
                }
            }
        }
        return true
    }
}
