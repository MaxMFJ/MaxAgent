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
                HStack(spacing: 6) {
                    Image(systemName: "bell.badge")
                        .font(CyberFont.body(size: 12))
                        .foregroundColor(CyberColor.cyan)
                    Text("SYSTEM MSG")
                        .font(CyberFont.mono(size: 11, weight: .bold))
                        .foregroundColor(CyberColor.cyan)
                        .tracking(1)
                }
                
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
                            .foregroundColor(CyberColor.textSecond)
                    }
                    .menuStyle(.borderlessButton)
                    .frame(width: 24)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            
            // Tab 栏 — Cyberpunk Style
            HStack(spacing: 0) {
                ForEach(SystemMessageTab.allCases, id: \.self) { tab in
                    CyberMsgTab(
                        title: tab.tabTitle,
                        isSelected: viewModel.selectedNotificationTab == tab
                    ) {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            viewModel.selectedNotificationTab = tab
                        }
                    }
                }
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 8)
            
            Rectangle()
                .fill(CyberColor.border)
                .frame(height: 1)
            
            if displayedNotifications.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: viewModel.selectedNotificationTab.category?.icon ?? "bell.slash")
                        .font(CyberFont.display(size: 36))
                        .foregroundColor(CyberColor.cyanDim)
                    Text(viewModel.selectedNotificationTab == .all ? "暂无系统消息" : "该分类下暂无消息")
                        .font(CyberFont.mono(size: 11))
                        .foregroundColor(CyberColor.textSecond)
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
        .background(CyberColor.bg1)
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

// MARK: - Cyber Message Tab

private struct CyberMsgTab: View {
    let title: String
    let isSelected: Bool
    let onTap: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            Text(title)
                .font(CyberFont.mono(size: 9, weight: isSelected ? .bold : .medium))
                .foregroundColor(isSelected ? CyberColor.cyan : CyberColor.textSecond)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(isSelected ? CyberColor.cyan.opacity(0.1) : Color.clear)
                .overlay(
                    RoundedRectangle(cornerRadius: 3)
                        .stroke(isSelected ? CyberColor.cyan.opacity(0.3) : Color.clear, lineWidth: 0.5)
                )
                .cornerRadius(3)
        }
        .buttonStyle(.plain)
    }
}

struct SystemMessageRow: View {
    let notification: SystemNotification
    let onMarkRead: () -> Void
    
    @State private var isHovering = false
    @State private var showCopied = false
    
    var levelColor: Color {
        switch notification.level {
        case .error: return CyberColor.red
        case .warning: return CyberColor.orange
        case .info: return CyberColor.cyan
        }
    }
    
    private var copyText: String {
        "[\(notification.level.rawValue.uppercased())] \(notification.title)\n\(notification.content)"
    }
    
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: notification.level.icon)
                .foregroundColor(levelColor)
                .font(CyberFont.body(size: 14))
                .frame(width: 20, alignment: .center)
                .padding(.top, 2)
                .shadow(color: levelColor.opacity(0.3), radius: 2)
            
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(notification.title)
                        .font(CyberFont.mono(size: 12, weight: notification.read ? .regular : .semibold))
                        .foregroundColor(CyberColor.textPrimary)
                        .lineLimit(1)
                    
                    Spacer()
                    
                    if showCopied {
                        Text("已复制")
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(CyberColor.green)
                            .transition(.opacity)
                    }
                    
                    if isHovering {
                        Button(action: copyToClipboard) {
                            Image(systemName: "doc.on.doc")
                                .font(CyberFont.body(size: 11))
                                .foregroundColor(CyberColor.textSecond)
                        }
                        .buttonStyle(.plain)
                        .help("复制此消息")
                        .transition(.opacity)
                    }
                    
                    Text(notification.relativeTime)
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond)
                }
                
                Text(notification.content)
                    .font(CyberFont.mono(size: 11))
                    .foregroundColor(CyberColor.textSecond)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
                
                if !notification.source.isEmpty && notification.source != "system" {
                    Text("来源: \(notification.source)")
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond.opacity(0.6))
                }
            }
            
            if !notification.read {
                Circle()
                    .fill(CyberColor.cyan)
                    .frame(width: 6, height: 6)
                    .padding(.top, 4)
                    .shadow(color: CyberColor.cyan.opacity(0.5), radius: 2)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 0)
                .fill(notification.read
                      ? Color.clear
                      : CyberColor.cyan.opacity(0.03))
        )
        .background(isHovering ? CyberColor.bg2 : Color.clear)
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
                    .font(.system(size: 17, weight: .medium))
                    .foregroundColor(viewModel.showSystemMessages || viewModel.unreadNotificationCount > 0 ? CyberColor.cyan : CyberColor.textSecond)
                
                if viewModel.unreadNotificationCount > 0 {
                    Text("\(min(viewModel.unreadNotificationCount, 99))")
                        .font(CyberFont.mono(size: 9, weight: .bold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Capsule().fill(CyberColor.red))
                        .offset(x: 8, y: -6)
                }
            }
            .frame(width: 36, height: 36)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(viewModel.showSystemMessages ? "隐藏系统消息面板" : "系统消息 (\(viewModel.unreadNotificationCount) 条未读)，点击显示面板")
    }
}

#Preview {
    SystemMessageView()
        .environmentObject(AgentViewModel())
}
