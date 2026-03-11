import SwiftUI

struct PortSettingsContent: View {
    @StateObject private var portConfig = PortConfiguration.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // 说明
            VStack(alignment: .leading, spacing: 6) {
                Text("端口配置")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                Text("配置 MacAgent 各服务使用的端口号。修改后需重启应用生效。")
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(.secondary)
            }

            // 端口输入列表
            VStack(spacing: 12) {
                PortRow(label: "后端 API / WebSocket", value: $portConfig.backendPort, defaultValue: PortConfiguration.defaultBackendPort)
                PortRow(label: "AX Bridge (辅助功能桥接)", value: $portConfig.axBridgePort, defaultValue: PortConfiguration.defaultAXBridgePort)
                PortRow(label: "IPC 服务 (TCP)", value: $portConfig.ipcPort, defaultValue: PortConfiguration.defaultIPCPort)
                PortRow(label: "Duck 分身起始端口", value: $portConfig.duckStartPort, defaultValue: PortConfiguration.defaultDuckStartPort)
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)

            // 冲突检测区
            HStack(spacing: 12) {
                Button {
                    portConfig.checkConflicts()
                    portConfig.writePortConfigFile()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "antenna.radiowaves.left.and.right")
                        Text("检测端口冲突")
                    }
                }
                .buttonStyle(.borderedProminent)

                Button {
                    portConfig.resetToDefaults()
                } label: {
                    Text("恢复默认")
                }
            }

            // 冲突结果
            if !portConfig.conflicts.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 4) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.orange)
                        Text("检测到端口冲突")
                            .font(CyberFont.body(size: 13, weight: .semibold))
                            .foregroundColor(.orange)
                    }
                    ForEach(portConfig.conflicts) { conflict in
                        HStack(spacing: 8) {
                            Text("端口 \(conflict.port)")
                                .font(CyberFont.body(size: 12).monospaced())
                                .foregroundColor(CyberColor.cyan)
                            Text(conflict.serviceName)
                                .font(CyberFont.body(size: 12))
                            Text("→ 被 \(conflict.conflictProcess) 占用")
                                .font(CyberFont.body(size: 12))
                                .foregroundColor(.red)
                        }
                    }
                    Text("请修改冲突的端口号，然后重启应用。")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                }
                .padding()
                .background(Color.orange.opacity(0.1))
                .cornerRadius(8)
            } else if portConfig.conflicts.isEmpty {
                // 只在用户点击过检测后显示无冲突
            }

            Spacer()
        }
    }
}

// MARK: - Port Row

private struct PortRow: View {
    let label: String
    @Binding var value: UInt16
    let defaultValue: UInt16

    @State private var text: String = ""

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(CyberFont.body(size: 13))
                Text("默认: \(defaultValue)")
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(.secondary)
            }
            Spacer()
            TextField("端口", text: $text)
                .textFieldStyle(.roundedBorder)
                .frame(width: 80)
                .multilineTextAlignment(.center)
                .onAppear { text = "\(value)" }
                .onChange(of: text) { _, newText in
                    if let parsed = UInt16(newText), parsed >= 1024 {
                        value = parsed
                    }
                }
                .onChange(of: value) { _, newValue in
                    text = "\(newValue)"
                }
        }
    }
}
