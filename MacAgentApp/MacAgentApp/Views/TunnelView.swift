import SwiftUI

struct TunnelView: View {
    @StateObject private var tunnelManager = TunnelManager.shared
    @State private var showInstallInstructions = false
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                tunnelStatusSection
                
                if tunnelManager.isTunnelRunning && !tunnelManager.tunnelURL.isEmpty {
                    connectionInfoSection
                    qrCodeSection
                    connectedClientsSection
                }
                
                authSection
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
                    .font(.headline)
                
                Spacer()
                
                Circle()
                    .fill(tunnelManager.isTunnelRunning ? Color.green : Color.gray)
                    .frame(width: 10, height: 10)
                
                Text(tunnelManager.isTunnelRunning ? "运行中" : "已停止")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            VStack(alignment: .leading, spacing: 12) {
                if !tunnelManager.checkCloudflaredInstalled() {
                    installPrompt
                } else {
                    HStack(spacing: 12) {
                        if tunnelManager.isTunnelRunning {
                            Button(action: { tunnelManager.stopTunnel() }) {
                                Label("停止 Tunnel", systemImage: "stop.fill")
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.red)
                        } else {
                            Button(action: { tunnelManager.startTunnel() }) {
                                Label("启动 Tunnel", systemImage: "play.fill")
                            }
                            .buttonStyle(.borderedProminent)
                        }
                        
                        Text("将本地服务暴露到公网，供 iOS 设备访问")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
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
                .font(.caption)
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
                .font(.title2)
                .fontWeight(.bold)
            
            VStack(alignment: .leading, spacing: 12) {
                Text("方式 1: 使用 Homebrew (推荐)")
                    .fontWeight(.medium)
                
                HStack {
                    Text("brew install cloudflared")
                        .font(.system(.body, design: .monospaced))
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
    
    // MARK: - Connection Info
    
    private var connectionInfoSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("连接信息")
                .font(.headline)
            
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("公网地址:")
                        .foregroundColor(.secondary)
                    
                    Text(tunnelManager.tunnelURL)
                        .font(.system(.body, design: .monospaced))
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
                            .font(.system(.body, design: .monospaced))
                        
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
                    .font(.headline)
                
                Spacer()
                
                Text("使用 iOS App 扫描此二维码")
                    .font(.caption)
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
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                } else {
                    VStack {
                        ProgressView()
                        Text("生成中...")
                            .font(.caption)
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
                    .font(.headline)
                
                Spacer()
                
                Text("\(tunnelManager.connectedClients.count) 个")
                    .font(.caption)
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
                                .font(.caption)
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
                .font(.headline)
            
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
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                if tunnelManager.isAuthEnabled {
                    Divider()
                    
                    HStack {
                        Button("重新生成 Token") {
                            tunnelManager.generateAuthToken()
                        }
                        
                        Text("生成新 Token 后，需要重新扫码或手动更新 iOS 端配置")
                            .font(.caption)
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
                    .font(.headline)
                
                Spacer()
                
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
                                .font(.system(.caption, design: .monospaced))
                                .foregroundColor(.secondary)
                                .frame(width: 70, alignment: .leading)
                            
                            Circle()
                                .fill(logLevelColor(log.level))
                                .frame(width: 6, height: 6)
                                .padding(.top, 4)
                            
                            Text(log.message)
                                .font(.system(.caption, design: .monospaced))
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

#Preview {
    TunnelView()
        .frame(width: 600, height: 700)
}
