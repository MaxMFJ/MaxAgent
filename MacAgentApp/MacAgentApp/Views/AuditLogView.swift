import SwiftUI

/// 审计日志浏览器
struct AuditLogView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @State private var selectedType: String = ""
    private let typeOptions = ["", "action_execute", "hitl_approved", "hitl_rejected", "hitl_timeout", "action_blocked", "session_start", "session_end", "config_change", "error"]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // 过滤栏
            HStack(spacing: 10) {
                Text("类型筛选:")
                    .font(CyberFont.body(size: 12))
                Picker("", selection: $selectedType) {
                    Text("全部").tag("")
                    ForEach(typeOptions.dropFirst(), id: \.self) { t in
                        Text(t).tag(t)
                    }
                }
                .pickerStyle(.menu)
                .frame(width: 180)
                .onChange(of: selectedType) { _, newValue in
                    Task { await viewModel.loadAuditLogs(logType: newValue.isEmpty ? nil : newValue) }
                }

                Spacer()

                Button {
                    Task { await viewModel.loadAuditLogs(logType: selectedType.isEmpty ? nil : selectedType) }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.borderless)
                .disabled(viewModel.isLoadingAuditLogs)
            }
            .padding(12)
            .background(Color(NSColor.controlBackgroundColor).opacity(0.5))

            Divider()

            if viewModel.isLoadingAuditLogs {
                ProgressView("加载中…").frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if viewModel.auditLogs.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "doc.text.magnifyingglass")
                        .font(.largeTitle).foregroundColor(.secondary)
                    Text("暂无审计记录")
                        .font(CyberFont.body(size: 12)).foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(viewModel.auditLogs.indices, id: \.self) { i in
                    AuditLogRow(log: viewModel.auditLogs[i])
                        .listRowSeparator(.visible)
                }
                .listStyle(.inset)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear {
            Task { await viewModel.loadAuditLogs() }
        }
    }
}

// MARK: - Audit Log Row

private struct AuditLogRow: View {
    let log: [String: Any]

    var body: some View {
        let logType = log["type"] as? String ?? ""
        let ts = log["ts"] as? String ?? ""
        let actionType = log["action_type"] as? String ?? ""
        let result = log["result"] as? String ?? ""
        let paramsSummary = log["params_summary"] as? String ?? ""
        let riskLevel = log["risk_level"] as? String ?? ""

        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                Text(typeIcon(logType))
                    .font(.system(size: 14))
                Text(logType)
                    .font(CyberFont.body(size: 11, weight: .semibold))
                    .foregroundColor(typeColor(logType))
                if !actionType.isEmpty {
                    Text(actionType)
                        .font(CyberFont.body(size: 10))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(CyberColor.cyan.opacity(0.12))
                        .cornerRadius(4)
                }
                if !riskLevel.isEmpty {
                    Text(riskLevel)
                        .font(CyberFont.body(size: 9))
                        .foregroundColor(riskColor(riskLevel))
                }
                Spacer()
                Text(formatTimestamp(ts))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.secondary)
            }
            if !paramsSummary.isEmpty {
                Text(paramsSummary)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.primary)
                    .lineLimit(2)
            }
            if !result.isEmpty {
                Text("结果: \(result)")
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(result == "success" ? .green : result == "failed" ? .red : .secondary)
            }
        }
        .padding(.vertical, 4)
    }

    private func typeIcon(_ t: String) -> String {
        switch t {
        case "action_execute": return "⚡"
        case "action_blocked": return "🛑"
        case "hitl_approved": return "✅"
        case "hitl_rejected", "hitl_timeout": return "❌"
        case "hitl_pending": return "⏳"
        case "session_start": return "🔌"
        case "session_end": return "🔴"
        case "config_change": return "⚙️"
        case "error": return "🔥"
        default: return "📝"
        }
    }

    private func typeColor(_ t: String) -> Color {
        switch t {
        case "action_blocked", "hitl_rejected", "error": return .red
        case "hitl_approved": return .green
        case "hitl_pending": return .orange
        default: return CyberColor.cyan
        }
    }

    private func riskColor(_ r: String) -> Color {
        switch r {
        case "high": return .red
        case "medium": return .orange
        case "critical": return .purple
        default: return .secondary
        }
    }

    private func formatTimestamp(_ ts: String) -> String {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = iso.date(from: ts) {
            let f = DateFormatter()
            f.dateFormat = "MM-dd HH:mm:ss"
            return f.string(from: date)
        }
        return String(ts.prefix(19))
    }
}
