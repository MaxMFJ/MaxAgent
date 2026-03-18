import SwiftUI

// MARK: - 多 Agent 协作群聊视图（只读）

struct GroupChatView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @State private var isUserScrolling = false

    var body: some View {
        VStack(spacing: 0) {
            if let group = viewModel.activeGroupChat {
                // 顶部栏
                GroupChatHeader(group: group)

                Rectangle()
                    .fill(CyberColor.border)
                    .frame(height: 1)

                // 任务面板
                GroupTaskPanel(summary: group.taskSummary, status: group.status)
                    .padding(.horizontal)
                    .padding(.vertical, 8)

                Rectangle()
                    .fill(CyberColor.border)
                    .frame(height: 1)

                // 消息列表
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 12) {
                            ForEach(group.messages) { message in
                                GroupMessageRow(message: message, participants: group.participants)
                                    .id(message.id)
                            }
                            Color.clear
                                .frame(height: 1)
                                .id("group_bottom")
                        }
                        .padding()
                    }
                    .onChange(of: group.messages.count) { _, _ in
                        if !isUserScrolling {
                            withAnimation(.easeOut(duration: 0.2)) {
                                proxy.scrollTo("group_bottom", anchor: .bottom)
                            }
                        }
                    }
                }

                Rectangle()
                    .fill(CyberColor.border)
                    .frame(height: 1)

                // 只读提示
                HStack {
                    Image(systemName: "eye")
                        .foregroundColor(CyberColor.textSecond)
                    Text("只读模式 — 群聊由 Agent 自动驱动")
                        .font(CyberFont.mono(size: 11))
                        .foregroundColor(CyberColor.textSecond)
                    Spacer()
                    Button {
                        viewModel.activeGroupChat = nil
                    } label: {
                        Text("返回对话")
                            .font(CyberFont.body(size: 11, weight: .semibold))
                            .foregroundColor(CyberColor.cyan)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal)
                .padding(.vertical, 8)
            } else {
                Text("未选中群聊")
                    .font(CyberFont.body(size: 14))
                    .foregroundColor(CyberColor.textSecond)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(CyberGridBackground())
    }
}

// MARK: - 群聊顶部栏

private struct GroupChatHeader: View {
    let group: GroupChat

    var body: some View {
        HStack(spacing: 10) {
            Text("🦆")
                .font(.system(size: 20))

            VStack(alignment: .leading, spacing: 2) {
                Text(group.title)
                    .font(CyberFont.display(size: 13, weight: .semibold))
                    .foregroundColor(CyberColor.cyan)
                    .lineLimit(1)

                HStack(spacing: 6) {
                    statusBadge(group.status)
                    Text("·")
                        .foregroundColor(CyberColor.textSecond)
                    Text("\(group.participants.count) 位成员")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                }
            }

            Spacer()

            // 参与者头像列
            HStack(spacing: -4) {
                ForEach(group.participants.prefix(6)) { p in
                    Text(p.emoji)
                        .font(.system(size: 14))
                        .frame(width: 24, height: 24)
                        .background(CyberColor.bgHighlight)
                        .clipShape(Circle())
                        .overlay(Circle().stroke(CyberColor.border, lineWidth: 1))
                }
                if group.participants.count > 6 {
                    Text("+\(group.participants.count - 6)")
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond)
                        .frame(width: 24, height: 24)
                        .background(CyberColor.bgHighlight)
                        .clipShape(Circle())
                        .overlay(Circle().stroke(CyberColor.border, lineWidth: 1))
                }
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
        .background(CyberColor.bg1)
    }

    @ViewBuilder
    private func statusBadge(_ status: GroupChatStatus) -> some View {
        let (text, color): (String, Color) = {
            switch status {
            case .active: return ("进行中", CyberColor.green)
            case .completed: return ("已完成", CyberColor.cyan)
            case .failed: return ("失败", CyberColor.red)
            case .cancelled: return ("已取消", CyberColor.orange)
            }
        }()
        Text(text)
            .font(CyberFont.mono(size: 9, weight: .semibold))
            .foregroundColor(color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .cornerRadius(4)
    }
}

// MARK: - 任务面板

private struct GroupTaskPanel: View {
    let summary: GroupTaskSummary
    let status: GroupChatStatus

    private var total: Int { summary.total ?? 0 }
    private var completed: Int { summary.completed ?? 0 }
    private var failed: Int { summary.failed ?? 0 }
    private var running: Int { summary.running ?? 0 }
    private var pending: Int { summary.pending ?? 0 }
    private var progress: Double {
        guard total > 0 else { return 0 }
        return Double(completed + failed) / Double(total)
    }

    var body: some View {
        VStack(spacing: 6) {
            // 进度条
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(CyberColor.bgHighlight)
                    RoundedRectangle(cornerRadius: 3)
                        .fill(failed > 0 ? CyberColor.orange : CyberColor.cyan)
                        .frame(width: geo.size.width * progress)
                        .animation(.easeInOut(duration: 0.3), value: progress)
                }
            }
            .frame(height: 6)

            // 计数
            HStack(spacing: 12) {
                taskStat("总计", "\(total)", CyberColor.textPrimary)
                taskStat("完成", "\(completed)", CyberColor.green)
                taskStat("运行", "\(running)", CyberColor.orange)
                taskStat("等待", "\(pending)", CyberColor.textSecond)
                if failed > 0 {
                    taskStat("失败", "\(failed)", CyberColor.red)
                }
                Spacer()
            }
        }
    }

    private func taskStat(_ label: String, _ value: String, _ color: Color) -> some View {
        HStack(spacing: 3) {
            Text(label)
                .font(CyberFont.mono(size: 9))
                .foregroundColor(CyberColor.textSecond)
            Text(value)
                .font(CyberFont.mono(size: 10, weight: .semibold))
                .foregroundColor(color)
        }
    }
}

// MARK: - 消息行

private struct GroupMessageRow: View {
    let message: GroupMessage
    let participants: [GroupParticipant]

    private var sender: GroupParticipant? {
        participants.first(where: { $0.participantId == message.senderId })
    }

    var body: some View {
        if message.senderRole == .system {
            systemRow
        } else {
            agentRow
        }
    }

    // 系统消息：居中小字
    private var systemRow: some View {
        HStack {
            Spacer()
            Text(message.content)
                .font(CyberFont.mono(size: 10))
                .foregroundColor(CyberColor.textSecond)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 12)
                .padding(.vertical, 4)
                .background(CyberColor.bgHighlight.opacity(0.5))
                .cornerRadius(8)
            Spacer()
        }
    }

    // Agent 消息气泡
    private var agentRow: some View {
        HStack(alignment: .top, spacing: 8) {
            // 头像
            Text(sender?.emoji ?? "🤖")
                .font(.system(size: 16))
                .frame(width: 28, height: 28)
                .background(bubbleColor.opacity(0.15))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 2) {
                // 名字 + 类型标签 + 时间
                HStack(spacing: 6) {
                    Text(message.senderName)
                        .font(CyberFont.body(size: 11, weight: .semibold))
                        .foregroundColor(bubbleColor)

                    if let badge = msgTypeBadge {
                        Text(badge)
                            .font(CyberFont.mono(size: 8, weight: .semibold))
                            .foregroundColor(.white)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(bubbleColor.opacity(0.6))
                            .cornerRadius(3)
                    }

                    Spacer()

                    Text(formatTimestamp(message.timestamp))
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond)
                }

                // 消息内容
                Text(message.content)
                    .font(CyberFont.body(size: 12))
                    .foregroundColor(CyberColor.textPrimary)
                    .textSelection(.enabled)

                // @提及
                if !message.mentions.isEmpty {
                    HStack(spacing: 4) {
                        ForEach(message.mentions, id: \.self) { m in
                            let mentionP = participants.first(where: { $0.participantId == m })
                            Text("@\(mentionP?.name ?? m)")
                                .font(CyberFont.mono(size: 9))
                                .foregroundColor(CyberColor.cyan)
                        }
                    }
                }
            }
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 8)
        .background(bubbleColor.opacity(0.05))
        .cornerRadius(8)
    }

    private var bubbleColor: Color {
        switch message.senderRole {
        case .main: return CyberColor.cyan
        case .duck: return CyberColor.orange
        case .monitor: return CyberColor.purple
        case .system: return CyberColor.textSecond
        }
    }

    private var msgTypeBadge: String? {
        switch message.msgType {
        case .taskAssign: return "分配"
        case .taskComplete: return "完成"
        case .taskFailed: return "失败"
        case .taskProgress: return "进度"
        case .plan: return "计划"
        case .conclusion: return "总结"
        case .monitorReport: return "报告"
        case .statusUpdate: return "状态"
        case .text: return nil
        }
    }

    private func formatTimestamp(_ ts: Double) -> String {
        let date = Date(timeIntervalSince1970: ts)
        let fmt = DateFormatter()
        fmt.dateFormat = "HH:mm:ss"
        return fmt.string(from: date)
    }
}
