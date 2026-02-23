import SwiftUI

struct SidebarView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("对话历史")
                    .font(.headline)
                    .foregroundColor(.secondary)
                
                Spacer()
                
                Button(action: { viewModel.newConversation() }) {
                    Image(systemName: "plus.circle.fill")
                        .font(.title2)
                }
                .buttonStyle(.plain)
                .help("新建对话")
            }
            .padding()
            
            Divider()
            
            // Conversation List
            if viewModel.conversations.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "bubble.left.and.bubble.right")
                        .font(.system(size: 40))
                        .foregroundColor(.secondary)
                    
                    Text("暂无对话")
                        .foregroundColor(.secondary)
                    
                    Button("开始新对话") {
                        viewModel.newConversation()
                    }
                    .buttonStyle(.borderedProminent)
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
            }
            
            Divider()
            
            // Connection Status
            HStack {
                Circle()
                    .fill(viewModel.isConnected ? Color.green : Color.red)
                    .frame(width: 8, height: 8)
                
                Text(viewModel.isConnected ? "已连接" : "未连接")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                Spacer()
                
                if !viewModel.isConnected {
                    Button("重连") {
                        viewModel.connect()
                    }
                    .font(.caption)
                    .buttonStyle(.link)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
    }
}

struct ConversationRow: View {
    let conversation: Conversation
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(conversation.title)
                .font(.body)
                .lineLimit(1)
            
            HStack {
                Text(conversation.updatedAt.formatted(date: .abbreviated, time: .shortened))
                    .font(.caption2)
                    .foregroundColor(.secondary)
                
                Spacer()
                
                Text("\(conversation.messages.count) 条消息")
                    .font(.caption2)
                    .foregroundColor(.secondary)
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
