import SwiftUI

// MARK: - 录制管理视图（ToolPanel 第6个 Tab）

struct RecordingManagementView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @StateObject private var recordingService = RecordingService()
    @State private var newRecordingName: String = ""
    @State private var showNameInput: Bool = false
    @State private var selectedRecording: RecordingSummary?
    @State private var replaySpeed: Double = 1.0
    @State private var isReplaying: Bool = false
    @State private var replayResult: ReplayResult?

    var body: some View {
        VStack(spacing: 0) {
            // 顶部：录制控制区
            recordingControlBar
            
            Rectangle()
                .fill(CyberColor.border)
                .frame(height: 1)

            // 录制列表
            if recordingService.isLoading {
                Spacer()
                ProgressView()
                    .tint(CyberColor.cyan)
                Spacer()
            } else if recordingService.recordings.isEmpty {
                emptyStateView
            } else {
                recordingListView
            }
        }
        .onAppear {
            recordingService.updateBaseURL("http://127.0.0.1:\(PortConfiguration.shared.backendPort)")
            Task {
                await recordingService.checkRecordingStatus()
                await recordingService.fetchRecordings()
                if recordingService.isRecording {
                    recordingService.startStatusPolling()
                }
            }
        }
        .onDisappear {
            // 切换 Tab 时不停止轮询，录制可能仍在进行
        }
    }

    // MARK: - 录制控制栏

    private var recordingControlBar: some View {
        VStack(spacing: 8) {
            if recordingService.isRecording {
                // 正在录制
                HStack(spacing: 8) {
                    Circle()
                        .fill(CyberColor.red)
                        .frame(width: 8, height: 8)
                        .modifier(PulseAnimation())

                    Text("录制中")
                        .font(CyberFont.mono(size: 11, weight: .semibold))
                        .foregroundColor(CyberColor.red)

                    Text(recordingService.activeRecordingName)
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                        .lineLimit(1)

                    Spacer()

                    Text("\(recordingService.activeActionCount) 步")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.cyan)

                    Button(action: {
                        Task { await recordingService.stopRecording() }
                    }) {
                        HStack(spacing: 4) {
                            Image(systemName: "stop.fill")
                                .font(.system(size: 9))
                            Text("停止")
                                .font(CyberFont.mono(size: 10, weight: .medium))
                        }
                        .foregroundColor(CyberColor.red)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(CyberColor.red.opacity(0.15))
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(CyberColor.red.opacity(0.4), lineWidth: 0.5)
                        )
                    }
                    .buttonStyle(.plain)
                }
            } else if showNameInput {
                // 输入名称
                HStack(spacing: 8) {
                    TextField("操作名称...", text: $newRecordingName)
                        .font(CyberFont.mono(size: 11))
                        .textFieldStyle(.plain)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 5)
                        .background(CyberColor.bg0)
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(CyberColor.cyan.opacity(0.3), lineWidth: 0.5)
                        )
                        .onSubmit { startRecording() }

                    Button(action: { startRecording() }) {
                        Image(systemName: "checkmark")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(CyberColor.green)
                    }
                    .buttonStyle(.plain)
                    .disabled(newRecordingName.trimmingCharacters(in: .whitespaces).isEmpty)

                    Button(action: { showNameInput = false; newRecordingName = "" }) {
                        Image(systemName: "xmark")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(CyberColor.textSecond)
                    }
                    .buttonStyle(.plain)
                }
            } else {
                // 默认：开始录制按钮
                HStack {
                    Button(action: { showNameInput = true }) {
                        HStack(spacing: 6) {
                            Image(systemName: "record.circle")
                                .font(.system(size: 12))
                            Text("开始录制")
                                .font(CyberFont.mono(size: 11, weight: .medium))
                        }
                        .foregroundColor(CyberColor.cyan)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                        .background(CyberColor.cyan.opacity(0.1))
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(CyberColor.cyan.opacity(0.3), lineWidth: 0.5)
                        )
                    }
                    .buttonStyle(.plain)

                    Spacer()

                    Button(action: {
                        Task { await recordingService.fetchRecordings() }
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
            Image(systemName: "record.circle")
                .font(.system(size: 32))
                .foregroundColor(CyberColor.textSecond.opacity(0.4))
            Text("暂无录制")
                .font(CyberFont.mono(size: 12))
                .foregroundColor(CyberColor.textSecond)
            Text("点击「开始录制」后，Agent 执行的\nGUI 和输入操作会自动记录")
                .font(CyberFont.mono(size: 10))
                .foregroundColor(CyberColor.textSecond.opacity(0.6))
                .multilineTextAlignment(.center)
            Spacer()
        }
    }

    // MARK: - 录制列表

    private var recordingListView: some View {
        ScrollView {
            LazyVStack(spacing: 6) {
                ForEach(recordingService.recordings) { rec in
                    RecordingRowView(
                        recording: rec,
                        isSelected: selectedRecording?.id == rec.id,
                        isReplaying: isReplaying && selectedRecording?.id == rec.id,
                        onSelect: { selectedRecording = (selectedRecording?.id == rec.id) ? nil : rec },
                        onReplay: { replayRecording(rec) },
                        onDelete: { Task { await recordingService.deleteRecording(id: rec.id) } }
                    )
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 8)
        }
    }

    // MARK: - Actions

    private func startRecording() {
        let name = newRecordingName.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        showNameInput = false
        Task {
            await recordingService.startRecording(name: name)
            newRecordingName = ""
        }
    }

    private func replayRecording(_ rec: RecordingSummary) {
        selectedRecording = rec
        isReplaying = true
        Task {
            let result = await recordingService.replayRecording(id: rec.id, speed: replaySpeed)
            replayResult = result
            isReplaying = false
        }
    }
}

// MARK: - 录制行

private struct RecordingRowView: View {
    let recording: RecordingSummary
    let isSelected: Bool
    let isReplaying: Bool
    let onSelect: () -> Void
    let onReplay: () -> Void
    let onDelete: () -> Void

    @State private var isHovering = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // 主行
            HStack(spacing: 8) {
                Image(systemName: "play.rectangle.fill")
                    .font(.system(size: 12))
                    .foregroundColor(CyberColor.cyan.opacity(0.7))

                VStack(alignment: .leading, spacing: 2) {
                    Text(recording.name)
                        .font(CyberFont.mono(size: 11, weight: .medium))
                        .foregroundColor(CyberColor.textPrimary)
                        .lineLimit(1)

                    HStack(spacing: 8) {
                        Text("\(recording.action_count) 步")
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(CyberColor.cyan.opacity(0.7))

                        Text(formatDate(recording.created_at))
                            .font(CyberFont.mono(size: 9))
                            .foregroundColor(CyberColor.textSecond.opacity(0.6))
                    }
                }

                Spacer()

                if isReplaying {
                    ProgressView()
                        .scaleEffect(0.6)
                        .tint(CyberColor.cyan)
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

                    Button(action: onReplay) {
                        HStack(spacing: 4) {
                            Image(systemName: "play.fill")
                                .font(.system(size: 9))
                            Text("回放")
                                .font(CyberFont.mono(size: 10))
                        }
                        .foregroundColor(CyberColor.green)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(CyberColor.green.opacity(0.1))
                        .cornerRadius(3)
                    }
                    .buttonStyle(.plain)
                    .disabled(isReplaying)

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
                .fill(isSelected ? CyberColor.cyan.opacity(0.08) : (isHovering ? CyberColor.bgHighlight : CyberColor.bg1))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(isSelected ? CyberColor.cyan.opacity(0.3) : Color.clear, lineWidth: 0.5)
        )
        .onHover { isHovering = $0 }
        .animation(.easeInOut(duration: 0.15), value: isSelected)
    }

    private func formatDate(_ timestamp: Double) -> String {
        let date = Date(timeIntervalSince1970: timestamp)
        let formatter = DateFormatter()
        formatter.dateFormat = "MM/dd HH:mm"
        return formatter.string(from: date)
    }
}

// MARK: - 脉冲动画

private struct PulseAnimation: ViewModifier {
    @State private var isPulsing = false

    func body(content: Content) -> some View {
        content
            .opacity(isPulsing ? 0.3 : 1.0)
            .animation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true), value: isPulsing)
            .onAppear { isPulsing = true }
    }
}
