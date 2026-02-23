import SwiftUI
import AppKit

struct MessageBubble: View {
    @EnvironmentObject var viewModel: AgentViewModel
    let message: Message
    @State private var isHovering = false
    
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            if message.role == .assistant {
                AssistantAvatar()
            } else {
                Spacer(minLength: 60)
            }
            
            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 4) {
                if message.role == .user {
                    HStack(spacing: 8) {
                        if isHovering {
                            UserMessageActions(message: message)
                        }
                        UserMessageContent(content: message.content)
                            .lineLimit(nil)
                    }
                    .onHover { hovering in
                        isHovering = hovering
                    }
                } else {
                    AssistantMessageContent(message: message)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                
                Text(message.timestamp.formatted(date: .omitted, time: .shortened))
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
            .contextMenu {
                if message.role == .user {
                    Button {
                        viewModel.editMessage(message)
                    } label: {
                        Label("重新编辑", systemImage: "pencil")
                    }
                    
                    Button {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(message.content, forType: .string)
                    } label: {
                        Label("复制", systemImage: "doc.on.doc")
                    }
                    
                    Divider()
                    
                    Button(role: .destructive) {
                        viewModel.deleteMessage(message)
                    } label: {
                        Label("删除", systemImage: "trash")
                    }
                } else {
                    Button {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(message.content, forType: .string)
                    } label: {
                        Label("复制", systemImage: "doc.on.doc")
                    }
                }
            }
            
            if message.role == .user {
                UserAvatar()
            } else {
                Spacer(minLength: 60)
            }
        }
    }
}

struct UserMessageActions: View {
    @EnvironmentObject var viewModel: AgentViewModel
    let message: Message
    
    var body: some View {
        HStack(spacing: 4) {
            Button {
                viewModel.editMessage(message)
            } label: {
                Image(systemName: "pencil.circle.fill")
                    .font(.title3)
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help("重新编辑")
        }
    }
}
