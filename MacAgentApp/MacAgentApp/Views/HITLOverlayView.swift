import SwiftUI

/// HITL 人工审批覆盖层 — 当有待确认操作时显示在聊天界面上方
struct HITLOverlayView: View {
    @EnvironmentObject var viewModel: AgentViewModel

    var body: some View {
        Group {
            if let request = viewModel.pendingHitlRequests.first {
                ZStack {
                    Color.black.opacity(0.45)
                        .ignoresSafeArea()
                    HITLConfirmCard(request: request)
                }
                .transition(.opacity)
                .animation(.easeInOut(duration: 0.2), value: viewModel.pendingHitlRequests.count)
            }
        }
    }
}

private struct HITLConfirmCard: View {
    @EnvironmentObject var viewModel: AgentViewModel
    let request: HitlRequest

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // 标题行
            HStack(spacing: 10) {
                Image(systemName: riskIcon)
                    .foregroundColor(request.riskColor)
                    .font(.title2)
                VStack(alignment: .leading, spacing: 2) {
                    Text("需要人工审批")
                        .font(CyberFont.body(size: 14, weight: .semibold))
                    Text("风险等级: \(riskLevelText)")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(request.riskColor)
                }
                Spacer()
                Text("\(viewModel.pendingHitlRequests.count) 个待确认")
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(.secondary)
            }

            Divider()

            // 操作详情
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("操作类型：")
                        .font(CyberFont.body(size: 12, weight: .medium))
                    Text(request.actionType)
                        .font(CyberFont.body(size: 12))
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(CyberColor.cyan.opacity(0.15))
                        .cornerRadius(4)
                    Spacer()
                }
                Text("操作描述：")
                    .font(CyberFont.body(size: 12, weight: .medium))
                Text(request.description)
                    .font(CyberFont.body(size: 12))
                    .foregroundColor(.primary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Divider()

            // 按钮
            HStack(spacing: 12) {
                Button(role: .destructive) {
                    Task { await viewModel.hitlReject(request) }
                } label: {
                    Label("拒绝", systemImage: "xmark.circle.fill")
                        .frame(maxWidth: .infinity)
                }
                .controlSize(.large)
                .buttonStyle(.bordered)
                .tint(.red)

                Button {
                    Task { await viewModel.hitlConfirm(request) }
                } label: {
                    Label("批准执行", systemImage: "checkmark.circle.fill")
                        .frame(maxWidth: .infinity)
                }
                .controlSize(.large)
                .buttonStyle(.borderedProminent)
                .tint(CyberColor.cyan)
            }
        }
        .padding(20)
        .frame(width: 420)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(NSColor.windowBackgroundColor))
                .shadow(color: .black.opacity(0.4), radius: 20, x: 0, y: 8)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(request.riskColor.opacity(0.5), lineWidth: 1.5)
        )
    }

    private var riskIcon: String {
        switch request.riskLevel {
        case "high": return "exclamationmark.triangle.fill"
        case "medium": return "exclamationmark.circle.fill"
        default: return "info.circle.fill"
        }
    }

    private var riskLevelText: String {
        switch request.riskLevel {
        case "high": return "高危"
        case "medium": return "中危"
        default: return "低危"
        }
    }
}
