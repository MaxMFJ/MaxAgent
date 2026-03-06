import SwiftUI

struct TunnelView: View {
    @StateObject private var tunnelManager = TunnelManager.shared
    @State private var showInstallInstructions = false
    @State private var showUserGuide = false
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                tunnelStatusSection
                
                // 退避/仅局域网 警告
                if tunnelManager.isLanOnly {
                    lanOnlyBanner
                } else if tunnelManager.consecutiveFailures > 0 {
                    backoffBanner
                }
                
                if tunnelManager.isTunnelRunning && !tunnelManager.tunnelURL.isEmpty {
                    connectionInfoSection
                    qrCodeSection
                    connectedClientsSection
                }
                
                // 局域网连接面板（始终显示）
                lanInfoSection
                
                authSection
                
                // 用户使用指南入口
                userGuideSection
                
                logsSection
            }
            .padding(20)
        }
    }
    
    // MARK: - Tunnel Status
    
    private var tunnelStatusSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Cloudflare Tunnel")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                
                Spacer()
                
                Circle()
                    .fill(statusColor)
                    .frame(width: 10, height: 10)
                
                Text(statusText)
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(.secondary)
            }
            
            VStack(alignment: .leading, spacing: 12) {
                if !tunnelManager.checkCloudflaredInstalled() {
                    installPrompt
                } else {
                    // 自动启动开关
                    Toggle("随后端自动启动 Tunnel", isOn: Binding(
                        get: { tunnelManager.autoStartEnabled },
                        set: { tunnelManager.setAutoStart($0) }
                    ))
                    .toggleStyle(.switch)
                    
                    Text("开启后，后端服务启动时将自动启动 Cloudflare Tunnel（异步，不影响后端启动速度）")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                    
                    Divider()
                    
                    HStack(spacing: 12) {
                        if tunnelManager.isTunnelRunning {
                            Button(action: { tunnelManager.stopTunnelViaBackend() }) {
                                Label("停止 Tunnel", systemImage: "stop.fill")
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.red)
                            
                            Button(action: {
                                Task { tunnelManager.startTunnelViaBackend() }
                            }) {
                                Label("重启", systemImage: "arrow.clockwise")
                            }
                            .buttonStyle(.bordered)
                        } else {
                            Button(action: { tunnelManager.startTunnelViaBackend() }) {
                                Label("启动 Tunnel", systemImage: "play.fill")
                            }
                            .buttonStyle(.borderedProminent)
                        }
                        
                        Text("将本地服务暴露到公网，供 iOS 设备远程访问")
                            .font(CyberFont.body(size: 11))
                            .foregroundColor(.secondary)
                    }
                    
                    if tunnelManager.totalRestarts > 0 {
                        Text("累计自动重启: \(tunnelManager.totalRestarts) 次")
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(.secondary)
                    }
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
    }
    
    private var statusColor: Color {
        if tunnelManager.isLanOnly { return .orange }
        if tunnelManager.isTunnelRunning { return .green }
        return .gray
    }
    
    private var statusText: String {
        if tunnelManager.isLanOnly { return "仅局域网" }
        if tunnelManager.isTunnelRunning { return "运行中" }
        if tunnelManager.consecutiveFailures > 0 { return "连接中断" }
        return "已停止"
    }
    
    private var installPrompt: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundColor(.orange)
                Text("cloudflared 未安装")
                    .fontWeight(.medium)
            }
            
            Text("请先安装 Cloudflare Tunnel CLI 工具")
                .font(CyberFont.body(size: 11))
                .foregroundColor(.secondary)
            
            HStack {
                Button("安装说明") {
                    showInstallInstructions = true
                }
                
                Button("使用 Homebrew 安装") {
                    NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:")!)
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString("brew install cloudflared", forType: .string)
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .sheet(isPresented: $showInstallInstructions) {
            installInstructionsSheet
        }
    }
    
    private var installInstructionsSheet: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("安装 cloudflared")
                .font(CyberFont.body(size: 18, weight: .semibold))
                .fontWeight(.bold)
            
            VStack(alignment: .leading, spacing: 12) {
                Text("方式 1: 使用 Homebrew (推荐)")
                    .fontWeight(.medium)
                
                HStack {
                    Text("brew install cloudflared")
                        .font(CyberFont.mono(size: 14))
                        .padding(8)
                        .background(Color(NSColor.textBackgroundColor))
                        .cornerRadius(4)
                    
                    Button(action: {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString("brew install cloudflared", forType: .string)
                    }) {
                        Image(systemName: "doc.on.doc")
                    }
                }
            }
            
            Divider()
            
            VStack(alignment: .leading, spacing: 12) {
                Text("方式 2: 官方下载")
                    .fontWeight(.medium)
                
                Link("下载 cloudflared →", destination: URL(string: "https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/")!)
            }
            
            Spacer()
            
            HStack {
                Spacer()
                Button("关闭") {
                    showInstallInstructions = false
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(20)
        .frame(width: 450, height: 300)
    }
    
    // MARK: - Backoff / LAN-Only Banners
    
    private var lanOnlyBanner: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "wifi.exclamationmark")
                    .foregroundColor(.orange)
                    .font(CyberFont.body(size: 16, weight: .semibold))
                Text("已切换为仅局域网模式")
                    .fontWeight(.medium)
                    .foregroundColor(.orange)
            }
            
            Text("Cloudflare Tunnel 连续 \(tunnelManager.consecutiveFailures) 次连接失败，可能因 IP 被暂时封禁或网络波动。系统将自动重试。")
                .font(CyberFont.body(size: 11))
                .foregroundColor(.secondary)
            
            if let backoffStr = tunnelManager.backoffUntil {
                Text("下次重试: \(backoffStr)")
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(.secondary)
            }
            
            Text("请使用局域网地址（见下方）连接，或等待自动恢复。")
                .font(CyberFont.body(size: 11))
                .foregroundColor(.secondary)
        }
        .padding()
        .background(Color.orange.opacity(0.1))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.orange.opacity(0.3), lineWidth: 1)
        )
        .cornerRadius(8)
    }
    
    private var backoffBanner: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: "arrow.clockwise.circle")
                    .foregroundColor(.yellow)
                Text("连接中断，尝试重连中...")
                    .fontWeight(.medium)
                    .font(CyberFont.body(size: 14))
            }
            Text("连续失败 \(tunnelManager.consecutiveFailures) 次，退避 \(tunnelManager.currentBackoffSeconds)s 后重试")
                .font(CyberFont.body(size: 11))
                .foregroundColor(.secondary)
        }
        .padding()
        .background(Color.yellow.opacity(0.08))
        .cornerRadius(8)
    }
    
    // MARK: - LAN Info
    
    private var lanInfoSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("局域网连接")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                Spacer()
                
                if tunnelManager.isLanOnly {
                    Text("当前模式")
                        .font(CyberFont.body(size: 11))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Color.orange.opacity(0.2))
                        .cornerRadius(4)
                } else {
                    Text("备用")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                }
            }
            
            VStack(alignment: .leading, spacing: 10) {
                if !tunnelManager.lanIP.isEmpty {
                    InfoRow(label: "IP 地址", value: tunnelManager.lanIP)
                    InfoRow(label: "HTTP", value: tunnelManager.lanHTTPUrl)
                    InfoRow(label: "WebSocket", value: tunnelManager.lanWSUrl)
                    
                    HStack {
                        Button(action: { tunnelManager.copyLanInfo() }) {
                            Label("复制局域网连接信息", systemImage: "doc.on.doc")
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        
                        Spacer()
                    }
                } else {
                    HStack {
                        ProgressView()
                            .controlSize(.small)
                        Text("获取局域网信息中...")
                            .font(CyberFont.body(size: 11))
                            .foregroundColor(.secondary)
                    }
                }
                
                Text("同一 Wi-Fi 下的设备可直接使用局域网地址连接，无需公网隧道。")
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(.secondary)
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
    }
    
    // MARK: - User Guide
    
    private var userGuideSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("远程连接指南")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                Spacer()
                Button(action: { showUserGuide.toggle() }) {
                    Label(showUserGuide ? "收起" : "展开", systemImage: showUserGuide ? "chevron.up" : "chevron.down")
                }
                .buttonStyle(.plain)
                .foregroundColor(.accentColor)
            }
            
            if showUserGuide {
                VStack(alignment: .leading, spacing: 16) {
                    GuideStep(number: 1, title: "安装 cloudflared",
                              desc: "Mac 上执行 brew install cloudflared，安装 Cloudflare Tunnel CLI 工具。")
                    
                    GuideStep(number: 2, title: "启动 Tunnel（或开启自动启动）",
                              desc: "在本页点击「启动 Tunnel」，或开启上方的「随后端自动启动」开关。系统将异步启动隧道，不影响后端性能。")
                    
                    GuideStep(number: 3, title: "获取连接地址",
                              desc: "Tunnel 启动后，上方会显示公网地址（xxx.trycloudflare.com）。每次重启会生成新地址。若配置了 SMTP 邮件，新地址会自动发送到邮箱。")
                    
                    GuideStep(number: 4, title: "iOS 端连接",
                              desc: "打开 iOS App → 设置 → 输入公网地址，或扫描上方二维码自动配置。同一 Wi-Fi 下也可直接使用局域网地址。")
                    
                    GuideStep(number: 5, title: "自动重连与退避",
                              desc: "后端会持续监控隧道健康状态。断线时自动重启并更新地址。若连续失败（如 IP 被封），系统会以指数退避策略重试（30s → 60s → 最大 30min），并切换为仅局域网模式。恢复后自动切回。")
                    
                    GuideStep(number: 6, title: "邮件通知（可选）",
                              desc: "在「设置 → 邮件」中配置 SMTP 后，Tunnel 地址变更时会自动发送邮件通知，确保您始终知道最新地址。")
                    
                    Divider()
                    
                    VStack(alignment: .leading, spacing: 6) {
                        Text("常见问题")
                            .fontWeight(.medium)
                        Text("• 地址变了？ — 每次 cloudflared 重启会获得新地址，开启邮件通知可自动接收。")
                            .font(CyberFont.body(size: 11))
                        Text("• 连不上？ — 检查 Mac 是否在运行、后端是否启动、cloudflared 是否安装。")
                            .font(CyberFont.body(size: 11))
                        Text("• IP 被封？ — 系统会自动退避重试，期间可用局域网连接。通常 10-30 分钟后恢复。")
                            .font(CyberFont.body(size: 11))
                    }
                }
                .padding()
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)
            }
        }
    }
    
    // MARK: - Connection Info
    
    private var connectionInfoSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("连接信息")
                .font(CyberFont.body(size: 14, weight: .semibold))
            
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("公网地址:")
                        .foregroundColor(.secondary)
                    
                    Text(tunnelManager.tunnelURL)
                        .font(CyberFont.mono(size: 14))
                        .textSelection(.enabled)
                    
                    Spacer()
                    
                    Button(action: { tunnelManager.copyTunnelURL() }) {
                        Image(systemName: "doc.on.doc")
                    }
                    .buttonStyle(.plain)
                    .help("复制 URL")
                }
                
                if tunnelManager.isAuthEnabled && !tunnelManager.authToken.isEmpty {
                    HStack {
                        Text("认证 Token:")
                            .foregroundColor(.secondary)
                        
                        Text(String(tunnelManager.authToken.prefix(20)) + "...")
                            .font(CyberFont.mono(size: 14))
                        
                        Spacer()
                        
                        Button(action: { tunnelManager.copyConnectionInfo() }) {
                            Image(systemName: "square.and.arrow.up")
                        }
                        .buttonStyle(.plain)
                        .help("复制完整连接信息")
                    }
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
    }
    
    // MARK: - QR Code
    
    private var qrCodeSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("扫码连接")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                
                Spacer()
                
                Text("使用 iOS App 扫描此二维码")
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(.secondary)
            }
            
            HStack {
                Spacer()
                
                if let qrImage = tunnelManager.qrCodeImage {
                    VStack(spacing: 8) {
                        Image(nsImage: qrImage)
                            .interpolation(.none)
                            .resizable()
                            .frame(width: 180, height: 180)
                            .background(Color.white)
                            .cornerRadius(8)
                        
                        Text("包含: URL" + (tunnelManager.isAuthEnabled ? " + Token" : ""))
                            .font(CyberFont.body(size: 11))
                            .foregroundColor(.secondary)
                    }
                } else {
                    VStack {
                        ProgressView()
                        Text("生成中...")
                            .font(CyberFont.body(size: 11))
                            .foregroundColor(.secondary)
                    }
                    .frame(width: 180, height: 180)
                }
                
                Spacer()
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
    }
    
    // MARK: - Connected Clients
    
    private var connectedClientsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("连接的客户端")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                
                Spacer()
                
                Text("\(tunnelManager.connectedClients.count) 个")
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(.secondary)
            }
            
            VStack(alignment: .leading, spacing: 8) {
                if tunnelManager.connectedClients.isEmpty {
                    HStack {
                        Image(systemName: "iphone.slash")
                            .foregroundColor(.secondary)
                        Text("暂无客户端连接")
                            .foregroundColor(.secondary)
                    }
                    .padding(.vertical, 8)
                } else {
                    ForEach(tunnelManager.connectedClients) { client in
                        HStack {
                            Image(systemName: client.clientType == "ios" ? "iphone" : "desktopcomputer")
                                .foregroundColor(.accentColor)
                            
                            Text(client.clientType.uppercased())
                                .fontWeight(.medium)
                            
                            Spacer()
                            
                            Text(client.id)
                                .font(CyberFont.body(size: 11))
                                .foregroundColor(.secondary)
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
    }
    
    // MARK: - Auth Section
    
    private var authSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("访问控制")
                .font(CyberFont.body(size: 14, weight: .semibold))
            
            VStack(alignment: .leading, spacing: 12) {
                Toggle("启用 Token 认证", isOn: Binding(
                    get: { tunnelManager.isAuthEnabled },
                    set: { enabled in
                        if enabled {
                            tunnelManager.generateAuthToken()
                        } else {
                            tunnelManager.disableAuth()
                        }
                    }
                ))
                
                Text("启用后，iOS 客户端需要提供正确的 Token 才能连接")
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(.secondary)
                
                if tunnelManager.isAuthEnabled {
                    Divider()
                    
                    HStack {
                        Button("重新生成 Token") {
                            tunnelManager.generateAuthToken()
                        }
                        
                        Text("生成新 Token 后，需要重新扫码或手动更新 iOS 端配置")
                            .font(CyberFont.body(size: 11))
                            .foregroundColor(.secondary)
                    }
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
    }
    
    // MARK: - Logs
    
    private var logsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Tunnel 日志")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                
                Spacer()
                
                Button(action: { tunnelManager.refreshLogsIfExternal() }) {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .help("刷新日志")
                
                Button(action: { tunnelManager.clearLogs() }) {
                    Image(systemName: "trash")
                }
                .buttonStyle(.plain)
                .help("清除日志")
            }
            
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 2) {
                    ForEach(tunnelManager.tunnelLogs.suffix(100)) { log in
                        HStack(alignment: .top, spacing: 8) {
                            Text(formatTime(log.timestamp))
                                .font(CyberFont.mono(size: 11))
                                .foregroundColor(.secondary)
                                .frame(width: 70, alignment: .leading)
                            
                            Circle()
                                .fill(logLevelColor(log.level))
                                .frame(width: 6, height: 6)
                                .padding(.top, 4)
                            
                            Text(log.message)
                                .font(CyberFont.mono(size: 11))
                                .foregroundColor(logLevelColor(log.level))
                                .textSelection(.enabled)
                        }
                    }
                }
                .padding(8)
            }
            .frame(height: 150)
            .background(Color(NSColor.textBackgroundColor))
            .cornerRadius(8)
        }
    }
    
    private func formatTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        return formatter.string(from: date)
    }
    
    private func logLevelColor(_ level: TunnelManager.LogEntry.LogLevel) -> Color {
        switch level {
        case .error: return .red
        case .warning: return .orange
        case .debug: return .gray
        case .info: return .primary
        }
    }
}

// MARK: - Helper Views

/// 信息行（标签 + 值）
private struct InfoRow: View {
    let label: String
    let value: String
    
    var body: some View {
        HStack {
            Text("\(label):")
                .foregroundColor(.secondary)
                .frame(width: 80, alignment: .trailing)
            Text(value)
                .font(CyberFont.mono(size: 14))
                .textSelection(.enabled)
            Spacer()
        }
    }
}

/// 用户指南步骤
private struct GuideStep: View {
    let number: Int
    let title: String
    let desc: String
    
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text("\(number)")
                .font(CyberFont.body(size: 11))
                .fontWeight(.bold)
                .foregroundColor(.white)
                .frame(width: 22, height: 22)
                .background(Circle().fill(Color.accentColor))
            
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .fontWeight(.medium)
                Text(desc)
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(.secondary)
            }
        }
    }
}

#Preview {
    TunnelView()
        .frame(width: 600, height: 900)
}
