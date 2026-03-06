import SwiftUI

/// 快照/回滚侧边面板 — 在 ToolPanelView 中展示当前任务的文件操作快照列表
struct RollbackPanelView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @State private var filterTaskId: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // 标题栏
            HStack {
                Image(systemName: "clock.arrow.circlepath")
                    .foregroundColor(CyberColor.cyan)
                Text("文件快照")
                    .font(CyberFont.body(size: 13, weight: .semibold))
                Spacer()
                Button {
                    Task { await viewModel.loadSnapshots(taskId: viewModel.currentTaskId) }
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 11))
                }
                .buttonStyle(.borderless)
            }
            .padding(.horizontal, 12)
            .padding(.top, 12)

            // 回滚消息
            if let msg = viewModel.rollbackMessage {
                Text(msg)
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(msg.hasPrefix("✅") ? .green : .red)
                    .padding(.horizontal, 12)
            }

            Divider()

            if viewModel.isLoadingSnapshots {
                ProgressView("加载中…")
                    .frame(maxWidth: .infinity)
                    .padding()
            } else if viewModel.snapshots.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "doc.badge.clock")
                        .font(.largeTitle)
                        .foregroundColor(.secondary)
                    Text("暂无快照")
                        .font(CyberFont.body(size: 12))
                        .foregroundColor(.secondary)
                    Text("文件写入/删除/移动前会自动生成快照")
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding()
            } else {
                ScrollView {
                    LazyVStack(spacing: 6) {
                        ForEach(viewModel.snapshots.indices, id: \.self) { i in
                            SnapshotRow(snapshot: viewModel.snapshots[i]) { snapshotId in
                                Task { await viewModel.rollback(snapshotId: snapshotId) }
                            }
                            .padding(.horizontal, 8)
                        }
                    }
                    .padding(.bottom, 12)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .onAppear {
            Task { await viewModel.loadSnapshots(taskId: viewModel.currentTaskId) }
        }
    }
}

// MARK: - Snapshot Row

private struct SnapshotRow: View {
    let snapshot: [String: Any]
    let onRollback: (String) -> Void

    var body: some View {
        let snapshotId = snapshot["snapshot_id"] as? String ?? ""
        let operation = snapshot["operation"] as? String ?? "unknown"
        let path = snapshot["path"] as? String ?? ""
        let timestamp = snapshot["timestamp"] as? String ?? ""
        let applied = snapshot["applied"] as? Bool ?? false

        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: operationIcon(operation))
                    .foregroundColor(operationColor(operation))
                    .frame(width: 14)
                Text(operation)
                    .font(CyberFont.body(size: 11, weight: .medium))
                    .foregroundColor(operationColor(operation))
                Spacer()
                if applied {
                    Text("已回滚")
                        .font(CyberFont.body(size: 9))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Color.green.opacity(0.15))
                        .foregroundColor(.green)
                        .cornerRadius(4)
                } else {
                    Button("撤销") {
                        onRollback(snapshotId)
                    }
                    .font(CyberFont.body(size: 11))
                    .buttonStyle(.bordered)
                    .controlSize(.mini)
                    .tint(CyberColor.cyan)
                }
            }
            Text((path as NSString).lastPathComponent)
                .font(CyberFont.body(size: 11))
                .lineLimit(1)
            Text(path)
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.secondary)
                .lineLimit(1)
            if !timestamp.isEmpty {
                Text(formatTimestamp(timestamp))
                    .font(CyberFont.body(size: 9))
                    .foregroundColor(.secondary)
            }
        }
        .padding(8)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(6)
    }

    private func operationIcon(_ op: String) -> String {
        switch op {
        case "write": return "doc.fill"
        case "delete": return "trash.fill"
        case "move": return "arrow.right.doc.on.clipboard"
        case "copy": return "doc.on.doc.fill"
        default: return "doc"
        }
    }

    private func operationColor(_ op: String) -> Color {
        switch op {
        case "write": return CyberColor.cyan
        case "delete": return .red
        case "move": return .orange
        case "copy": return .purple
        default: return .secondary
        }
    }

    private func formatTimestamp(_ ts: String) -> String {
        // ISO8601 to "HH:mm:ss"
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = iso.date(from: ts) {
            let f = DateFormatter()
            f.dateFormat = "MM-dd HH:mm:ss"
            return f.string(from: date)
        }
        return ts
    }
}
