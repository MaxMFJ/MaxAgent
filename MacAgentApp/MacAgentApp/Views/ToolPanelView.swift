import SwiftUI

struct ToolPanelView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @State private var selectedTab = 0
    
    var body: some View {
        VStack(spacing: 0) {
            // Tab Header
            Picker("", selection: $selectedTab) {
                Text("工具").tag(0)
                Text("历史").tag(1)
                Text("任务").tag(2)
                Text("执行日志").tag(3)
            }
            .pickerStyle(.segmented)
            .padding()
            
            Divider()
            
            // Content
            switch selectedTab {
            case 0:
                ToolsListView()
            case 1:
                ToolHistoryView()
            case 2:
                AutonomousTaskView()
            case 3:
                ExecutionLogsView()
            default:
                ToolsListView()
            }
        }
    }
}

struct ToolsListView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    
    var body: some View {
        if viewModel.availableTools.isEmpty {
            VStack(spacing: 12) {
                Image(systemName: "wrench.and.screwdriver")
                    .font(.system(size: 40))
                    .foregroundColor(.secondary)
                
                Text("加载工具中...")
                    .foregroundColor(.secondary)
                
                ProgressView()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            List {
                ForEach(viewModel.availableTools) { tool in
                    ToolRow(tool: tool)
                }
            }
            .listStyle(.inset)
        }
    }
}

struct ToolRow: View {
    let tool: ToolDefinition
    @State private var isExpanded = false
    
    var body: some View {
        DisclosureGroup(isExpanded: $isExpanded) {
            Text(tool.description)
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(.vertical, 4)
        } label: {
            HStack {
                Image(systemName: iconForTool(tool.name))
                    .foregroundColor(.accentColor)
                    .frame(width: 24)
                
                Text(displayNameForTool(tool.name))
                    .font(.body)
            }
        }
    }
    
    private func iconForTool(_ name: String) -> String {
        switch name {
        case "file_operations": return "folder"
        case "terminal": return "terminal"
        case "app_control": return "app.badge"
        case "system_info": return "cpu"
        case "clipboard": return "doc.on.clipboard"
        default: return "wrench"
        }
    }
    
    private func displayNameForTool(_ name: String) -> String {
        switch name {
        case "file_operations": return "文件操作"
        case "terminal": return "终端命令"
        case "app_control": return "应用控制"
        case "system_info": return "系统信息"
        case "clipboard": return "剪贴板"
        default: return name
        }
    }
}

struct ToolHistoryView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    
    var body: some View {
        if viewModel.recentToolCalls.isEmpty {
            VStack(spacing: 12) {
                Image(systemName: "clock")
                    .font(.system(size: 40))
                    .foregroundColor(.secondary)
                
                Text("暂无工具调用记录")
                    .foregroundColor(.secondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            List {
                ForEach(viewModel.recentToolCalls) { call in
                    ToolCallRow(toolCall: call)
                }
            }
            .listStyle(.inset)
        }
    }
}

struct ToolCallRow: View {
    let toolCall: ToolCall
    @State private var isExpanded = false
    
    var body: some View {
        DisclosureGroup(isExpanded: $isExpanded) {
            VStack(alignment: .leading, spacing: 8) {
                Text("参数:")
                    .font(.caption)
                    .fontWeight(.semibold)
                
                Text(formatArguments(toolCall.arguments))
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                if let result = toolCall.result {
                    Divider()
                    
                    HStack {
                        Text("结果:")
                            .font(.caption)
                            .fontWeight(.semibold)
                        
                        Image(systemName: result.success ? "checkmark.circle.fill" : "xmark.circle.fill")
                            .foregroundColor(result.success ? .green : .red)
                            .font(.caption)
                    }
                    
                    Text(result.output)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(5)
                }
            }
            .padding(.vertical, 4)
        } label: {
            HStack {
                Image(systemName: toolCall.result?.success == true ? "checkmark.circle.fill" : 
                      toolCall.result?.success == false ? "xmark.circle.fill" : "arrow.triangle.2.circlepath")
                    .foregroundColor(toolCall.result?.success == true ? .green : 
                                    toolCall.result?.success == false ? .red : .orange)
                
                Text(toolCall.name)
                    .font(.body)
            }
        }
    }
    
    private func formatArguments(_ args: [String: AnyCodable]) -> String {
        let pairs = args.map { "\($0.key): \($0.value.value)" }
        return pairs.joined(separator: "\n")
    }
}

// MARK: - Autonomous Task View

struct AutonomousTaskView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    
    var body: some View {
        VStack(spacing: 0) {
            // Task Progress Header
            if let progress = viewModel.taskProgress {
                TaskProgressHeader(progress: progress)
                    .environmentObject(viewModel)
                Divider()
            }
            
            // Action Logs
            if viewModel.actionLogs.isEmpty {
                EmptyTaskView()
            } else {
                ActionLogsList(logs: viewModel.actionLogs)
            }
            
            // Clear Button
            if !viewModel.actionLogs.isEmpty {
                Divider()
                Button(action: { viewModel.clearActionLogs() }) {
                    Label("清除日志", systemImage: "trash")
                        .foregroundColor(.red)
                }
                .buttonStyle(.plain)
                .padding()
            }
        }
    }
}

struct TaskProgressHeader: View {
    @EnvironmentObject var viewModel: AgentViewModel
    let progress: TaskProgress
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Circle()
                    .fill(statusColor)
                    .frame(width: 10, height: 10)
                
                Text(statusText)
                    .font(.headline)
                
                Spacer()
                
                Text(progress.formattedDuration)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            Text(progress.taskDescription)
                .font(.caption)
                .foregroundColor(.secondary)
                .lineLimit(2)
            
            // Model Selection Info
            if let modelType = viewModel.selectedModelType {
                HStack(spacing: 8) {
                    Image(systemName: modelType == "local" ? "house.fill" : "cloud.fill")
                        .foregroundColor(modelType == "local" ? .green : .blue)
                    
                    Text(modelType == "local" ? "本地模型" : "远程模型")
                        .font(.caption)
                        .fontWeight(.medium)
                    
                    if viewModel.taskComplexity > 0 {
                        Text("复杂度: \(viewModel.taskComplexity)/10")
                            .font(.caption2)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(complexityColor.opacity(0.2))
                            .foregroundColor(complexityColor)
                            .cornerRadius(4)
                    }
                    
                    Spacer()
                }
            }
            
            HStack(spacing: 16) {
                StatBadge(icon: "number", value: "\(progress.totalActions)", label: "动作")
                StatBadge(icon: "checkmark.circle", value: "\(progress.successfulActions)", label: "成功")
                StatBadge(icon: "xmark.circle", value: "\(progress.failedActions)", label: "失败")
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
    }
    
    private var complexityColor: Color {
        if viewModel.taskComplexity <= 3 {
            return .green
        } else if viewModel.taskComplexity <= 6 {
            return .orange
        } else {
            return .red
        }
    }
    
    private var statusColor: Color {
        switch progress.status {
        case .running: return .orange
        case .completed: return .green
        case .failed: return .red
        }
    }
    
    private var statusText: String {
        switch progress.status {
        case .running: return "执行中..."
        case .completed: return "已完成"
        case .failed: return "失败"
        }
    }
}

struct StatBadge: View {
    let icon: String
    let value: String
    let label: String
    
    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption2)
            Text(value)
                .font(.caption)
                .fontWeight(.semibold)
        }
        .foregroundColor(.secondary)
    }
}

struct EmptyTaskView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "robot")
                .font(.system(size: 40))
                .foregroundColor(.secondary)
            
            Text("自主执行")
                .font(.headline)
            
            Text("在聊天框输入任务后点击 🤖 按钮\n自动选择本地/远程模型执行")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}

struct ActionLogsList: View {
    let logs: [ActionLogEntry]
    
    var body: some View {
        VStack(spacing: 0) {
            // Toolbar
            HStack {
                Text("执行日志")
                    .font(.caption)
                    .fontWeight(.semibold)
                    .foregroundColor(.secondary)
                
                Spacer()
                
                Button(action: copyAllLogs) {
                    Label("复制全部", systemImage: "doc.on.doc")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .foregroundColor(.accentColor)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color(NSColor.controlBackgroundColor))
            
            Divider()
            
            // Log TextView
            ScrollViewReader { proxy in
                ScrollView {
                    Text(formattedLogs)
                        .font(.system(.caption, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                        .id("logContent")
                }
                .onChange(of: logs.count) { _, _ in
                    withAnimation {
                        proxy.scrollTo("logContent", anchor: .bottom)
                    }
                }
            }
            .background(Color(NSColor.textBackgroundColor))
        }
    }
    
    private var formattedLogs: AttributedString {
        var result = AttributedString()
        
        for log in logs {
            // Status icon and action type
            var header = AttributedString()
            let statusSymbol: String
            let statusColor: Color
            
            switch log.status {
            case .pending:
                statusSymbol = "⏳"
                statusColor = .secondary
            case .executing:
                statusSymbol = "🔄"
                statusColor = .orange
            case .success:
                statusSymbol = "✅"
                statusColor = .green
            case .failed:
                statusSymbol = "❌"
                statusColor = .red
            }
            
            header = AttributedString("\(statusSymbol) [\(log.iteration)] \(log.actionType)\n")
            header.foregroundColor = statusColor
            result.append(header)
            
            // Reasoning
            var reasoning = AttributedString("   原因: \(log.reasoning)\n")
            reasoning.foregroundColor = .secondary
            result.append(reasoning)
            
            // Output
            if let output = log.output, !output.isEmpty {
                var outputLine = AttributedString("   输出: \(output.prefix(200))\(output.count > 200 ? "..." : "")\n")
                outputLine.foregroundColor = .primary
                result.append(outputLine)
            }
            
            // Error
            if let error = log.error {
                var errorLine = AttributedString("   错误: \(error)\n")
                errorLine.foregroundColor = .red
                result.append(errorLine)
            }
            
            // Separator
            result.append(AttributedString("\n"))
        }
        
        return result
    }
    
    private func copyAllLogs() {
        var text = ""
        for log in logs {
            let statusSymbol: String
            switch log.status {
            case .pending: statusSymbol = "[待执行]"
            case .executing: statusSymbol = "[执行中]"
            case .success: statusSymbol = "[成功]"
            case .failed: statusSymbol = "[失败]"
            }
            
            text += "\(statusSymbol) 步骤 \(log.iteration): \(log.actionType)\n"
            text += "  原因: \(log.reasoning)\n"
            
            if let output = log.output, !output.isEmpty {
                text += "  输出: \(output)\n"
            }
            
            if let error = log.error {
                text += "  错误: \(error)\n"
            }
            
            text += "\n"
        }
        
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}

// MARK: - Execution Logs View

struct ExecutionLogsView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("工具执行日志")
                    .font(.caption)
                    .fontWeight(.semibold)
                    .foregroundColor(.secondary)
                
                Spacer()
                
                if !viewModel.executionLogs.isEmpty {
                    Button(action: { viewModel.clearExecutionLogs() }) {
                        Label("清空", systemImage: "trash")
                            .font(.caption)
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(.secondary)
                    
                    Button(action: copyAllLogs) {
                        Label("复制全部", systemImage: "doc.on.doc")
                            .font(.caption)
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(.accentColor)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color(NSColor.controlBackgroundColor))
            
            Divider()
            
            if viewModel.executionLogs.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "terminal")
                        .font(.system(size: 36))
                        .foregroundColor(.secondary)
                    Text("工具执行时，实时日志将显示在此")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 2) {
                            ForEach(viewModel.executionLogs) { log in
                                HStack(alignment: .top, spacing: 6) {
                                    Text(formatTime(log.timestamp))
                                        .font(.system(.caption2, design: .monospaced))
                                        .foregroundColor(.secondary)
                                    
                                    Text("[\(log.level.uppercased())]")
                                        .font(.system(.caption2, design: .monospaced))
                                        .foregroundColor(colorForLevel(log.level))
                                    
                                    if !log.toolName.isEmpty {
                                        Text("\(log.toolName):")
                                            .font(.system(.caption2, design: .monospaced))
                                            .foregroundColor(.accentColor)
                                    }
                                    
                                    Text(log.message)
                                        .font(.system(.caption, design: .monospaced))
                                        .foregroundColor(.primary)
                                        .textSelection(.enabled)
                                }
                                .id(log.id)
                            }
                        }
                        .padding(12)
                    }
                    .onChange(of: viewModel.executionLogs.count) { _, _ in
                        if let last = viewModel.executionLogs.last {
                            withAnimation {
                                proxy.scrollTo(last.id, anchor: .bottom)
                            }
                        }
                    }
                }
                .background(Color(NSColor.textBackgroundColor))
            }
        }
    }
    
    private func formatTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        return formatter.string(from: date)
    }
    
    private func colorForLevel(_ level: String) -> Color {
        switch level.lowercased() {
        case "error": return .red
        case "warning": return .orange
        case "info": return .blue
        case "debug": return .secondary
        default: return .secondary
        }
    }
    
    private func copyAllLogs() {
        let text = viewModel.executionLogs.map { log in
            "[\(formatTime(log.timestamp))] [\(log.level.uppercased())] \(log.toolName): \(log.message)"
        }.joined(separator: "\n")
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}

#Preview {
    ToolPanelView()
        .environmentObject(AgentViewModel())
        .frame(width: 300)
}
