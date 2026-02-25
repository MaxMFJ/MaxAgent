import SwiftUI

struct SystemMessageView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    
    private var displayedNotifications: [SystemNotification] {
        viewModel.filteredSystemNotifications
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("系统消息")
                    .font(.headline)
                
                Spacer()
                
                if !viewModel.systemNotifications.isEmpty {
                    Menu {
                        Button {
                            copyAllNotifications(displayedNotifications)
                        } label: {
                            Label("复制当前列表", systemImage: "doc.on.doc")
                        }
                        Button("全部标为已读") {
                            viewModel.markAllNotificationsRead()
                        }
                        Divider()
                        Button("清空所有消息", role: .destructive) {
                            viewModel.clearNotifications()
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                            .foregroundColor(.secondary)
                    }
                    .menuStyle(.borderlessButton)
                    .frame(width: 24)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            
            // Tab 栏：全部 | 系统错误 | 进化状态 | 任务完成 | 其他
            Picker("分类", selection: $viewModel.selectedNotificationTab) {
                ForEach(SystemMessageTab.allCases, id: \.self) { tab in
                    Text(tab.tabTitle).tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .padding(.horizontal, 12)
            .padding(.bottom, 8)
            
            Divider()
            
            if displayedNotifications.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: viewModel.selectedNotificationTab.category?.icon ?? "bell.slash")
                        .font(.system(size: 36))
                        .foregroundColor(.secondary)
                    Text(viewModel.selectedNotificationTab == .all ? "暂无系统消息" : "该分类下暂无消息")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 1) {
                        ForEach(displayedNotifications) { notification in
                            SystemMessageRow(notification: notification) {
                                viewModel.markNotificationRead(notification)
                            }
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(NSColor.windowBackgroundColor))
    }
    
    private func copyAllNotifications(_ notifications: [SystemNotification]) {
        let text = notifications.map { n in
            let levelTag = "[\(n.level.rawValue.uppercased())]"
            return "\(levelTag) \(n.title)\n\(n.content)\n(\(n.relativeTime))"
        }.joined(separator: "\n\n---\n\n")
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}

struct SystemMessageRow: View {
    let notification: SystemNotification
    let onMarkRead: () -> Void
    
    @State private var isHovering = false
    @State private var showCopied = false
    
    var levelColor: Color {
        switch notification.level {
        case .error: return .red
        case .warning: return .orange
        case .info: return .blue
        }
    }
    
    private var copyText: String {
        "[\(notification.level.rawValue.uppercased())] \(notification.title)\n\(notification.content)"
    }
    
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: notification.level.icon)
                .foregroundColor(levelColor)
                .font(.system(size: 16))
                .frame(width: 20, alignment: .center)
                .padding(.top, 2)
            
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(notification.title)
                        .font(.system(size: 13, weight: notification.read ? .regular : .semibold))
                        .lineLimit(1)
                    
                    Spacer()
                    
                    if showCopied {
                        Text("已复制")
                            .font(.caption2)
                            .foregroundColor(.green)
                            .transition(.opacity)
                    }
                    
                    if isHovering {
                        Button(action: copyToClipboard) {
                            Image(systemName: "doc.on.doc")
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                        .help("复制此消息")
                        .transition(.opacity)
                    }
                    
                    Text(notification.relativeTime)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                
                Text(notification.content)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
                
                if !notification.source.isEmpty && notification.source != "system" {
                    Text("来源: \(notification.source)")
                        .font(.caption2)
                        .foregroundColor(Color(NSColor.tertiaryLabelColor))
                }
            }
            
            if !notification.read {
                Circle()
                    .fill(Color.accentColor)
                    .frame(width: 8, height: 8)
                    .padding(.top, 4)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 0)
                .fill(notification.read
                      ? Color.clear
                      : Color.accentColor.opacity(0.04))
        )
        .background(isHovering ? Color(NSColor.controlBackgroundColor) : Color.clear)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.15)) {
                isHovering = hovering
            }
        }
        .onTapGesture {
            if !notification.read {
                onMarkRead()
            }
        }
        .contextMenu {
            Button {
                copyToClipboard()
            } label: {
                Label("复制消息", systemImage: "doc.on.doc")
            }
            if !notification.read {
                Button {
                    onMarkRead()
                } label: {
                    Label("标为已读", systemImage: "checkmark.circle")
                }
            }
        }
    }
    
    private func copyToClipboard() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(copyText, forType: .string)
        withAnimation { showCopied = true }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            withAnimation { showCopied = false }
        }
    }
}

// MARK: - Notification Bell Button (for toolbar)

struct NotificationBellButton: View {
    @EnvironmentObject var viewModel: AgentViewModel
    
    var body: some View {
        Button(action: {
            withAnimation {
                viewModel.showSystemMessages.toggle()
            }
        }) {
            ZStack(alignment: .topTrailing) {
                Image(systemName: viewModel.unreadNotificationCount > 0 ? "bell.badge.fill" : "bell")
                    .font(.system(size: 14))
                    .foregroundColor(viewModel.showSystemMessages || viewModel.unreadNotificationCount > 0 ? .accentColor : .secondary)
                
                if viewModel.unreadNotificationCount > 0 {
                    Text("\(min(viewModel.unreadNotificationCount, 99))")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Capsule().fill(Color.red))
                        .offset(x: 8, y: -6)
                }
            }
        }
        .buttonStyle(.plain)
        .help(viewModel.showSystemMessages ? "隐藏系统消息面板" : "系统消息 (\(viewModel.unreadNotificationCount) 条未读)，点击显示面板")
    }
}

#Preview {
    SystemMessageView()
        .environmentObject(AgentViewModel())
}
