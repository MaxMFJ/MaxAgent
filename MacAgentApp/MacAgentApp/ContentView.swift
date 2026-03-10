import SwiftUI
#if os(macOS)
import AppKit
#endif

struct ContentView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @StateObject private var processManager = ProcessManager.shared
    @StateObject private var portConfig = PortConfiguration.shared
    @State private var showRestartAlert = false
    
    var body: some View {
        VStack(spacing: 0) {
            // 自定义顶部栏（无系统边框，完全自控样式）
            CustomToolbarView(processManager: processManager)
                .environmentObject(viewModel)
            
            HSplitView {
                // 左侧边栏
                SidebarView()
                    .frame(minWidth: 200, idealWidth: 250, maxWidth: 300)
                
                // 中间聊天区域
                ChatView()
                    .frame(minWidth: 400)
                
                // 右侧工具面板（可隐藏）
                if viewModel.showToolPanel {
                    ToolPanelView()
                        .frame(minWidth: 250, idealWidth: 300, maxWidth: 400)
                }
                
                // 系统消息面板（可隐藏）
                if viewModel.showSystemMessages {
                    SystemMessageView()
                        .environmentObject(viewModel)
                        .frame(minWidth: 280, idealWidth: 360, maxWidth: 420)
                }
            }
        }
        .frame(minWidth: 800, minHeight: 500)
        .toolbar(.hidden, for: .windowToolbar)
        .navigationTitle("")
        .background(WindowButtonHider())
        .sheet(isPresented: $viewModel.showSettings) {
            SettingsView()
        }
        .alert("重启应用", isPresented: $showRestartAlert) {
            Button("确定") {
                restartApp()
            }
        } message: {
            Text("后端设置已更改，即将重启应用以生效。")
        }
        // Homebrew 未安装弹窗（仅在未与服务器建立连接时显示）
        .alert("需要安装 Homebrew", isPresented: $processManager.showHomebrewAlert) {
            Button("前往安装") {
                NSWorkspace.shared.open(URL(string: "https://brew.sh")!)
            }
            Button("已安装，继续") {
                processManager.showHomebrewAlert = false
            }
            Button("忽略") {
                processManager.showHomebrewAlert = false
            }
            .keyboardShortcut(.cancelAction)
        } message: {
            Text("检测到 Homebrew 未安装。\n\nHomebrew 是 macOS 包管理器，MaxAgent 需要它来自动安装以下依赖：\n• Node.js / npx（MCP 服务器）\n• cliclick（GUI 鼠标控制）\n\n安装方法：\n1. 点击\"前往安装\"打开官网，复制安装命令\n2. 在终端执行后，重启应用即可自动完成全部配置")
        }
        // 建立连接后自动关闭 Homebrew 弹窗，并刷新 Duck 状态
        .onChange(of: viewModel.isConnected) { _, connected in
            if connected {
                processManager.showHomebrewAlert = false
                Task { await viewModel.refreshDuckStatus() }
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .backendSettingDidChange)) { _ in
            showRestartAlert = true
        }
        // 端口冲突弹窗
        .alert("端口冲突", isPresented: $portConfig.showConflictAlert) {
            Button("打开端口设置") {
                viewModel.showSettings = true
            }
            Button("忽略", role: .cancel) {}
        } message: {
            let msgs = portConfig.conflicts.map { "• 端口 \($0.port) (\($0.serviceName)) 被 \($0.conflictProcess) 占用" }
            Text("以下端口存在冲突，部分功能可能无法正常工作：\n\(msgs.joined(separator: "\n"))\n\n请前往「设置 → 端口」修改端口号。")
        }
        .onAppear {
            viewModel.connect()
            processManager.checkServicesStatus()
            
            // 设置后端启动后的回调
            processManager.onBackendStarted = { [weak viewModel] in
                // 延迟一秒后重新连接，确保后端完全启动
                Task {
                    try? await Task.sleep(nanoseconds: 1_500_000_000)
                    await MainActor.run {
                        viewModel?.connect()
                    }
                }
            }
        }
    }
    
    /// 重新启动当前 App（用于后端设置更改后恢复，避免用户误以为程序关闭）
    private func restartApp() {
#if os(macOS)
        let path = Bundle.main.bundlePath
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        proc.arguments = ["-n", path]
        try? proc.run()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            NSApplication.shared.terminate(nil)
        }
#endif
    }
}

/// 自定义窗口控制按钮（关闭、最小化、放大）
private struct WindowTrafficLightButtons: View {
    var body: some View {
#if os(macOS)
        HStack(spacing: 8) {
            TrafficLightButton(color: .red) {
                NSApplication.shared.keyWindow?.close()
            }
            .help("关闭")
            TrafficLightButton(color: .yellow) {
                NSApplication.shared.keyWindow?.miniaturize(nil)
            }
            .help("最小化")
            TrafficLightButton(color: .green) {
                NSApplication.shared.keyWindow?.zoom(nil)
            }
            .help("放大")
        }
        .padding(.trailing, 12)
#endif
    }
}

#if os(macOS)
/// 隐藏系统默认交通灯，使用自定义按钮
private struct WindowButtonHider: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let v = NSView()
        DispatchQueue.main.async {
            v.window?.standardWindowButton(.closeButton)?.isHidden = true
            v.window?.standardWindowButton(.miniaturizeButton)?.isHidden = true
            v.window?.standardWindowButton(.zoomButton)?.isHidden = true
        }
        return v
    }
    func updateNSView(_ nsView: NSView, context: Context) {
        nsView.window?.standardWindowButton(.closeButton)?.isHidden = true
        nsView.window?.standardWindowButton(.miniaturizeButton)?.isHidden = true
        nsView.window?.standardWindowButton(.zoomButton)?.isHidden = true
    }
}

private struct TrafficLightButton: View {
    let color: Color
    let action: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            Circle()
                .fill(color.opacity(isHovered ? 1 : 0.85))
                .frame(width: 12, height: 12)
                .overlay(
                    Circle()
                        .stroke(Color.white.opacity(0.3), lineWidth: 0.5)
                )
        }
        .buttonStyle(.plain)
        .onHover { isHovered = $0 }
    }
}
#endif

/// 自定义顶部栏：无系统边框，完全自控样式
private struct CustomToolbarView: View {
    @ObservedObject var processManager: ProcessManager
    @EnvironmentObject var viewModel: AgentViewModel
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        HStack {
            // 左侧：窗口控制 + 服务状态 + 铃铛 + Duck 状态
            HStack(spacing: 10) {
                WindowTrafficLightButtons()
                ServiceStatusIndicator(
                    label: "后端",
                    isRunning: processManager.isBackendRunning,
                    onTap: {
                        if processManager.isBackendRunning {
                            processManager.stopBackend()
                        } else {
                            processManager.startBackend()
                        }
                    }
                )
                ServiceStatusIndicator(
                    label: "Ollama",
                    isRunning: processManager.isOllamaRunning,
                    onTap: {
                        if processManager.isOllamaRunning {
                            processManager.stopOllama()
                        } else {
                            processManager.startOllama()
                        }
                    }
                )
                NotificationBellButton()
                    .environmentObject(viewModel)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            // 中间：标题
            ChowDuckTitleView()
                .frame(maxWidth: .infinity, alignment: .center)

            // 右侧：Duck 状态 + 监控、工具面板、设置
            HStack(spacing: 8) {
                // Duck 分身状态指示器（监控中心左侧）
                DuckStatusRow()
                    .environmentObject(viewModel)

                ToolbarIconButton(systemName: "chart.bar.xaxis", color: CyberColor.cyan.opacity(0.7)) {
                    openWindow(id: "monitoring")
                }
                .help("打开监控仪表板")

                ToolbarIconButton(
                    systemName: "sidebar.right",
                    color: viewModel.showToolPanel ? CyberColor.cyan : CyberColor.cyan.opacity(0.5)
                ) {
                    withAnimation { viewModel.showToolPanel.toggle() }
                }
                .help(viewModel.showToolPanel ? "隐藏工具面板" : "显示工具面板")

                ToolbarIconButton(systemName: "gear", color: CyberColor.cyan.opacity(0.7)) {
                    viewModel.showSettings = true
                }
                .help("设置")
            }
            .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .frame(minHeight: 52)
        .background(CyberColor.bg0.opacity(0.85))
        .buttonStyle(.plain)
    }
}

/// 程序标题：霓虹发光 + 呼吸动画（官网 Chow Duck 赛博朋克效果，无边框）
private struct ChowDuckTitleView: View {
    @State private var breathePhase = false

    var body: some View {
        Text("Chow Duck")
            .font(CyberFont.display(size: 20, weight: .bold))
            .foregroundStyle(CyberColor.textPrimary)
            .tracking(1.5)
            .shadow(color: CyberColor.cyan.opacity(breathePhase ? 0.95 : 0.55), radius: breathePhase ? 10 : 5)
            .shadow(color: CyberColor.cyan.opacity(breathePhase ? 0.8 : 0.4), radius: breathePhase ? 22 : 14)
            .shadow(color: CyberColor.cyan.opacity(breathePhase ? 0.5 : 0.25), radius: breathePhase ? 40 : 26)
            .animation(.easeInOut(duration: 1.5).repeatForever(autoreverses: true), value: breathePhase)
            .onAppear { breathePhase = true }
    }
}

/// 顶部栏图标按钮：统一尺寸与点击区域
private struct ToolbarIconButton: View {
    let systemName: String
    let color: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 17, weight: .medium))
                .foregroundColor(color)
                .frame(width: 36, height: 36)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

struct ServiceStatusIndicator: View {
    let label: String
    let isRunning: Bool
    let onTap: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 6) {
                Circle()
                    .fill(isRunning ? CyberColor.green : CyberColor.red)
                    .frame(width: 10, height: 10)
                    .shadow(color: (isRunning ? CyberColor.green : CyberColor.red).opacity(0.5), radius: 4)
                Text(label)
                    .font(CyberFont.mono(size: 12))
                    .foregroundColor(CyberColor.textPrimary)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(CyberColor.bg2)
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(CyberColor.border, lineWidth: 0.5)
            )
            .cornerRadius(6)
        }
        .buttonStyle(.plain)
        .help(isRunning ? "点击停止 \(label)" : "点击启动 \(label)")
    }
}

// MARK: - Duck 分身状态指示器

/// 顶部栏 Duck 状态行：仅当 Chow Duck 已启用且有已注册 Duck 时才显示
/// task/timer 始终运行以保证数据能被拉取，等数据到达后条件视图才渲染
private struct DuckStatusRow: View {
    @EnvironmentObject var viewModel: AgentViewModel
    // 每 5 秒轮询一次，确保任务执行中状态及时更新
    private let refreshTimer = Timer.publish(every: 5, on: .main, in: .common).autoconnect()

    var body: some View {
        // 无论 duck 列表是否为空，容器始终存在，以便 task/timer 能正常工作
        Group {
            if viewModel.chowDuckEnabled && !viewModel.duckList.isEmpty {
                HStack(spacing: 6) {
                    // 竖分割线
                    Rectangle()
                        .fill(CyberColor.border)
                        .frame(width: 1, height: 16)

                    // 每个 Duck 的状态 Pill
                    ForEach(viewModel.duckList.indices, id: \.self) { i in
                        let duck = viewModel.duckList[i]
                        DuckStatusPill(duck: duck)
                            .environmentObject(viewModel)
                    }
                }
            }
        }
        // task 和 timer 挂在 Group 上，无论内容是否可见都会运行
        .task {
            await viewModel.refreshDuckStatus()
        }
        .onReceive(refreshTimer) { _ in
            Task { await viewModel.refreshDuckStatus() }
        }
    }
}

/// 单个 Duck 的状态胶囊：彩色圆点 + 名称（可点击查看详情）
private struct DuckStatusPill: View {
    @EnvironmentObject var viewModel: AgentViewModel
    let duck: [String: Any]
    @State private var showDetail = false

    private var name: String {
        duck["name"] as? String ?? "Duck"
    }

    private var status: String {
        duck["status"] as? String ?? "offline"
    }

    private var statusColor: Color {
        switch status {
        case "online":  return CyberColor.green
        case "busy":    return CyberColor.orange
        default:        return CyberColor.textSecond
        }
    }

    private var statusLabel: String {
        switch status {
        case "online":  return "在线"
        case "busy":    return "忙碌"
        default:        return "离线"
        }
    }

    var body: some View {
        Button {
            showDetail = true
        } label: {
            HStack(spacing: 5) {
                Circle()
                    .fill(statusColor)
                    .frame(width: 7, height: 7)
                    .shadow(color: statusColor.opacity(0.7), radius: 3)
                Text(name)
                    .font(CyberFont.mono(size: 10))
                    .foregroundColor(CyberColor.textPrimary)
                    .lineLimit(1)
            }
            .padding(.horizontal, 7)
            .padding(.vertical, 4)
            .background(CyberColor.bg2)
            .overlay(
                RoundedRectangle(cornerRadius: 5)
                    .stroke(statusColor.opacity(0.4), lineWidth: 0.5)
            )
            .cornerRadius(5)
        }
        .buttonStyle(.plain)
        .help("\(name) — \(statusLabel)")
#if os(macOS)
        .popover(isPresented: $showDetail, arrowEdge: .bottom) {
            DuckQuickInfoPopover(duck: duck)
                .environmentObject(viewModel)
        }
#endif
    }
}

/// 顶部栏点击 Duck 后弹出的快速信息卡片
private struct DuckQuickInfoPopover: View {
    @EnvironmentObject var viewModel: AgentViewModel
    let duck: [String: Any]

    private var duckId: String {
        duck["duck_id"] as? String ?? ""
    }

    private var name: String {
        duck["name"] as? String ?? duckId
    }

    private var duckType: String {
        duck["duck_type"] as? String ?? ""
    }

    private var status: String {
        duck["status"] as? String ?? "offline"
    }

    private var isLocal: Bool {
        duck["is_local"] as? Bool ?? false
    }

    private var hostname: String {
        duck["hostname"] as? String ?? ""
    }

    private var completed: Int {
        duck["completed_tasks"] as? Int ?? 0
    }

    private var failed: Int {
        duck["failed_tasks"] as? Int ?? 0
    }

    private var currentTaskId: String? {
        duck["current_task_id"] as? String
    }

    private var busyReason: String? {
        duck["busy_reason"] as? String
    }

    private var statusColor: Color {
        switch status {
        case "online":  return CyberColor.green
        case "busy":    return CyberColor.orange
        default:        return CyberColor.textSecond
        }
    }

    private var statusLabel: String {
        switch status {
        case "online":  return "在线"
        case "busy":    return "忙碌"
        default:        return "离线"
        }
    }

    private var hasRunningTask: Bool {
        if let tid = currentTaskId, !tid.isEmpty {
            return true
        }
        return status == "busy"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Text("🦆")
                VStack(alignment: .leading, spacing: 2) {
                    Text(name)
                        .font(CyberFont.body(size: 13, weight: .semibold))
                        .foregroundColor(CyberColor.textPrimary)
                    if !duckType.isEmpty {
                        Text(duckType)
                            .font(CyberFont.body(size: 11))
                            .foregroundColor(CyberColor.cyan)
                    }
                }
                Spacer()
                HStack(spacing: 4) {
                    Circle()
                        .fill(statusColor)
                        .frame(width: 8, height: 8)
                    Text(statusLabel)
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(statusColor)
                }
            }

            if isLocal || !hostname.isEmpty {
                HStack(spacing: 6) {
                    if isLocal {
                        Text("本地")
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(.blue)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 1)
                            .background(Color.blue.opacity(0.1))
                            .cornerRadius(4)
                    }
                    if !hostname.isEmpty {
                        Text(hostname)
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                }
            }

            HStack(spacing: 12) {
                Text("完成 \(completed)")
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(CyberColor.textSecond)
                Text("失败 \(failed)")
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(CyberColor.textSecond)
            }

            if let tid = currentTaskId, !tid.isEmpty {
                Text("当前任务：\(tid)")
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(CyberColor.textSecond)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }

            if let reason = busyReason, !reason.isEmpty {
                Text("原因：\(reason)")
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(CyberColor.textSecond.opacity(0.8))
            }

            if hasRunningTask {
                Divider()
                Button {
                    viewModel.stopTask()
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "stop.circle.fill")
                        Text("停止任务")
                    }
                    .font(CyberFont.body(size: 12, weight: .medium))
                }
                .buttonStyle(.borderedProminent)
                .tint(CyberColor.red)
            }
        }
        .padding(12)
        .frame(minWidth: 260)
        .background(CyberColor.bg1)
        .cornerRadius(10)
    }
}

#Preview {
    ContentView()
        .environmentObject(AgentViewModel())
}
