import SwiftUI

// MARK: - Tab4: 实时日志流 (Terminal Style)

struct LogStreamView: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        VStack(spacing: 0) {
            LogFilterBar()
                .environmentObject(vm)

            Rectangle()
                .fill(CyberColor.cyan.opacity(0.3))
                .frame(height: 1)

            LogContentArea()
                .environmentObject(vm)

            Rectangle()
                .fill(CyberColor.border)
                .frame(height: 1)

            LogStatusBar()
                .environmentObject(vm)
        }
    }
}

// MARK: - 过滤栏

private struct LogFilterBar: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        HStack(spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(CyberColor.cyan)
                    .font(CyberFont.body(size: 11))
                TextField("搜索日志...", text: $vm.logSearchText)
                    .textFieldStyle(.plain)
                    .font(CyberFont.mono(size: 11))
                    .foregroundColor(CyberColor.textPrimary)
                if !vm.logSearchText.isEmpty {
                    Button(action: { vm.logSearchText = "" }) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(CyberColor.textSecond)
                            .font(CyberFont.body(size: 11))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(CyberColor.bg2)
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(CyberColor.border, lineWidth: 1))
            .cornerRadius(6)
            .frame(maxWidth: 220)

            Picker("来源", selection: $vm.logSourceFilter) {
                Text("工具日志").tag("tool")
                Text("系统日志").tag("backend")
                Text("系统通知").tag("notification")
            }
            .pickerStyle(.segmented)
            .frame(maxWidth: 240)

            Menu {
                Button("全部") { vm.logLevelFilter = nil }
                Divider()
                Button("INFO") { vm.logLevelFilter = "INFO" }
                Button("WARNING") { vm.logLevelFilter = "WARNING" }
                Button("ERROR") { vm.logLevelFilter = "ERROR" }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "line.3.horizontal.decrease.circle")
                        .font(CyberFont.body(size: 11))
                    Text(vm.logLevelFilter ?? "全部级别")
                        .font(CyberFont.body(size: 11))
                }
                .foregroundColor(levelColor(vm.logLevelFilter))
            }
            .menuStyle(.borderlessButton)
            .frame(maxWidth: 100)

            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(CyberColor.bg1)
    }

    private func levelColor(_ level: String?) -> Color {
        switch level {
        case "ERROR": return CyberColor.red
        case "WARNING": return CyberColor.orange
        case "INFO": return CyberColor.cyan
        default: return CyberColor.textSecond
        }
    }
}

// MARK: - 日志内容区域

private struct LogContentArea: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        ZStack {
            CyberColor.bg0
            switch vm.logSourceFilter {
            case "tool":   ToolLogList().environmentObject(vm)
            case "backend": BackendLogList().environmentObject(vm)
            default:        NotificationLogList().environmentObject(vm)
            }
        }
    }
}

// MARK: - 工具执行日志

private struct ToolLogList: View {
    @EnvironmentObject var vm: MonitoringViewModel
    @State private var autoScroll = true

    var body: some View {
        if vm.filteredExecutionLogs.isEmpty {
            EmptyLogView(icon: "wrench.and.screwdriver", message: "暂无工具执行日志")
        } else {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(vm.filteredExecutionLogs) { log in
                            TerminalLogRow(
                                timestamp: log.timestamp.formatted(.dateTime.hour().minute().second()),
                                level: log.level,
                                source: log.toolName,
                                message: log.message
                            )
                            .id(log.id)
                        }
                    }
                    .padding(8)
                }
                .onChange(of: vm.filteredExecutionLogs.count) {
                    if autoScroll, let last = vm.filteredExecutionLogs.last {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }
            .overlay(alignment: .bottomTrailing) {
                Toggle("自动滚动", isOn: $autoScroll)
                    .toggleStyle(.checkbox)
                    .font(CyberFont.mono(size: 10))
                    .foregroundColor(CyberColor.textSecond)
                    .padding(8)
            }
        }
    }
}

// MARK: - 后端系统日志

private struct BackendLogList: View {
    @EnvironmentObject var vm: MonitoringViewModel
    @State private var autoScroll = true

    var body: some View {
        if vm.filteredBackendLogs.isEmpty {
            EmptyLogView(icon: "server.rack", message: "暂无后端日志")
        } else {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(vm.filteredBackendLogs) { log in
                            TerminalLogRow(
                                timestamp: log.timestamp,
                                level: log.level,
                                source: "backend",
                                message: log.message
                            )
                            .id(log.id)
                        }
                    }
                    .padding(8)
                }
                .onChange(of: vm.filteredBackendLogs.count) {
                    if autoScroll, let last = vm.filteredBackendLogs.last {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }
            .overlay(alignment: .bottomTrailing) {
                Toggle("自动滚动", isOn: $autoScroll)
                    .toggleStyle(.checkbox)
                    .font(CyberFont.mono(size: 10))
                    .foregroundColor(CyberColor.textSecond)
                    .padding(8)
            }
        }
    }
}

// MARK: - 系统通知列表

private struct NotificationLogList: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var body: some View {
        if vm.filteredNotifications.isEmpty {
            EmptyLogView(icon: "bell.slash", message: "暂无系统通知")
        } else {
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(vm.filteredNotifications) { n in
                        TerminalNotificationRow(notification: n)
                    }
                }
                .padding(8)
            }
        }
    }
}

// MARK: - 终端风格日志行

private struct TerminalLogRow: View {
    let timestamp: String
    let level: String
    let source: String
    let message: String

    var levelColor: Color {
        switch level.uppercased() {
        case "ERROR": return CyberColor.red
        case "WARNING": return CyberColor.orange
        case "INFO": return CyberColor.cyan
        case "DEBUG": return CyberColor.textSecond
        default: return CyberColor.textSecond
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text(timestamp)
                .font(CyberFont.mono(size: 10))
                .foregroundColor(CyberColor.green.opacity(0.8))
                .frame(width: 76, alignment: .leading)

            Text(level.uppercased())
                .font(CyberFont.mono(size: 9, weight: .bold))
                .foregroundColor(levelColor)
                .frame(width: 50, alignment: .leading)

            if !source.isEmpty {
                Text(source)
                    .font(CyberFont.mono(size: 10))
                    .foregroundColor(CyberColor.cyan)
                    .frame(width: 90, alignment: .leading)
                    .lineLimit(1)
            }

            Text(message)
                .font(CyberFont.mono(size: 11))
                .foregroundColor(CyberColor.textPrimary)
                .lineLimit(3)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 3)
        .padding(.horizontal, 4)
    }
}

private struct TerminalNotificationRow: View {
    let notification: SystemNotification

    var levelColor: Color {
        switch notification.level {
        case .error: return CyberColor.red
        case .warning: return CyberColor.orange
        case .info: return CyberColor.cyan
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: notification.level.icon)
                .font(CyberFont.body(size: 12))
                .foregroundColor(levelColor)
                .frame(width: 16)
                .padding(.top, 1)

            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text(notification.title)
                        .font(CyberFont.body(size: 11, weight: .semibold))
                        .foregroundColor(CyberColor.textPrimary)
                    Spacer()
                    Text(notification.relativeTime)
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                }
                Text(notification.content)
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(CyberColor.textSecond)
                    .lineLimit(3)
                if !notification.source.isEmpty {
                    Text("来源: \(notification.source)")
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond.opacity(0.7))
                }
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 4)
    }
}

// MARK: - 底部状态条

private struct LogStatusBar: View {
    @EnvironmentObject var vm: MonitoringViewModel

    var currentCount: Int {
        switch vm.logSourceFilter {
        case "tool": return vm.filteredExecutionLogs.count
        case "backend": return vm.filteredBackendLogs.count
        default: return vm.filteredNotifications.count
        }
    }

    var body: some View {
        HStack(spacing: 10) {
            Text("共 \(currentCount) 条")
                .font(CyberFont.mono(size: 10))
                .foregroundColor(CyberColor.textSecond)

            if let filter = vm.logLevelFilter {
                HStack(spacing: 4) {
                    Text("级别: \(filter)")
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                    Button(action: { vm.logLevelFilter = nil }) {
                        Image(systemName: "xmark")
                            .font(CyberFont.mono(size: 8))
                            .foregroundColor(CyberColor.textSecond)
                    }
                    .buttonStyle(.plain)
                }
            }

            Spacer()

            if vm.logSourceFilter == "backend" {
                Button(action: { vm.backendLogs.removeAll() }) {
                    Text("清空日志")
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(CyberColor.cyan)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(CyberColor.bg1)
    }
}

// MARK: - 空状态

private struct EmptyLogView: View {
    let icon: String
    let message: String

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: icon)
                .font(CyberFont.display(size: 36))
                .foregroundColor(CyberColor.cyan.opacity(0.3))
            Text(message)
                .font(CyberFont.body(size: 12))
                .foregroundColor(CyberColor.textSecond)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
