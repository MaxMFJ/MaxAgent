import SwiftUI

/// 定时任务管理页 — 对应 ScheduledTaskService 后端
struct ScheduledTasksSettingsContent: View {
    @EnvironmentObject var viewModel: AgentViewModel

    @State private var showCreateSheet = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("定时任务 (Scheduled Tasks)")
                        .font(CyberFont.body(size: 14, weight: .semibold))
                    Text("管理定时/周期任务，支持 interval 与 cron 两种触发方式。")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                }
                Spacer()
                Button {
                    showCreateSheet = true
                } label: {
                    Label("新建", systemImage: "plus.circle")
                }
                .buttonStyle(.plain)
                .foregroundColor(CyberColor.cyan)

                Button {
                    Task { await viewModel.loadScheduledTasks() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .disabled(viewModel.isLoadingScheduledTasks)
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)

            if viewModel.isLoadingScheduledTasks {
                ProgressView("加载中…").frame(maxWidth: .infinity).padding()
            } else if viewModel.scheduledTasks.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "clock.badge.questionmark")
                        .font(.system(size: 32))
                        .foregroundColor(.secondary)
                    Text("暂无定时任务")
                        .foregroundColor(.secondary)
                        .font(CyberFont.body(size: 12))
                    Text("点击「新建」创建第一个定时任务")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary.opacity(0.7))
                }
                .frame(maxWidth: .infinity)
                .padding(40)
            } else {
                ForEach(Array(viewModel.scheduledTasks.enumerated()), id: \.offset) { _, task in
                    ScheduledTaskRow(task: task)
                        .environmentObject(viewModel)
                }
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear {
            Task { await viewModel.loadScheduledTasks() }
        }
        .sheet(isPresented: $showCreateSheet) {
            CreateScheduledTaskSheet()
                .environmentObject(viewModel)
        }
    }
}

// MARK: - Task Row

private struct ScheduledTaskRow: View {
    @EnvironmentObject var viewModel: AgentViewModel
    let task: [String: Any]

    private var taskId: String { task["task_id"] as? String ?? "" }
    private var desc: String { task["description"] as? String ?? "无描述" }
    private var triggerType: String { task["trigger_type"] as? String ?? "" }
    private var status: String { task["status"] as? String ?? "unknown" }
    private var runCount: Int { task["run_count"] as? Int ?? 0 }
    private var lastRun: String? { task["last_run_at"] as? String }
    private var nextRun: String? { task["next_run_at"] as? String }
    private var lastError: String? { task["last_error"] as? String }

    private var triggerDesc: String {
        guard let cfg = task["trigger_config"] as? [String: Any] else { return triggerType }
        if triggerType == "interval" {
            let secs = cfg["every_seconds"] as? Int ?? 0
            if secs >= 3600 { return "每 \(secs / 3600) 小时" }
            return "每 \(secs / 60) 分钟"
        } else {
            let hour = cfg["hour"] as? Int ?? 0
            let minute = cfg["minute"] as? Int ?? 0
            return "每日 \(String(format: "%02d:%02d", hour, minute))"
        }
    }

    private var statusColor: Color {
        switch status {
        case "active": return .green
        case "paused": return .orange
        default: return .gray
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Status indicator
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)
                .padding(.top, 5)

            VStack(alignment: .leading, spacing: 4) {
                Text(desc)
                    .font(CyberFont.body(size: 12, weight: .medium))
                    .lineLimit(2)

                HStack(spacing: 12) {
                    Label(triggerDesc, systemImage: triggerType == "interval" ? "repeat" : "calendar.badge.clock")
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(.secondary)

                    Text("运行 \(runCount) 次")
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(.secondary)

                    if let next = nextRun {
                        Text("下次: \(formatTime(next))")
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(.secondary)
                    }
                }

                if let err = lastError, !err.isEmpty {
                    Text("❌ \(err)")
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(.red)
                        .lineLimit(1)
                }
            }

            Spacer()

            // Action buttons
            HStack(spacing: 6) {
                if status == "active" {
                    Button {
                        Task { await viewModel.pauseScheduledTask(taskId: taskId) }
                    } label: {
                        Image(systemName: "pause.circle")
                            .foregroundColor(.orange)
                    }
                    .buttonStyle(.plain)
                    .help("暂停")
                } else {
                    Button {
                        Task { await viewModel.resumeScheduledTask(taskId: taskId) }
                    } label: {
                        Image(systemName: "play.circle")
                            .foregroundColor(.green)
                    }
                    .buttonStyle(.plain)
                    .help("恢复")
                }

                Button {
                    Task { await viewModel.deleteScheduledTask(taskId: taskId) }
                } label: {
                    Image(systemName: "trash")
                        .foregroundColor(.red.opacity(0.8))
                }
                .buttonStyle(.plain)
                .help("删除")
            }
        }
        .padding(10)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
    }

    private func formatTime(_ iso: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = formatter.date(from: iso) else { return iso.prefix(16).description }
        let display = DateFormatter()
        display.dateFormat = "MM-dd HH:mm"
        return display.string(from: date)
    }
}

// MARK: - Create Sheet

private struct CreateScheduledTaskSheet: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @Environment(\.dismiss) var dismiss

    @State private var description = ""
    @State private var triggerType = "interval"
    @State private var intervalMinutes: Int = 60
    @State private var cronHour: Int = 8
    @State private var cronMinute: Int = 0

    var body: some View {
        VStack(spacing: 16) {
            Text("新建定时任务")
                .font(CyberFont.body(size: 14, weight: .semibold))

            VStack(alignment: .leading, spacing: 8) {
                Text("任务描述")
                    .font(CyberFont.body(size: 11, weight: .medium))
                TextField("例如：每小时检查系统状态", text: $description)
                    .textFieldStyle(.roundedBorder)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("触发方式")
                    .font(CyberFont.body(size: 11, weight: .medium))
                Picker("", selection: $triggerType) {
                    Text("间隔").tag("interval")
                    Text("定时 (Cron)").tag("cron")
                }
                .pickerStyle(.segmented)
            }

            if triggerType == "interval" {
                HStack {
                    Text("执行间隔")
                        .font(CyberFont.body(size: 11, weight: .medium))
                    Stepper(value: $intervalMinutes, in: 1...1440, step: 5) {
                        Text("\(intervalMinutes) 分钟")
                            .font(CyberFont.body(size: 12))
                    }
                }
            } else {
                HStack(spacing: 16) {
                    HStack {
                        Text("时")
                            .font(CyberFont.body(size: 11))
                        Picker("", selection: $cronHour) {
                            ForEach(0..<24, id: \.self) { h in
                                Text(String(format: "%02d", h)).tag(h)
                            }
                        }
                        .frame(width: 70)
                    }
                    HStack {
                        Text("分")
                            .font(CyberFont.body(size: 11))
                        Picker("", selection: $cronMinute) {
                            ForEach(0..<60, id: \.self) { m in
                                Text(String(format: "%02d", m)).tag(m)
                            }
                        }
                        .frame(width: 70)
                    }
                }
            }

            HStack {
                Button("取消") { dismiss() }
                Spacer()
                Button("创建") {
                    let config: [String: Any]
                    if triggerType == "interval" {
                        config = ["every_seconds": intervalMinutes * 60]
                    } else {
                        config = ["hour": cronHour, "minute": cronMinute]
                    }
                    Task {
                        await viewModel.createScheduledTask(
                            description: description,
                            triggerType: triggerType,
                            triggerConfig: config
                        )
                        dismiss()
                    }
                }
                .disabled(description.trimmingCharacters(in: .whitespaces).isEmpty)
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(20)
        .frame(width: 400)
    }
}
