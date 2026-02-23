import SwiftUI

struct ServiceManagerView: View {
    @StateObject private var processManager = ProcessManager.shared
    @State private var selectedTab = 0
    
    var body: some View {
        VStack(spacing: 0) {
            // 服务状态卡片
            HStack(spacing: 16) {
                ServiceCard(
                    title: "后端服务",
                    isRunning: processManager.isBackendRunning,
                    onStart: { processManager.startBackend() },
                    onStop: { processManager.stopBackend() }
                )
                
                ServiceCard(
                    title: "Ollama",
                    isRunning: processManager.isOllamaRunning,
                    onStart: { processManager.startOllama() },
                    onStop: { processManager.stopOllama() }
                )
            }
            .padding()
            
            Divider()
            
            // 日志标签页
            Picker("日志", selection: $selectedTab) {
                Text("后端日志").tag(0)
                Text("Ollama 日志").tag(1)
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .padding(.vertical, 8)
            
            // 日志内容
            LogView(
                logs: selectedTab == 0 ? processManager.backendLogs : processManager.ollamaLogs,
                onClear: {
                    processManager.clearLogs(for: selectedTab == 0 ? "backend" : "ollama")
                }
            )
        }
        .onAppear {
            processManager.checkServicesStatus()
        }
    }
}

struct ServiceCard: View {
    let title: String
    let isRunning: Bool
    let onStart: () -> Void
    let onStop: () -> Void
    
    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Circle()
                    .fill(isRunning ? Color.green : Color.red)
                    .frame(width: 10, height: 10)
                
                Text(title)
                    .font(.headline)
                
                Spacer()
            }
            
            Text(isRunning ? "运行中" : "已停止")
                .font(.caption)
                .foregroundColor(.secondary)
            
            HStack(spacing: 8) {
                Button(action: onStart) {
                    Label("启动", systemImage: "play.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(.green)
                .disabled(isRunning)
                
                Button(action: onStop) {
                    Label("停止", systemImage: "stop.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .tint(.red)
                .disabled(!isRunning)
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(12)
    }
}

struct LogView: View {
    let logs: [ProcessManager.LogEntry]
    let onClear: () -> Void
    
    @State private var autoScroll = true
    
    private var logsText: String {
        logs.map { entry in
            let formatter = DateFormatter()
            formatter.dateFormat = "HH:mm:ss"
            let time = formatter.string(from: entry.timestamp)
            return "[\(time)] [\(entry.level.rawValue)] \(entry.message)"
        }.joined(separator: "\n")
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // 工具栏
            HStack {
                Text("\(logs.count) 条日志")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                Spacer()
                
                Toggle("自动滚动", isOn: $autoScroll)
                    .toggleStyle(.checkbox)
                    .font(.caption)
                
                Button(action: copyAllLogs) {
                    Label("复制全部", systemImage: "doc.on.doc")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .disabled(logs.isEmpty)
                
                Button(action: onClear) {
                    Label("清除", systemImage: "trash")
                        .font(.caption)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal)
            .padding(.vertical, 4)
            
            Divider()
            
            // 使用 NSTextView 包装的日志视图
            LogTextView(text: logsText, autoScroll: autoScroll)
                .background(Color(NSColor.textBackgroundColor))
        }
    }
    
    private func copyAllLogs() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(logsText, forType: .string)
    }
}

// NSTextView 包装器 - 支持全选和复制
struct LogTextView: NSViewRepresentable {
    let text: String
    let autoScroll: Bool
    
    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSTextView.scrollableTextView()
        let textView = scrollView.documentView as! NSTextView
        
        textView.isEditable = false
        textView.isSelectable = true
        textView.font = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
        textView.backgroundColor = NSColor.textBackgroundColor
        textView.textColor = NSColor.textColor
        textView.drawsBackground = true
        textView.isRichText = false
        textView.allowsUndo = false
        
        // 自动换行
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.containerSize = NSSize(
            width: CGFloat.greatestFiniteMagnitude,
            height: CGFloat.greatestFiniteMagnitude
        )
        textView.isHorizontallyResizable = false
        textView.isVerticallyResizable = true
        
        return scrollView
    }
    
    func updateNSView(_ nsView: NSScrollView, context: Context) {
        guard let textView = nsView.documentView as? NSTextView else { return }
        
        let currentText = textView.string
        if currentText != text {
            // 保存当前选择
            let selectedRanges = textView.selectedRanges
            
            // 使用带颜色的属性字符串
            let attributedString = colorizedLogText(text)
            textView.textStorage?.setAttributedString(attributedString)
            
            // 恢复选择
            if !selectedRanges.isEmpty {
                textView.selectedRanges = selectedRanges
            }
            
            // 自动滚动到底部
            if autoScroll && !text.isEmpty {
                textView.scrollToEndOfDocument(nil)
            }
        }
    }
    
    private func colorizedLogText(_ text: String) -> NSAttributedString {
        let result = NSMutableAttributedString()
        let lines = text.components(separatedBy: "\n")
        
        let defaultFont = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
        let timeColor = NSColor.secondaryLabelColor
        let infoColor = NSColor.textColor
        let warningColor = NSColor.systemOrange
        let errorColor = NSColor.systemRed
        let debugColor = NSColor.systemGray
        
        for (index, line) in lines.enumerated() {
            if line.isEmpty { continue }
            
            var textColor = infoColor
            if line.contains("[ERROR]") {
                textColor = errorColor
            } else if line.contains("[WARNING]") {
                textColor = warningColor
            } else if line.contains("[DEBUG]") {
                textColor = debugColor
            }
            
            // 时间部分着色
            if let timeRange = line.range(of: #"\[\d{2}:\d{2}:\d{2}\]"#, options: .regularExpression) {
                let timeStr = String(line[timeRange])
                let restStr = String(line[timeRange.upperBound...])
                
                let timeAttr = NSAttributedString(string: timeStr, attributes: [
                    .font: defaultFont,
                    .foregroundColor: timeColor
                ])
                let restAttr = NSAttributedString(string: restStr, attributes: [
                    .font: defaultFont,
                    .foregroundColor: textColor
                ])
                
                result.append(timeAttr)
                result.append(restAttr)
            } else {
                let lineAttr = NSAttributedString(string: line, attributes: [
                    .font: defaultFont,
                    .foregroundColor: textColor
                ])
                result.append(lineAttr)
            }
            
            if index < lines.count - 1 {
                result.append(NSAttributedString(string: "\n"))
            }
        }
        
        return result
    }
}

#Preview {
    ServiceManagerView()
        .frame(width: 600, height: 400)
}
