import SwiftUI

struct ToolPanelView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @State private var selectedTab = 0
    
    var body: some View {
        VStack(spacing: 0) {
            // Cyber Tab Header
            HStack(spacing: 0) {
                CyberTab(title: "矩阵", icon: "cpu", index: 0, selected: $selectedTab)
                CyberTab(title: "历史", icon: "clock", index: 1, selected: $selectedTab)
                CyberTab(title: "任务", icon: "bolt.fill", index: 2, selected: $selectedTab)
                CyberTab(title: "日志", icon: "terminal", index: 3, selected: $selectedTab)
                CyberTab(title: "快照", icon: "clock.arrow.circlepath", index: 4, selected: $selectedTab)
                CyberTab(title: "演示", icon: "person.badge.plus", index: 5, selected: $selectedTab)
            }
            .padding(.horizontal, 8)
            .padding(.top, 10)
            .padding(.bottom, 6)
            
            Rectangle()
                .fill(CyberColor.border)
                .frame(height: 1)
            
            // Content
            switch selectedTab {
            case 0:
                ToolMatrixView()
            case 1:
                ToolHistoryView()
            case 2:
                AutonomousTaskView()
            case 3:
                ExecutionLogsView()
            case 4:
                RollbackPanelView()
            case 5:
                HumanDemoView()
            default:
                ToolMatrixView()
            }
        }
        .background(CyberColor.bg1)
    }
}

// MARK: - Cyber Tab Button

private struct CyberTab: View {
    let title: String
    let icon: String
    let index: Int
    @Binding var selected: Int
    @State private var isHovering = false
    
    private var isSelected: Bool { selected == index }
    
    var body: some View {
        Button(action: { withAnimation(.easeInOut(duration: 0.2)) { selected = index } }) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(CyberFont.mono(size: 10))
                Text(title)
                    .font(CyberFont.mono(size: 10, weight: .medium))
            }
            .foregroundColor(isSelected ? CyberColor.cyan : CyberColor.textSecond)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(isSelected ? CyberColor.cyan.opacity(0.1) : (isHovering ? CyberColor.bg2 : Color.clear))
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(isSelected ? CyberColor.cyan.opacity(0.4) : Color.clear, lineWidth: 0.5)
            )
            .cornerRadius(4)
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
    }
}

// MARK: - Tool Matrix View (CPU Die Layout)

struct ToolMatrixView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @State private var selectedTool: ToolDefinition? = nil
    
    private var systemTools: [ToolDefinition] {
        viewModel.availableTools.filter { !$0.isGenerated }
    }
    
    private var generatedTools: [ToolDefinition] {
        viewModel.availableTools.filter { $0.isGenerated }
    }
    
    var body: some View {
        if viewModel.availableTools.isEmpty {
            // Loading State
            VStack(spacing: 16) {
                ZStack {
                    // Spinning ring
                    Circle()
                        .stroke(CyberColor.cyan.opacity(0.15), lineWidth: 2)
                        .frame(width: 50, height: 50)
                    
                    ProgressView()
                        .scaleEffect(0.8)
                        .tint(CyberColor.cyan)
                }
                
                Text("LOADING TOOLS...")
                    .font(CyberFont.mono(size: 10, weight: .semibold))
                    .foregroundColor(CyberColor.textSecond)
                    .tracking(2)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView {
                VStack(spacing: 12) {
                    // ── SYSTEM TOOLS Section ──
                    ToolSectionHeader(
                        icon: "cpu",
                        title: "SYSTEM TOOLS",
                        count: systemTools.count,
                        color: CyberColor.cyan
                    )
                    
                    ToolMatrixGrid(
                        tools: systemTools,
                        selectedTool: $selectedTool,
                        accentColor: CyberColor.cyan
                    )
                    
                    // ── GENERATED TOOLS Section ──
                    if !generatedTools.isEmpty {
                        Rectangle()
                            .fill(CyberColor.border)
                            .frame(height: 0.5)
                            .padding(.vertical, 4)
                        
                        ToolSectionHeader(
                            icon: "wand.and.stars",
                            title: "GENERATED",
                            count: generatedTools.count,
                            color: CyberColor.orange
                        )
                        
                        ToolMatrixGrid(
                            tools: generatedTools,
                            selectedTool: $selectedTool,
                            accentColor: CyberColor.orange
                        )
                    }
                }
                .padding(12)
            }
        }
    }
}

// MARK: - Tool Section Header

private struct ToolSectionHeader: View {
    let icon: String
    let title: String
    let count: Int
    var color: Color = CyberColor.cyan
    
    var body: some View {
        HStack {
            Image(systemName: icon)
                .font(CyberFont.mono(size: 10))
                .foregroundColor(color)
            Text(title)
                .font(CyberFont.mono(size: 9, weight: .bold))
                .foregroundColor(color)
                .tracking(2)
            
            Spacer()
            
            Text("\(count) UNITS")
                .font(CyberFont.mono(size: 9))
                .foregroundColor(CyberColor.textSecond)
        }
        .padding(.horizontal, 4)
    }
}

// MARK: - Tool Matrix Grid (reusable for both sections)

private struct ToolMatrixGrid: View {
    let tools: [ToolDefinition]
    @Binding var selectedTool: ToolDefinition?
    var accentColor: Color = CyberColor.cyan
    
    var body: some View {
        let colCount = 3
        let rowCount = (tools.count + colCount - 1) / colCount
        
        ForEach(0..<rowCount, id: \.self) { row in
            let startIdx = row * colCount
            let endIdx = min(startIdx + colCount, tools.count)
            
            // 本行的 cells
            HStack(spacing: 8) {
                ForEach(startIdx..<endIdx, id: \.self) { idx in
                    let tool = tools[idx]
                    ToolMatrixCell(
                        tool: tool,
                        isSelected: selectedTool?.id == tool.id,
                        accentColor: accentColor
                    ) {
                        withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                            selectedTool = selectedTool?.id == tool.id ? nil : tool
                        }
                    }
                }
                // 填充空位确保均匀宽度
                if endIdx - startIdx < colCount {
                    ForEach(0..<(colCount - (endIdx - startIdx)), id: \.self) { _ in
                        Color.clear.frame(maxWidth: .infinity)
                    }
                }
            }
            
            // 如果选中的 tool 在当前行，紧跟在该行下方展开详情
            if let sel = selectedTool,
               let selIdx = tools.firstIndex(where: { $0.id == sel.id }),
               selIdx >= startIdx && selIdx < endIdx {
                ToolDetailPanel(tool: sel, accentColor: accentColor)
                    .transition(.asymmetric(
                        insertion: .scale(scale: 0.95).combined(with: .opacity),
                        removal: .opacity
                    ))
            }
        }
    }
}

// MARK: - Matrix Cell (Chip Die)

private struct ToolMatrixCell: View {
    let tool: ToolDefinition
    let isSelected: Bool
    var accentColor: Color = CyberColor.cyan
    let onTap: () -> Void
    @State private var isHovering = false
    
    private var borderColor: Color {
        isSelected ? accentColor : (isHovering ? accentColor.opacity(0.6) : CyberColor.border)
    }
    
    private var bgColor: Color {
        isSelected ? accentColor.opacity(0.08) : (isHovering ? CyberColor.bgHighlight : CyberColor.bg2)
    }
    
    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 8) {
                // Icon with glow
                ZStack {
                    if isSelected || isHovering {
                        Circle()
                            .fill(accentColor.opacity(0.1))
                            .frame(width: 36, height: 36)
                            .blur(radius: 4)
                    }
                    
                    Image(systemName: iconForTool(tool.name))
                        .font(CyberFont.display(size: 20))
                        .foregroundColor(isSelected ? accentColor : accentColor.opacity(0.6))
                        .shadow(color: isSelected ? accentColor.opacity(0.5) : .clear, radius: 4)
                }
                .frame(height: 32)
                
                // Name
                Text(displayNameForTool(tool.name))
                    .font(CyberFont.mono(size: 9, weight: .medium))
                    .foregroundColor(isSelected ? CyberColor.textPrimary : CyberColor.textSecond)
                    .lineLimit(1)
                
                // Status dot
                Circle()
                    .fill(CyberColor.green)
                    .frame(width: 4, height: 4)
                    .shadow(color: CyberColor.green.opacity(0.5), radius: 2)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .padding(.horizontal, 4)
            .background(bgColor)
            .overlay(
                ZStack {
                    // Main border
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(borderColor, lineWidth: isSelected ? 1.2 : 0.5)
                    
                    // Corner accents (chip pads)
                    CornerPads(color: borderColor, padSize: 4)
                }
            )
            .cornerRadius(6)
            .shadow(color: isSelected ? accentColor.opacity(0.12) : .clear, radius: 6)
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.15)) { isHovering = hovering }
        }
    }
}

// MARK: - Corner Pads (Chip-like decoration)

private struct CornerPads: View {
    let color: Color
    let padSize: CGFloat
    
    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            
            // Top-left corner lines
            Path { p in
                p.move(to: CGPoint(x: 0, y: padSize))
                p.addLine(to: CGPoint(x: 0, y: 0))
                p.addLine(to: CGPoint(x: padSize, y: 0))
            }
            .stroke(color.opacity(0.6), lineWidth: 1.5)
            
            // Top-right
            Path { p in
                p.move(to: CGPoint(x: w - padSize, y: 0))
                p.addLine(to: CGPoint(x: w, y: 0))
                p.addLine(to: CGPoint(x: w, y: padSize))
            }
            .stroke(color.opacity(0.6), lineWidth: 1.5)
            
            // Bottom-left
            Path { p in
                p.move(to: CGPoint(x: 0, y: h - padSize))
                p.addLine(to: CGPoint(x: 0, y: h))
                p.addLine(to: CGPoint(x: padSize, y: h))
            }
            .stroke(color.opacity(0.6), lineWidth: 1.5)
            
            // Bottom-right
            Path { p in
                p.move(to: CGPoint(x: w - padSize, y: h))
                p.addLine(to: CGPoint(x: w, y: h))
                p.addLine(to: CGPoint(x: w, y: h - padSize))
            }
            .stroke(color.opacity(0.6), lineWidth: 1.5)
        }
    }
}

// MARK: - Tool Detail Panel

private struct ToolDetailPanel: View {
    let tool: ToolDefinition
    var accentColor: Color = CyberColor.cyan
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: iconForTool(tool.name))
                    .font(CyberFont.body(size: 14))
                    .foregroundColor(accentColor)
                
                Text(displayNameForTool(tool.name))
                    .font(CyberFont.mono(size: 12, weight: .semibold))
                    .foregroundColor(CyberColor.textPrimary)
                
                Spacer()
                
                Text(tool.isGenerated ? "DYNAMIC" : "ONLINE")
                    .font(CyberFont.mono(size: 8, weight: .bold))
                    .foregroundColor(tool.isGenerated ? CyberColor.orange : CyberColor.green)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background((tool.isGenerated ? CyberColor.orange : CyberColor.green).opacity(0.1))
                    .cornerRadius(3)
            }
            
            Rectangle()
                .fill(CyberColor.border)
                .frame(height: 0.5)
            
            Text(tool.description)
                .font(CyberFont.mono(size: 11))
                .foregroundColor(CyberColor.textSecond)
                .lineSpacing(3)
            
            // Parameter info
            if !tool.parameters.isEmpty {
                Rectangle()
                    .fill(CyberColor.border)
                    .frame(height: 0.5)
                
                HStack(spacing: 4) {
                    Image(systemName: "list.bullet")
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond)
                    Text("参数: \(tool.parameters.count)")
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.textSecond)
                }
            }
        }
        .padding(12)
        .background(CyberColor.bg2)
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(accentColor.opacity(0.25), lineWidth: 0.5)
        )
        .cornerRadius(6)
    }
}

// MARK: - Tool Name/Icon Helpers

private func iconForTool(_ name: String) -> String {
    switch name {
    case "file_operations": return "folder"
    case "terminal": return "terminal"
    case "app_control": return "app.badge"
    case "system_info": return "cpu"
    case "clipboard": return "doc.on.clipboard"
    case "screen_capture": return "camera.viewfinder"
    case "browser": return "globe"
    case "keyboard": return "keyboard"
    case "accessibility": return "accessibility"
    default: return "wrench.and.screwdriver"
    }
}

private func displayNameForTool(_ name: String) -> String {
    switch name {
    case "file_operations": return "文件操作"
    case "terminal": return "终端命令"
    case "app_control": return "应用控制"
    case "system_info": return "系统信息"
    case "clipboard": return "剪贴板"
    case "screen_capture": return "屏幕截图"
    case "browser": return "浏览器"
    case "keyboard": return "键盘输入"
    case "accessibility": return "无障碍"
    default: return name
    }
}

struct ToolHistoryView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    
    var body: some View {
        if viewModel.recentToolCalls.isEmpty {
            VStack(spacing: 12) {
                Image(systemName: "clock")
                    .font(CyberFont.display(size: 40))
                    .foregroundColor(CyberColor.textSecond)
                
                Text("暂无工具调用记录")
                    .foregroundColor(CyberColor.textSecond)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(CyberColor.bg1)
        } else {
            ScrollView {
                LazyVStack(spacing: 2) {
                    ForEach(viewModel.recentToolCalls) { call in
                        ToolCallRow(toolCall: call)
                    }
                }
                .padding(8)
            }
            .background(CyberColor.bg1)
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
                    .font(CyberFont.mono(size: 10, weight: .semibold))
                    .foregroundColor(CyberColor.cyan)
                
                Text(formatArguments(toolCall.arguments))
                    .font(CyberFont.mono(size: 10))
                    .foregroundColor(CyberColor.textSecond)
                
                if let result = toolCall.result {
                    Rectangle()
                        .fill(CyberColor.border)
                        .frame(height: 0.5)
                    
                    HStack {
                        Text("结果:")
                            .font(CyberFont.mono(size: 10, weight: .semibold))
                            .foregroundColor(CyberColor.cyan)
                        
                        Image(systemName: result.success ? "checkmark.circle.fill" : "xmark.circle.fill")
                            .foregroundColor(result.success ? CyberColor.green : CyberColor.red)
                            .font(CyberFont.body(size: 11))
                    }
                    
                    Text(result.output)
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                        .lineLimit(5)
                }
            }
            .padding(.vertical, 4)
            .padding(.horizontal, 8)
        } label: {
            HStack {
                Image(systemName: toolCall.result?.success == true ? "checkmark.circle.fill" : 
                      toolCall.result?.success == false ? "xmark.circle.fill" : "arrow.triangle.2.circlepath")
                    .foregroundColor(toolCall.result?.success == true ? CyberColor.green : 
                                    toolCall.result?.success == false ? CyberColor.red : CyberColor.orange)
                
                Text(toolCall.name)
                    .font(CyberFont.mono(size: 11))
                    .foregroundColor(CyberColor.textPrimary)
            }
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 8)
        .background(CyberColor.bg2)
        .cornerRadius(4)
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
                Rectangle()
                    .fill(CyberColor.border)
                    .frame(height: 1)
            }
            
            // Action Logs
            if viewModel.actionLogs.isEmpty {
                EmptyTaskView()
            } else {
                ActionLogsList(logs: viewModel.actionLogs)
            }
            
            // Clear Button
            if !viewModel.actionLogs.isEmpty {
                Rectangle()
                    .fill(CyberColor.border)
                    .frame(height: 1)
                Button(action: { viewModel.clearActionLogs() }) {
                    Label("清除日志", systemImage: "trash")
                        .font(CyberFont.mono(size: 11))
                        .foregroundColor(CyberColor.red)
                }
                .buttonStyle(.plain)
                .padding()
            }
        }
        .background(CyberColor.bg1)
    }
}

// MARK: - Task Views (used by monitoring dashboard)

struct TaskProgressHeader: View {
    @EnvironmentObject var viewModel: AgentViewModel
    let progress: TaskProgress
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Circle()
                    .fill(statusColor)
                    .frame(width: 10, height: 10)
                    .shadow(color: statusColor.opacity(0.5), radius: 3)
                
                Text(statusText)
                    .font(CyberFont.mono(size: 13, weight: .semibold))
                    .foregroundColor(CyberColor.textPrimary)
                
                Spacer()
                
                Text(progress.formattedDuration)
                    .font(CyberFont.mono(size: 10))
                    .foregroundColor(CyberColor.textSecond)
            }
            
            Text(progress.taskDescription)
                .font(CyberFont.mono(size: 11))
                .foregroundColor(CyberColor.textSecond)
                .lineLimit(2)
            
            // Model Selection Info
            if let modelType = viewModel.selectedModelType {
                HStack(spacing: 8) {
                    Image(systemName: modelType == "local" ? "house.fill" : "cloud.fill")
                        .foregroundColor(modelType == "local" ? CyberColor.green : CyberColor.cyan)
                    
                    Text(modelType == "local" ? "本地模型" : "远程模型")
                        .font(CyberFont.mono(size: 10, weight: .medium))
                        .foregroundColor(CyberColor.textPrimary)
                    
                    if viewModel.taskComplexity > 0 {
                        Text("复杂度: \(viewModel.taskComplexity)/10")
                            .font(CyberFont.mono(size: 9))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(complexityColor.opacity(0.15))
                            .foregroundColor(complexityColor)
                            .cornerRadius(4)
                    }
                    
                    Spacer()
                }
            }
            
            HStack(spacing: 16) {
                CyberStatMini(icon: "number", value: "\(progress.totalActions)", label: "动作", color: CyberColor.cyan)
                CyberStatMini(icon: "checkmark.circle", value: "\(progress.successfulActions)", label: "成功", color: CyberColor.green)
                CyberStatMini(icon: "xmark.circle", value: "\(progress.failedActions)", label: "失败", color: CyberColor.red)
            }
        }
        .padding()
        .background(CyberColor.bg2)
    }
    
    private var complexityColor: Color {
        if viewModel.taskComplexity <= 3 { return CyberColor.green }
        else if viewModel.taskComplexity <= 6 { return CyberColor.orange }
        else { return CyberColor.red }
    }
    
    private var statusColor: Color {
        switch progress.status {
        case .running: return CyberColor.orange
        case .completed: return CyberColor.green
        case .failed: return CyberColor.red
        }
    }
    
    private var statusText: String {
        switch progress.status {
        case .running: return "EXECUTING..."
        case .completed: return "COMPLETED"
        case .failed: return "FAILED"
        }
    }
}

private struct CyberStatMini: View {
    let icon: String
    let value: String
    let label: String
    var color: Color = CyberColor.cyan
    
    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(CyberFont.mono(size: 9))
                .foregroundColor(color)
            Text(value)
                .font(CyberFont.mono(size: 10, weight: .semibold))
                .foregroundColor(color)
        }
    }
}

struct EmptyTaskView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "bolt.circle")
                .font(CyberFont.display(size: 40))
                .foregroundColor(CyberColor.cyanDim)
            
            Text("AUTONOMOUS MODE")
                .font(CyberFont.mono(size: 11, weight: .bold))
                .foregroundColor(CyberColor.textPrimary)
                .tracking(2)
            
            Text("在聊天框输入任务后点击 🤖 按钮\n自动选择本地/远程模型执行")
                .font(CyberFont.mono(size: 10))
                .foregroundColor(CyberColor.textSecond)
                .multilineTextAlignment(.center)
                .lineSpacing(3)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
        .background(CyberColor.bg1)
    }
}

struct ActionLogsList: View {
    let logs: [ActionLogEntry]
    
    var body: some View {
        VStack(spacing: 0) {
            // Toolbar
            HStack {
                HStack(spacing: 4) {
                    Image(systemName: "list.bullet.rectangle")
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.cyan)
                    Text("EXECUTION LOG")
                        .font(CyberFont.mono(size: 9, weight: .bold))
                        .foregroundColor(CyberColor.cyan)
                        .tracking(1)
                }
                
                Spacer()
                
                Button(action: copyAllLogs) {
                    Label("复制", systemImage: "doc.on.doc")
                        .font(CyberFont.mono(size: 9))
                }
                .buttonStyle(.plain)
                .foregroundColor(CyberColor.cyanDim)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(CyberColor.bg2)
            
            Rectangle()
                .fill(CyberColor.border)
                .frame(height: 0.5)
            
            // Log TextView
            ScrollViewReader { proxy in
                ScrollView {
                    Text(formattedLogs)
                        .font(CyberFont.mono(size: 11))
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
            .background(CyberColor.bg0)
        }
    }
    
    private var formattedLogs: AttributedString {
        var result = AttributedString()
        
        for log in logs {
            var header = AttributedString()
            let statusSymbol: String
            let statusColor: Color
            
            switch log.status {
            case .pending:
                statusSymbol = "◇"
                statusColor = CyberColor.textSecond
            case .executing:
                statusSymbol = "◈"
                statusColor = CyberColor.orange
            case .success:
                statusSymbol = "◆"
                statusColor = CyberColor.green
            case .failed:
                statusSymbol = "✕"
                statusColor = CyberColor.red
            }
            
            header = AttributedString("\(statusSymbol) [\(log.iteration)] \(log.actionType)\n")
            header.foregroundColor = statusColor
            result.append(header)
            
            var reasoning = AttributedString("  ← \(log.reasoning)\n")
            reasoning.foregroundColor = CyberColor.textSecond
            result.append(reasoning)
            
            if let output = log.output, !output.isEmpty {
                var outputLine = AttributedString("  → \(output.prefix(200))\(output.count > 200 ? "..." : "")\n")
                outputLine.foregroundColor = CyberColor.textPrimary
                result.append(outputLine)
            }
            
            if let error = log.error {
                var errorLine = AttributedString("  ✕ \(error)\n")
                errorLine.foregroundColor = CyberColor.red
                result.append(errorLine)
            }
            
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
                HStack(spacing: 4) {
                    Image(systemName: "terminal")
                        .font(CyberFont.mono(size: 9))
                        .foregroundColor(CyberColor.cyan)
                    Text("RUNTIME LOG")
                        .font(CyberFont.mono(size: 9, weight: .bold))
                        .foregroundColor(CyberColor.cyan)
                        .tracking(1)
                }
                
                Spacer()
                
                if !viewModel.executionLogs.isEmpty {
                    Button(action: { viewModel.clearExecutionLogs() }) {
                        Label("清空", systemImage: "trash")
                            .font(CyberFont.mono(size: 9))
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(CyberColor.textSecond)
                    
                    Button(action: copyAllLogs) {
                        Label("复制", systemImage: "doc.on.doc")
                            .font(CyberFont.mono(size: 9))
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(CyberColor.cyanDim)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(CyberColor.bg2)
            
            Rectangle()
                .fill(CyberColor.border)
                .frame(height: 0.5)
            
            if viewModel.executionLogs.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "terminal")
                        .font(CyberFont.display(size: 36))
                        .foregroundColor(CyberColor.cyanDim)
                    Text("工具执行时，实时日志将显示在此")
                        .font(CyberFont.mono(size: 10))
                        .foregroundColor(CyberColor.textSecond)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(CyberColor.bg1)
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 2) {
                            ForEach(viewModel.executionLogs) { log in
                                HStack(alignment: .top, spacing: 6) {
                                    Text(formatTime(log.timestamp))
                                        .font(CyberFont.mono(size: 10))
                                        .foregroundColor(CyberColor.textSecond)
                                    
                                    Text("[\(log.level.uppercased())]")
                                        .font(CyberFont.mono(size: 10))
                                        .foregroundColor(colorForLevel(log.level))
                                    
                                    if !log.toolName.isEmpty {
                                        Text("\(log.toolName):")
                                            .font(CyberFont.mono(size: 10))
                                            .foregroundColor(CyberColor.cyan)
                                    }
                                    
                                    Text(log.message)
                                        .font(CyberFont.mono(size: 11))
                                        .foregroundColor(CyberColor.textPrimary)
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
                .background(CyberColor.bg0)
            }
        }
        .background(CyberColor.bg1)
    }
    
    private func formatTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        return formatter.string(from: date)
    }
    
    private func colorForLevel(_ level: String) -> Color {
        switch level.lowercased() {
        case "error": return CyberColor.red
        case "warning": return CyberColor.orange
        case "info": return CyberColor.cyan
        case "debug": return CyberColor.textSecond
        default: return CyberColor.textSecond
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
