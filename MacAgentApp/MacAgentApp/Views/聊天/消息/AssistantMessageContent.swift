import SwiftUI
import AppKit

struct AssistantMessageContent: View {
    let message: Message
    @State private var isHovering = false
    @State private var showCopied = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            switch message.displayKind {
            case .standard:
                standardContent
            case .toolCall:
                toolCallContent
            }
        }
        .padding(12)
        .background(CyberColor.bg2)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(CyberColor.cyan.opacity(0.15), lineWidth: 0.5)
        )
        .cornerRadius(16)
        .cornerRadius(4, corners: .topLeft)
        .shadow(color: CyberColor.cyan.opacity(0.08), radius: 6)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.15)) {
                isHovering = hovering
            }
        }
    }
    
    /// 标准：Markdown 正文 + 附件 + 元信息
    private var standardContent: some View {
        Group {
            if message.content.isEmpty && message.isStreaming {
                TypingIndicator()
            } else {
                MarkdownText(content: message.content, isStreaming: message.isStreaming)
            }
            
            if let attachments = message.attachments, !attachments.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(attachments.enumerated()), id: \.offset) { _, attachment in
                        AttachmentView(attachment: attachment)
                    }
                }
                .padding(.top, 4)
            }
            
            if message.isStreaming {
                HStack(spacing: 4) {
                    ProgressView()
                        .scaleEffect(0.6)
                        .tint(CyberColor.cyan)
                    Text("正在思考...")
                        .font(.caption)
                        .foregroundColor(CyberColor.textSecond)
                }
            }
            
            footerRow
        }
    }
    
    /// 工具调用型：可扩展为展示 toolCalls 列表、结果等
    private var toolCallContent: some View {
        Group {
            if message.content.isEmpty && message.isStreaming {
                TypingIndicator()
            } else {
                MarkdownText(content: message.content, isStreaming: message.isStreaming)
            }
            if let attachments = message.attachments, !attachments.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(attachments.enumerated()), id: \.offset) { _, attachment in
                        AttachmentView(attachment: attachment)
                    }
                }
                .padding(.top, 4)
            }
            if message.isStreaming {
                HStack(spacing: 4) {
                    ProgressView()
                        .scaleEffect(0.6)
                        .tint(CyberColor.cyan)
                    Text("正在思考...")
                        .font(.caption)
                        .foregroundColor(CyberColor.textSecond)
                }
            }
            footerRow
        }
    }
    
    private var footerRow: some View {
        HStack(spacing: 8) {
            if !message.isStreaming, let modelName = message.modelName, !modelName.isEmpty {
                HStack(spacing: 4) {
                    Image(systemName: "cpu")
                        .font(.caption2)
                    Text(modelName)
                        .font(.caption2)
                    if let usage = message.tokenUsage {
                        Text("·")
                            .font(.caption2)
                        Image(systemName: "number")
                            .font(.caption2)
                        Text(usage.formatted)
                            .font(.caption2)
                    }
                }
                .foregroundColor(CyberColor.textSecond)
            }
            Spacer()
            if isHovering && !message.isStreaming && !message.content.isEmpty {
                Button {
                    copyContent()
                } label: {
                    HStack(spacing: 2) {
                        Image(systemName: showCopied ? "checkmark" : "doc.on.doc")
                            .font(.caption2)
                        Text(showCopied ? "已复制" : "复制全部")
                            .font(.caption2)
                    }
                    .foregroundColor(showCopied ? CyberColor.green : CyberColor.textSecond)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(CyberColor.bg1)
                    .cornerRadius(4)
                }
                .buttonStyle(.plain)
                .transition(.opacity.combined(with: .scale(scale: 0.9)))
            }
        }
        .padding(.top, 4)
    }
    
    private func copyContent() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(message.content, forType: .string)
        
        withAnimation {
            showCopied = true
        }
        
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            withAnimation {
                showCopied = false
            }
        }
    }
}
