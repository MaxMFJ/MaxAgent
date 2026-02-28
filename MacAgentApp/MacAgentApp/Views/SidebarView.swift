import SwiftUI

struct SidebarView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("对话历史")
                    .font(.system(size: 13, weight: .semibold, design: .monospaced))
                    .foregroundColor(CyberColor.cyan)
                    .tracking(1)
                
                Spacer()
                
                Button(action: { viewModel.newConversation() }) {
                    Image(systemName: "plus.circle.fill")
                        .font(.title2)
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
                        .font(.system(size: 40))
                        .foregroundColor(CyberColor.textSecond)
                    
                    Text("暂无对话")
                        .foregroundColor(CyberColor.textSecond)
                    
                    Button("开始新对话") {
                        viewModel.newConversation()
                    }
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
            
            // Connection Status
            HStack {
                Circle()
                    .fill(viewModel.isConnected ? CyberColor.green : CyberColor.red)
                    .frame(width: 8, height: 8)
                    .shadow(color: (viewModel.isConnected ? CyberColor.green : CyberColor.red).opacity(0.5), radius: 4)
                
                Text(viewModel.isConnected ? "已连接" : "未连接")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(CyberColor.textSecond)
                
                Spacer()
                
                if !viewModel.isConnected {
                    Button("重连") {
                        viewModel.connect()
                    }
                    .font(.caption)
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
                .font(.body)
                .foregroundColor(CyberColor.textPrimary)
                .lineLimit(1)
            
            HStack {
                Text(conversation.updatedAt.formatted(date: .abbreviated, time: .shortened))
                    .font(.caption2)
                    .foregroundColor(CyberColor.textSecond)
                
                Spacer()
                
                Text("\(conversation.messages.count) 条消息")
                    .font(.caption2)
                    .foregroundColor(CyberColor.textSecond)
            }
        }
        .padding(.vertical, 4)
    }
}

#Preview {
    SidebarView()
        .environmentObject(AgentViewModel())
        .frame(width: 250)
}
