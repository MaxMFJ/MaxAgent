import SwiftUI

struct SidebarView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("对话历史")
                    .font(CyberFont.display(size: 13, weight: .semibold))
                    .foregroundColor(CyberColor.cyan)
                    .tracking(1)
                
                Spacer()
                
                Button(action: { viewModel.newConversation() }) {
                    Image(systemName: "plus.circle.fill")
                        .font(CyberFont.body(size: 15, weight: .semibold))
                        .foregroundColor(CyberColor.cyan)
                }
                .buttonStyle(.plain)
                .help("新建对话")
            }
            .padding()
            
            Rectangle()
                .fill(CyberColor.border)
                .frame(height: 1)
            
            // Conversation List
            if viewModel.conversations.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "bubble.left.and.bubble.right")
                        .font(CyberFont.display(size: 40))
                        .foregroundColor(CyberColor.textSecond)
                    
                    Text("暂无对话")
                        .font(CyberFont.body(size: 14))
                        .foregroundColor(CyberColor.textSecond)
                    
                    Button("开始新对话") {
                        viewModel.newConversation()
                    }
                    .font(CyberFont.body(size: 13, weight: .semibold))
                    .buttonStyle(.borderedProminent)
                    .tint(CyberColor.cyan)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(selection: Binding(
                    get: { viewModel.currentConversation?.id },
                    set: { id in
                        if let id = id,
                           let conversation = viewModel.conversations.first(where: { $0.id == id }) {
                            viewModel.selectConversation(conversation)
                        }
                    }
                )) {
                    ForEach(viewModel.conversations) { conversation in
                        ConversationRow(conversation: conversation)
                            .tag(conversation.id)
                            .contextMenu {
                                Button(role: .destructive) {
                                    viewModel.deleteConversation(conversation)
                                } label: {
                                    Label("删除", systemImage: "trash")
                                }
                            }
                    }
                }
                .listStyle(.sidebar)
                .scrollContentBackground(.hidden)
            }
            
            Rectangle()
                .fill(CyberColor.border)
                .frame(height: 1)

            // Group Chats Section
            if !viewModel.groupChats.isEmpty {
                VStack(spacing: 0) {
                    HStack {
                        Text("协作群聊")
                            .font(CyberFont.display(size: 11, weight: .semibold))
                            .foregroundColor(CyberColor.purple)
                            .tracking(1)
                        Spacer()
                    }
                    .padding(.horizontal)
                    .padding(.vertical, 6)

                    ForEach(viewModel.groupChats) { group in
                        GroupChatRow(group: group, isActive: viewModel.activeGroupChat?.groupId == group.groupId)
                            .contentShape(Rectangle())
                            .onTapGesture {
                                viewModel.activeGroupChat = group
                                viewModel.currentConversation = nil
                            }
                            .contextMenu {
                                Button(role: .destructive) {
                                    viewModel.deleteGroupChat(group)
                                } label: {
                                    Label("删除群聊", systemImage: "trash")
                                }
                            }
                    }
                }

                Rectangle()
                    .fill(CyberColor.border)
                    .frame(height: 1)
            }

            // Connection Status
            HStack {
                Circle()
                    .fill(viewModel.isConnected ? CyberColor.green : CyberColor.red)
                    .frame(width: 8, height: 8)
                    .shadow(color: (viewModel.isConnected ? CyberColor.green : CyberColor.red).opacity(0.5), radius: 4)
                
                Text(viewModel.isConnected ? "已连接" : "未连接")
                    .font(CyberFont.mono(size: 11))
                    .foregroundColor(CyberColor.textSecond)
                
                Spacer()
                
                if !viewModel.isConnected {
                    Button("重连") {
                        viewModel.connect()
                    }
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(CyberColor.cyan)
                    .buttonStyle(.link)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
        .background(CyberColor.bg1)
    }
}

struct ConversationRow: View {
    let conversation: Conversation
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(conversation.title)
                .font(CyberFont.body(size: 13))
                .foregroundColor(CyberColor.textPrimary)
                .lineLimit(1)
            
            HStack {
                Text(conversation.updatedAt.formatted(date: .abbreviated, time: .shortened))
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(CyberColor.textSecond)
                
                Spacer()
                
                Text("\(conversation.messages.count) 条消息")
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(CyberColor.textSecond)
            }
        }
        .padding(.vertical, 4)
    }
}

struct GroupChatRow: View {
    let group: GroupChat
    let isActive: Bool

    private var statusEmoji: String {
        switch group.status {
        case .active: return "🟢"
        case .completed: return "✅"
        case .failed: return "❌"
        case .cancelled: return "⏹️"
        }
    }

    var body: some View {
        HStack(spacing: 8) {
            Text(statusEmoji)
                .font(.system(size: 10))

            VStack(alignment: .leading, spacing: 2) {
                Text(group.title)
                    .font(CyberFont.body(size: 12))
                    .foregroundColor(CyberColor.textPrimary)
                    .lineLimit(1)

                HStack(spacing: 6) {
                    Text("\(group.participants.count) 成员")
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond)
                    Text("·")
                        .foregroundColor(CyberColor.textSecond)
                    Text("\(group.messages.count) 消息")
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond)
                }
            }

            Spacer()
        }
        .padding(.horizontal)
        .padding(.vertical, 6)
        .background(isActive ? CyberColor.bgHighlight : Color.clear)
    }
}

#Preview {
    SidebarView()
        .environmentObject(AgentViewModel())
        .frame(width: 250)
}
