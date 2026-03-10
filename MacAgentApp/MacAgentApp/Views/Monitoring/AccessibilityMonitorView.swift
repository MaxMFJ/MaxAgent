import SwiftUI

// MARK: - Tab7: Accessibility Monitor HUD

struct AccessibilityMonitorView: View {
    @EnvironmentObject var vm: MonitoringViewModel

    let columns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                // IPC + Observer 健康总览
                AXServiceHealthCard()

                LazyVGrid(columns: columns, spacing: 14) {
                    // 观察中的应用列表
                    AXObservedAppsCard()
                    // IPC 连接状态
                    AXIPCStatusCard()
                }

                // 实时事件流
                AXEventStreamCard()

                // GUI 世界状态快照
                AXWorldStateCard()
            }
            .padding(16)
        }
    }
}

// MARK: - Service Health 总览

private struct AXServiceHealthCard: View {
    @ObservedObject private var ipc = IPCService.shared
    @ObservedObject private var observer = AXObserverManager.shared

    var body: some View {
        CyberCard(glowColor: ipc.isRunning ? CyberColor.green : CyberColor.orange, padding: 12) {
            HStack(spacing: 16) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 6) {
                        Image(systemName: "accessibility.fill")
                            .font(CyberFont.display(size: 20))
                            .foregroundColor(ipc.isRunning ? CyberColor.green : CyberColor.orange)
                            .shadow(color: (ipc.isRunning ? CyberColor.green : CyberColor.orange).opacity(0.6), radius: 4)
                        Text("ACCESSIBILITY ENGINE")
                            .font(CyberFont.display(size: 12, weight: .bold))
                            .foregroundColor(CyberColor.textPrimary)
                    }
                    Text(ipc.isRunning ? "全部服务运行正常" : "IPC 服务未启动")
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                }

                Spacer()

                // 指标概览
                HStack(spacing: 20) {
                    MetricPill(label: "OBSERVER", value: "\(observer.observedCount)", color: CyberColor.cyan)
                    MetricPill(label: "CLIENTS", value: "\(ipc.connectionCount)", color: CyberColor.purple)
                    MetricPill(label: "REQUESTS", value: "\(ipc.requestCount)", color: CyberColor.green)
                }
            }
        }
    }
}

// MARK: - Observed Apps 卡片

private struct AXObservedAppsCard: View {
    @ObservedObject private var observer = AXObserverManager.shared

    var body: some View {
        CyberCard(glowColor: CyberColor.cyan, padding: 12) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "app.connected.to.app.below.fill")
                        .font(CyberFont.display(size: 14))
                        .foregroundColor(CyberColor.cyan)
                    Text("OBSERVED APPS")
                        .font(CyberFont.display(size: 11, weight: .bold))
                        .foregroundColor(CyberColor.textPrimary)
                    Spacer()
                    Text("\(observer.observedCount)")
                        .font(CyberFont.display(size: 18, weight: .bold))
                        .foregroundColor(CyberColor.cyan)
                }

                Divider().opacity(0.3)

                if observer.observedAppNames.isEmpty {
                    Text("未检测到应用")
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.vertical, 8)
                } else {
                    ForEach(observer.observedAppNames.sorted(), id: \.self) { name in
                        HStack(spacing: 6) {
                            Circle()
                                .fill(CyberColor.green)
                                .frame(width: 6, height: 6)
                            Text(name)
                                .font(CyberFont.mono(size: 10))
                                .foregroundColor(CyberColor.textPrimary)
                                .lineLimit(1)
                            Spacer()
                        }
                    }
                }
            }
        }
        .frame(minHeight: 120)
    }
}

// MARK: - IPC Status 卡片

private struct AXIPCStatusCard: View {
    @ObservedObject private var ipc = IPCService.shared

    var body: some View {
        CyberCard(glowColor: CyberColor.purple, padding: 12) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "network")
                        .font(CyberFont.display(size: 14))
                        .foregroundColor(CyberColor.purple)
                    Text("IPC SERVICE")
                        .font(CyberFont.display(size: 11, weight: .bold))
                        .foregroundColor(CyberColor.textPrimary)
                    Spacer()
                    StatusDot(isActive: ipc.isRunning)
                }

                Divider().opacity(0.3)

                VStack(spacing: 6) {
                    InfoRow(label: "协议", value: "TCP :\(PortConfiguration.shared.ipcPort)  v\(IPC_PROTOCOL_VERSION)")
                    InfoRow(label: "连接数", value: "\(ipc.connectionCount)")
                    InfoRow(label: "请求数", value: "\(ipc.requestCount)")
                    InfoRow(label: "认证", value: "Token (600)")
                }
            }
        }
        .frame(minHeight: 120)
    }
}

// MARK: - Event Stream 实时事件流

private struct AXEventStreamCard: View {
    @State private var events: [AXEvent] = []
    @State private var timer: Timer? = nil

    var body: some View {
        CyberCard(glowColor: CyberColor.cyan, padding: 12) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "bolt.horizontal.fill")
                        .font(CyberFont.display(size: 14))
                        .foregroundColor(CyberColor.cyan)
                    Text("EVENT STREAM")
                        .font(CyberFont.display(size: 11, weight: .bold))
                        .foregroundColor(CyberColor.textPrimary)
                    Spacer()
                    Text("\(events.count) events")
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond)
                }

                Divider().opacity(0.3)

                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 4) {
                        ForEach(events.indices.reversed(), id: \.self) { idx in
                            EventRow(event: events[idx])
                        }
                    }
                }
                .frame(maxHeight: 200)
            }
        }
        .onAppear {
            events = GUIStateStore.shared.getRecentEvents(count: 50)
            timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
                DispatchQueue.main.async {
                    events = GUIStateStore.shared.getRecentEvents(count: 50)
                }
            }
        }
        .onDisappear {
            timer?.invalidate()
            timer = nil
        }
    }
}

private struct EventRow: View {
    let event: AXEvent

    var eventColor: Color {
        if event.eventType.contains("Activated") || event.eventType.contains("Focus") {
            return CyberColor.cyan
        }
        if event.eventType.contains("Created") || event.eventType.contains("Deminiaturized") {
            return CyberColor.green
        }
        if event.eventType.contains("Destroyed") || event.eventType.contains("Miniaturized") {
            return CyberColor.orange
        }
        return CyberColor.textSecond
    }

    var shortType: String {
        event.eventType
            .replacingOccurrences(of: "AX", with: "")
            .replacingOccurrences(of: "Notification", with: "")
    }

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(eventColor)
                .frame(width: 5, height: 5)
            Text(shortType)
                .font(CyberFont.mono(size: 9))
                .foregroundColor(eventColor)
                .frame(width: 100, alignment: .leading)
            Text(event.appName)
                .font(CyberFont.mono(size: 9))
                .foregroundColor(CyberColor.textPrimary)
                .frame(width: 80, alignment: .leading)
                .lineLimit(1)
            if !event.elementRole.isEmpty {
                Text(event.elementRole)
                    .font(CyberFont.mono(size: 9))
                    .foregroundColor(CyberColor.purple)
                    .frame(width: 70, alignment: .leading)
            }
            if !event.elementTitle.isEmpty {
                Text(event.elementTitle)
                    .font(CyberFont.mono(size: 9))
                    .foregroundColor(CyberColor.textSecond)
                    .lineLimit(1)
            }
            Spacer()
        }
    }
}

// MARK: - GUI World State 快照卡片

private struct AXWorldStateCard: View {
    @State private var snapshot: GUIState?
    @State private var timer: Timer? = nil

    var body: some View {
        CyberCard(glowColor: CyberColor.green, padding: 12) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "globe.desk")
                        .font(CyberFont.display(size: 14))
                        .foregroundColor(CyberColor.green)
                    Text("WORLD STATE")
                        .font(CyberFont.display(size: 11, weight: .bold))
                        .foregroundColor(CyberColor.textPrimary)
                    Spacer()
                    if let s = snapshot {
                        Text("v\(s.version)")
                            .font(CyberFont.mono(size: 10))
                            .foregroundColor(CyberColor.green)
                    }
                }

                Divider().opacity(0.3)

                if let s = snapshot {
                    VStack(spacing: 6) {
                        InfoRow(label: "焦点应用", value: s.focusedAppName.isEmpty ? "—" : s.focusedAppName)
                        InfoRow(label: "焦点元素", value: s.focusedElementRole.isEmpty ? "—" : "\(s.focusedElementRole): \(s.focusedElementTitle)")
                        InfoRow(label: "窗口数量", value: "\(s.windows.count)")
                        InfoRow(label: "状态版本", value: "\(s.version)")
                    }

                    if !s.windows.isEmpty {
                        Divider().opacity(0.2)
                        Text("WINDOWS")
                            .font(CyberFont.display(size: 9, weight: .bold))
                            .foregroundColor(CyberColor.textSecond)
                        ForEach(s.windows.prefix(5), id: \.windowId) { w in
                            HStack(spacing: 6) {
                                Image(systemName: w.minimized ? "minus.square" : "macwindow")
                                    .font(.system(size: 9))
                                    .foregroundColor(w.focused ? CyberColor.cyan : CyberColor.textSecond)
                                Text(w.title.isEmpty ? "(untitled)" : w.title)
                                    .font(CyberFont.mono(size: 9))
                                    .foregroundColor(CyberColor.textPrimary)
                                    .lineLimit(1)
                                Spacer()
                                Text(w.appName)
                                    .font(CyberFont.mono(size: 8))
                                    .foregroundColor(CyberColor.textSecond)
                            }
                        }
                    }
                } else {
                    Text("正在获取状态...")
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.vertical, 8)
                }
            }
        }
        .onAppear {
            snapshot = GUIStateStore.shared.getSnapshot()
            timer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { _ in
                DispatchQueue.main.async {
                    snapshot = GUIStateStore.shared.getSnapshot()
                }
            }
        }
        .onDisappear {
            timer?.invalidate()
            timer = nil
        }
    }
}

// MARK: - Helpers

private struct MetricPill: View {
    let label: String
    let value: String
    let color: Color

    var body: some View {
        VStack(spacing: 2) {
            Text(value)
                .font(CyberFont.display(size: 16, weight: .bold))
                .foregroundColor(color)
            Text(label)
                .font(CyberFont.display(size: 8, weight: .semibold))
                .foregroundColor(CyberColor.textSecond)
        }
    }
}

private struct StatusDot: View {
    let isActive: Bool

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(isActive ? CyberColor.green : CyberColor.orange)
                .frame(width: 8, height: 8)
                .shadow(color: (isActive ? CyberColor.green : CyberColor.orange).opacity(0.6), radius: 3)
            Text(isActive ? "ONLINE" : "OFFLINE")
                .font(CyberFont.mono(size: 9))
                .foregroundColor(isActive ? CyberColor.green : CyberColor.orange)
        }
    }
}

private struct InfoRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .font(CyberFont.body(size: 10))
                .foregroundColor(CyberColor.textSecond)
            Spacer()
            Text(value)
                .font(CyberFont.mono(size: 10))
                .foregroundColor(CyberColor.textPrimary)
                .lineLimit(1)
        }
    }
}
