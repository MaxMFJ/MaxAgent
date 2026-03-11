import SwiftUI

// MARK: - 人工演示录制视图

struct HumanDemoView: View {
    @StateObject private var demoService = HumanDemoService()
    @State private var taskDescription: String = ""
    @State private var showStartInput: Bool = false
    @State private var selectedDemo: DemoSummary?

    var body: some View {
        VStack(spacing: 0) {
            // 顶部：录制控制区
            demoControlBar

            Rectangle()
                .fill(CyberColor.border)
                .frame(height: 1)

            // 演示列表
            if demoService.isLoading {
                Spacer()
                ProgressView()
                    .tint(CyberColor.cyan)
                Spacer()
            } else if demoService.demos.isEmpty {
                emptyStateView
            } else {
                demoListView
            }

            // 底部错误信息
            if let err = demoService.errorMessage {
                HStack {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 9))
                    Text(err)
                        .font(CyberFont.mono(size: 9))
                        .lineLimit(2)
                }
                .foregroundColor(CyberColor.red)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(CyberColor.red.opacity(0.08))
            }
        }
        .onAppear {
            demoService.updateBaseURL("http://127.0.0.1:\(PortConfiguration.shared.backendPort)")
            Task {
                await demoService.checkStatus()
                await demoService.fetchDemos()
                if demoService.isRecording {
                    demoService.startStatusPolling()
                }
            }
        }
    }

    // MARK: - 录制控制栏

    private var demoControlBar: some View {
        VStack(spacing: 8) {
            if demoService.isRecording {
                // 正在录制人工演示
                HStack(spacing: 8) {
                    Circle()
                        .fill(CyberColor.purple)
                        .frame(width: 8, height: 8)
                        .modifier(DemoPulseAnimation())

                    Text("演示中")
                        .font(CyberFont.mono(size: 11, weight: .semibold))
                        .foregroundColor(CyberColor.purple)

                    Text("请执行你的操作流程")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                        .lineLimit(1)

                    Spacer()

                    Text("\(demoService.activeEventCount) 事件")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.cyan)

                    Button(action: {
                        Task { await demoService.stopDemo() }
                    }) {
                        HStack(spacing: 4) {
                            Image(systemName: "stop.fill")
                                .font(.system(size: 9))
                            Text("完成")
                                .font(CyberFont.mono(size: 10, weight: .medium))
                        }
                        .foregroundColor(CyberColor.purple)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(CyberColor.purple.opacity(0.15))
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(CyberColor.purple.opacity(0.4), lineWidth: 0.5)
                        )
                    }
                    .buttonStyle(.plain)
                }

                // 键盘捕获权限警告
                if !demoService.keyboardCaptureWorking {
                    HStack(spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.system(size: 10))
                            .foregroundColor(.orange)
                        Text("键盘事件无法捕获，请在系统设置 > 隐私与安全 > 输入监控中授权本应用")
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(.orange)
                            .lineLimit(2)
                        Spacer()
                        Button("打开设置") {
                            demoService.openInputMonitoringSettings()
                        }
                        .font(CyberFont.mono(size: 9, weight: .medium))
                        .foregroundColor(CyberColor.cyan)
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.orange.opacity(0.08))
                    .cornerRadius(4)
                }
            } else if showStartInput {
                // 输入任务描述
                VStack(spacing: 6) {
                    Text("描述你要演示的任务:")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    HStack(spacing: 8) {
                        TextField("例: 打开Safari搜索天气...", text: $taskDescription)
                            .font(CyberFont.mono(size: 11))
                            .textFieldStyle(.plain)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 5)
                            .background(CyberColor.bg0)
                            .cornerRadius(4)
                            .overlay(
                                RoundedRectangle(cornerRadius: 4)
                                    .stroke(CyberColor.purple.opacity(0.3), lineWidth: 0.5)
                            )
                            .onSubmit { startDemo() }

                        Button(action: { startDemo() }) {
                            Image(systemName: "checkmark")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundColor(CyberColor.green)
                        }
                        .buttonStyle(.plain)

                        Button(action: { showStartInput = false; taskDescription = "" }) {
                            Image(systemName: "xmark")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundColor(CyberColor.textSecond)
                        }
                        .buttonStyle(.plain)
                    }
                }
            } else {
                // 默认：开始按钮
                HStack {
                    Button(action: { showStartInput = true }) {
                        HStack(spacing: 6) {
                            Image(systemName: "person.badge.plus")
                                .font(.system(size: 12))
                            Text("录制演示")
                                .font(CyberFont.mono(size: 11, weight: .medium))
                        }
                        .foregroundColor(CyberColor.purple)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                        .background(CyberColor.purple.opacity(0.1))
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(CyberColor.purple.opacity(0.3), lineWidth: 0.5)
                        )
                    }
                    .buttonStyle(.plain)

                    Spacer()

                    Button(action: {
                        Task { await demoService.fetchDemos() }
                    }) {
                        Image(systemName: "arrow.clockwise")
                            .font(.system(size: 11))
                            .foregroundColor(CyberColor.textSecond)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(CyberColor.bg2)
    }

    // MARK: - 空状态

    private var emptyStateView: some View {
        VStack(spacing: 12) {
            Spacer()
            Image(systemName: "person.badge.plus")
                .font(.system(size: 32))
                .foregroundColor(CyberColor.textSecond.opacity(0.4))
            Text("教 AI 新技能")
                .font(CyberFont.mono(size: 12))
                .foregroundColor(CyberColor.textSecond)
            Text("点击「录制演示」后亲自操作一遍，\nAI 会学习你的操作流程并自动化执行")
                .font(CyberFont.mono(size: 10))
                .foregroundColor(CyberColor.textSecond.opacity(0.6))
                .multilineTextAlignment(.center)
            Spacer()
        }
    }

    // MARK: - 演示列表

    private var demoListView: some View {
        ScrollView {
            LazyVStack(spacing: 6) {
                ForEach(demoService.demos) { demo in
                    DemoRowView(
                        demo: demo,
                        isSelected: selectedDemo?.id == demo.id,
                        isLearning: demoService.isLearning && selectedDemo?.id == demo.id,
                        onSelect: {
                            selectedDemo = (selectedDemo?.id == demo.id) ? nil : demo
                        },
                        onLearn: {
                            selectedDemo = demo
                            Task { await demoService.learnFromDemo(id: demo.id) }
                        },
                        onApprove: {
                            Task { let _ = await demoService.approveCapsule(id: demo.id) }
                        },
                        onDelete: {
                            Task { await demoService.deleteDemo(id: demo.id) }
                        }
                    )
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 8)
        }
    }

    // MARK: - Actions

    private func startDemo() {
        let desc = taskDescription.trimmingCharacters(in: .whitespaces)
        showStartInput = false
        Task {
            await demoService.startDemo(taskDescription: desc)
            taskDescription = ""
        }
    }
}

// MARK: - 演示行

private struct DemoRowView: View {
    let demo: DemoSummary
    let isSelected: Bool
    let isLearning: Bool
    let onSelect: () -> Void
    let onLearn: () -> Void
    let onApprove: () -> Void
    let onDelete: () -> Void

    @State private var isHovering = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // 主行
            HStack(spacing: 8) {
                statusIcon

                VStack(alignment: .leading, spacing: 2) {
                    Text(demo.task_description.isEmpty ? "未命名演示" : demo.task_description)
                        .font(CyberFont.mono(size: 11, weight: .medium))
                        .foregroundColor(CyberColor.textPrimary)
                        .lineLimit(1)

                    HStack(spacing: 8) {
                        Text("\(demo.step_count) 步")
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(CyberColor.cyan.opacity(0.7))

                        statusBadge

                        Text(formatDate(demo.created_at))
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(CyberColor.textSecond.opacity(0.6))
                    }
                }

                Spacer()

                if isLearning {
                    ProgressView()
                        .scaleEffect(0.6)
                        .tint(CyberColor.purple)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .contentShape(Rectangle())
            .onTapGesture(perform: onSelect)

            // 展开的操作按钮
            if isSelected {
                HStack(spacing: 8) {
                    Spacer()

                    if demo.status == "finished" || demo.status == "recording" {
                        Button(action: onLearn) {
                            HStack(spacing: 4) {
                                Image(systemName: "brain")
                                    .font(.system(size: 9))
                                Text("AI学习")
                                    .font(CyberFont.mono(size: 10))
                            }
                            .foregroundColor(CyberColor.purple)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(CyberColor.purple.opacity(0.1))
                            .cornerRadius(3)
                        }
                        .buttonStyle(.plain)
                        .disabled(isLearning)
                    }

                    if demo.status == "analyzed" {
                        Button(action: onApprove) {
                            HStack(spacing: 4) {
                                Image(systemName: "checkmark.seal")
                                    .font(.system(size: 9))
                                Text("启用技能")
                                    .font(CyberFont.mono(size: 10))
                            }
                            .foregroundColor(CyberColor.green)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(CyberColor.green.opacity(0.1))
                            .cornerRadius(3)
                        }
                        .buttonStyle(.plain)
                    }

                    if demo.status == "approved" {
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark.seal.fill")
                                .font(.system(size: 9))
                            Text("已启用")
                                .font(CyberFont.mono(size: 10))
                        }
                        .foregroundColor(CyberColor.green.opacity(0.6))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                    }

                    Button(action: onDelete) {
                        HStack(spacing: 4) {
                            Image(systemName: "trash")
                                .font(.system(size: 9))
                            Text("删除")
                                .font(CyberFont.mono(size: 10))
                        }
                        .foregroundColor(CyberColor.red)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(CyberColor.red.opacity(0.1))
                        .cornerRadius(3)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 10)
                .padding(.bottom, 8)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 4)
                .fill(isSelected ? CyberColor.purple.opacity(0.08) : (isHovering ? CyberColor.bgHighlight : CyberColor.bg1))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(isSelected ? CyberColor.purple.opacity(0.3) : Color.clear, lineWidth: 0.5)
        )
        .onHover { isHovering = $0 }
        .animation(.easeInOut(duration: 0.15), value: isSelected)
    }

    private var statusIcon: some View {
        Group {
            switch demo.status {
            case "approved":
                Image(systemName: "checkmark.seal.fill")
                    .foregroundColor(CyberColor.green.opacity(0.7))
            case "analyzed":
                Image(systemName: "brain")
                    .foregroundColor(CyberColor.purple.opacity(0.7))
            default:
                Image(systemName: "person.badge.plus")
                    .foregroundColor(CyberColor.cyan.opacity(0.7))
            }
        }
        .font(.system(size: 12))
    }

    private var statusBadge: some View {
        Group {
            switch demo.status {
            case "approved":
                Text("已启用")
                    .foregroundColor(CyberColor.green)
            case "analyzed":
                Text("待审批")
                    .foregroundColor(CyberColor.purple)
            case "finished":
                Text("待学习")
                    .foregroundColor(CyberColor.orange)
            default:
                Text(demo.status)
                    .foregroundColor(CyberColor.textSecond)
            }
        }
        .font(CyberFont.mono(size: 9))
    }

    private func formatDate(_ timestamp: Double) -> String {
        guard timestamp > 0 else { return "" }
        let date = Date(timeIntervalSince1970: timestamp)
        let formatter = DateFormatter()
        formatter.dateFormat = "MM/dd HH:mm"
        return formatter.string(from: date)
    }
}

// MARK: - 脉冲动画

private struct DemoPulseAnimation: ViewModifier {
    @State private var isPulsing = false

    func body(content: Content) -> some View {
        content
            .opacity(isPulsing ? 0.3 : 1.0)
            .animation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true), value: isPulsing)
            .onAppear { isPulsing = true }
    }
}
