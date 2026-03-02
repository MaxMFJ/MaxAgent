import SwiftUI

/// 权限设置页面 - 显示并引导用户配置各项系统权限
struct PermissionSettingsContent: View {
    @StateObject private var permissionManager = PermissionManager.shared
    @StateObject private var processManager = ProcessManager.shared
    @State private var showPythonPathCopied = false
    @State private var showCommandCopied = false
    @State private var isRestarting = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // 顶部状态概览
            overviewSection
            
            Divider()
            
            // 各权限详情
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    appAccessibilitySection
                    pythonAccessibilitySection
                    screenRecordingSection
                    automationSection
                    toolsSection
                }
                .padding(.bottom, 20)
            }
        }
        .padding(20)
        .onAppear {
            permissionManager.refreshAll()
        }
    }
    
    // MARK: - Overview
    
    private var overviewSection: some View {
        HStack(spacing: 16) {
            // 总体状态指示
            VStack(spacing: 8) {
                Image(systemName: permissionManager.allCriticalPermissionsGranted ? "checkmark.shield.fill" : "exclamationmark.shield.fill")
                    .font(.system(size: 36))
                    .foregroundColor(permissionManager.allCriticalPermissionsGranted ? .green : .orange)
                
                Text(permissionManager.allCriticalPermissionsGranted ? "权限就绪" : "需要配置")
                    .font(.headline)
                    .foregroundColor(permissionManager.allCriticalPermissionsGranted ? .green : .orange)
            }
            .frame(width: 100)
            
            VStack(alignment: .leading, spacing: 6) {
                Text("MacAgent 需要以下系统权限才能完整运行")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                if !permissionManager.allCriticalPermissionsGranted {
                    Text("请按照下方引导逐项开启权限。⚠️ 授权后需重启后端服务（或重启电脑），然后点击「刷新」检查状态。")
                        .font(.caption)
                        .foregroundColor(.orange)
                }
                
                HStack(spacing: 8) {
                    Button(action: { permissionManager.refreshAll() }) {
                        HStack(spacing: 4) {
                            if permissionManager.isChecking {
                                ProgressView()
                                    .scaleEffect(0.7)
                            } else {
                                Image(systemName: "arrow.clockwise")
                            }
                            Text("刷新状态")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(permissionManager.isChecking)
                    
                    if let lastCheck = permissionManager.lastCheckTime {
                        Text("上次检测: \(lastCheck, formatter: timeFormatter)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
            }
            
            Spacer()
        }
    }
    
    // MARK: - App Accessibility
    
    private var appAccessibilitySection: some View {
        PermissionRow(
            icon: "hand.tap.fill",
            title: "App 辅助功能权限",
            description: "允许 MacAgentApp 本身控制键鼠和窗口操作",
            isGranted: permissionManager.appAccessibilityGranted,
            guidance: permissionManager.appAccessibilityGranted
                ? "MacAgentApp 已拥有辅助功能权限。"
                : "点击下方按钮，系统将弹出权限请求对话框。如对话框未出现，请手动在系统设置中添加 MacAgentApp。",
            buttonTitle: permissionManager.appAccessibilityGranted ? "已授权" : "请求权限",
            buttonAction: {
                permissionManager.requestAppAccessibility()
            },
            secondaryButtonTitle: "打开系统设置",
            secondaryAction: {
                permissionManager.openAccessibilitySettings()
            },
            isButtonDisabled: permissionManager.appAccessibilityGranted
        )
    }
    
    // MARK: - Python Accessibility
    
    private var pythonAccessibilitySection: some View {
        PermissionRow(
            icon: "terminal.fill",
            title: "Python 辅助功能权限",
            description: "允许后端 Python 进程模拟键盘和鼠标（CGEvent / AppleScript keystroke）。这是 Agent 执行自动化操作的核心权限。",
            isGranted: permissionManager.pythonAccessibilityGranted,
            guidance: pythonAccessibilityGuidance,
            buttonTitle: "打开辅助功能设置",
            buttonAction: {
                permissionManager.openAccessibilitySettings()
            },
            isButtonDisabled: false,
            extraContent: AnyView(pythonPathInfo)
        )
    }
    
    private var pythonAccessibilityGuidance: String {
        if permissionManager.pythonAccessibilityGranted {
            return "Python 进程已拥有辅助功能权限，Agent 可以完整执行键鼠操作。"
        }
        if permissionManager.pythonPath.isEmpty {
            return "后端未运行，无法检测 Python 权限。请先启动后端服务，然后刷新。"
        }
        if permissionManager.pythonPathIsInsideAppBundle {
            return """
            Python 进程需要单独的辅助功能权限。
            
            ⚠️ 当前 Python 位于 .app 包内，系统文件浏览器中可能无法直接选中。
            请参考下方的「方式 1」或「方式 2」完成授权。
            
            ⚠️ 重要：授权完成后，必须重启后端服务（或重启电脑）才能生效！
            请点击下方的「重启后端并重新检测」按钮。
            """
        }
        return """
        Python 进程需要单独的辅助功能权限。操作步骤：
        1. 点击「打开辅助功能设置」
        2. 点击左下角 🔒 解锁
        3. 点击 + 号，添加下方 Python 路径
        4. ⚠️ 添加后必须重启后端服务才能生效
        5. 点击下方「重启后端并重新检测」按钮
        
        提示：此授权只需做一次，除非 Python 路径发生变化。
        """
    }
    
    @ViewBuilder
    private var pythonPathInfo: some View {
        if !permissionManager.pythonPath.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 4) {
                    Text("Python 实际路径 (sys.executable):")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    if permissionManager.pythonPathChanged {
                        Label("路径已变更，需重新授权", systemImage: "exclamationmark.triangle.fill")
                            .font(.caption2)
                            .foregroundColor(.orange)
                    }
                }
                
                pathCopyRow(permissionManager.pythonPath)
                
                // 如果 venv 路径不同于实际路径，也显示
                if !permissionManager.pythonPathVenv.isEmpty && permissionManager.pythonPathVenv != permissionManager.pythonPath {
                    Text("Python venv 路径:")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.top, 4)
                    pathCopyRow(permissionManager.pythonPathVenv)
                }
                
                // 如果路径在 .app 包内，提供特殊引导
                if permissionManager.pythonPathIsInsideAppBundle {
                    appBundlePythonGuidance
                }
                
                // Finder 快速导航（仅当路径不在 .app 包内时有效）
                if !permissionManager.pythonPathIsInsideAppBundle {
                    Button(action: {
                        let url = URL(fileURLWithPath: permissionManager.pythonDisplayPath)
                        NSWorkspace.shared.activateFileViewerSelecting([url])
                    }) {
                        Label("在 Finder 中显示", systemImage: "folder")
                            .font(.caption)
                    }
                    .buttonStyle(.link)
                }
                
                // 重启后端提示（始终显示，让用户知道需要重启）
                Divider()
                VStack(alignment: .leading, spacing: 6) {
                    Label(permissionManager.pythonAccessibilityGranted ? "权限生效中 ✓" : "⚠️ 授权后必须重启后端才能生效", systemImage: permissionManager.pythonAccessibilityGranted ? "checkmark.circle.fill" : "arrow.clockwise.circle.fill")
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundColor(permissionManager.pythonAccessibilityGranted ? .green : .orange)
                    
                    if !permissionManager.pythonAccessibilityGranted {
                        Text("macOS 辅助功能权限在进程启动时加载。在系统设置中添加 Python 后，必须重启后端服务（或重新启动电脑），权限才会生效。")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                        
                    Button(action: {
                        isRestarting = true
                        processManager.stopBackend()
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                            processManager.startBackend()
                            DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
                                isRestarting = false
                                permissionManager.refreshAll()
                            }
                        }
                    }) {
                        HStack(spacing: 4) {
                            if isRestarting {
                                ProgressView()
                                    .scaleEffect(0.6)
                            }
                            Label("重启后端并重新检测", systemImage: "arrow.clockwise")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(permissionManager.pythonAccessibilityGranted ? .green : .orange)
                    .disabled(isRestarting)
                    
                    if !permissionManager.pythonAccessibilityGranted {
                        Text("如果重启后仍显示未授权，请尝试重启电脑后再打开 MacAgentApp。")
                            .font(.caption2)
                            .foregroundColor(.orange)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(8)
                .background(permissionManager.pythonAccessibilityGranted ? Color.green.opacity(0.06) : Color.orange.opacity(0.06))
                .cornerRadius(6)
            }
        }
    }
    
    @ViewBuilder
    private func pathCopyRow(_ path: String) -> some View {
        HStack {
            Text(path)
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.primary)
                .textSelection(.enabled)
                .lineLimit(2)
            
            Button(action: {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(path, forType: .string)
                showPythonPathCopied = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                    showPythonPathCopied = false
                }
            }) {
                Image(systemName: showPythonPathCopied ? "checkmark" : "doc.on.doc")
                    .foregroundColor(showPythonPathCopied ? .green : .blue)
            }
            .buttonStyle(.plain)
            .help("复制路径")
        }
        .padding(8)
        .background(Color(NSColor.textBackgroundColor))
        .cornerRadius(6)
    }
    
    // MARK: - App Bundle Python Guidance
    
    @ViewBuilder
    private var appBundlePythonGuidance: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Python 位于 .app 包内，系统文件浏览器中可能无法选择", systemImage: "exclamationmark.triangle.fill")
                .font(.caption)
                .fontWeight(.medium)
                .foregroundColor(.orange)
            
            // 方式 1：⌘⇧G 跳转全路径
            VStack(alignment: .leading, spacing: 4) {
                Text("方式 1（推荐）— 在文件选择器中输入完整路径")
                    .font(.caption)
                    .fontWeight(.medium)
                
                Text("""
                1. 在系统设置的辅助功能页面，点击 + 号
                2. 在弹出的文件选择器中，按 ⌘⇧G（Cmd+Shift+G）
                3. 在弹出的「前往文件夹」输入框中，粘贴以下完整路径：
                """)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                
                pathCopyRow(permissionManager.pythonPath)
                
                Text("4. 点击「前往」，系统会自动选中该文件，再点击「打开」即可")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            Divider()
            
            // 方式 2：Homebrew Python（推荐长期方案）
            VStack(alignment: .leading, spacing: 4) {
                Text("方式 2 — 改用 Homebrew Python（一劳永逸）")
                    .font(.caption)
                    .fontWeight(.medium)
                
                Text("当前 Python 来自 Xcode 内部，路径不便操作。推荐安装独立的 Homebrew Python：")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                
                let brewCommand = "brew install python@3 && cd \(backendDir) && rm -rf venv && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
                
                HStack {
                    Text(brewCommand)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundColor(.primary)
                        .textSelection(.enabled)
                        .lineLimit(3)
                    
                    Button(action: {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(brewCommand, forType: .string)
                        showCommandCopied = true
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                            showCommandCopied = false
                        }
                    }) {
                        Image(systemName: showCommandCopied ? "checkmark" : "doc.on.doc")
                            .foregroundColor(showCommandCopied ? .green : .blue)
                    }
                    .buttonStyle(.plain)
                    .help("复制命令")
                }
                .padding(8)
                .background(Color(NSColor.textBackgroundColor))
                .cornerRadius(6)
                
                Text("安装后重启后端，新的 Python 路径（如 /opt/homebrew/bin/python3）可在文件浏览器中正常选择。")
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(10)
        .background(Color.orange.opacity(0.06))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.orange.opacity(0.2), lineWidth: 1)
        )
        .cornerRadius(8)
    }
    
    private var backendDir: String {
        // 从 venv 路径推导 backend 目录
        let venv = permissionManager.pythonPathVenv
        if !venv.isEmpty, let range = venv.range(of: "/venv/") {
            return String(venv[..<range.lowerBound])
        }
        // 尝试从 python path
        if let range = permissionManager.pythonPath.range(of: "/backend/") {
            return String(permissionManager.pythonPath[..<range.upperBound].dropLast())
        }
        return "~/MacAgent/backend"
    }
    
    // MARK: - Screen Recording
    
    private var screenRecordingSection: some View {
        PermissionRow(
            icon: "rectangle.dashed.badge.record",
            title: "屏幕录制权限",
            description: "允许后端截取屏幕内容，用于 Agent 的视觉感知（截图分析 UI 元素）",
            isGranted: permissionManager.screenRecordingGranted,
            guidance: permissionManager.screenRecordingGranted
                ? "屏幕录制权限已授予。"
                : """
                操作步骤：
                1. 点击「打开屏幕录制设置」
                2. 点击 + 号，添加 Python 可执行文件
                3. 也可以添加 MacAgentApp（如系统提示）
                4. ⚠️ 添加后需重启后端服务（或重启电脑）才能生效
                """,
            buttonTitle: "打开屏幕录制设置",
            buttonAction: {
                permissionManager.openScreenRecordingSettings()
            },
            isButtonDisabled: false
        )
    }
    
    // MARK: - Automation
    
    private var automationSection: some View {
        PermissionRow(
            icon: "gearshape.2.fill",
            title: "自动化权限 (System Events)",
            description: "允许 Python 通过 AppleScript 控制其他应用（如打开/关闭应用、操作窗口等）",
            isGranted: permissionManager.automationGranted,
            guidance: permissionManager.automationGranted
                ? "Python 已获得 System Events 自动化权限。\n如需控制其他应用（微信、Finder 等），首次操作时系统会弹窗请求。"
                : """
                Python 进程需要自动化权限才能通过 AppleScript 控制其他应用。
                操作步骤：
                1. 点击「打开自动化设置」
                2. 如果列表中有 Python / python3，确保 System Events 已勾选
                3. 如果没有，后端运行 AppleScript 时系统会自动弹窗请求
                4. 确保不要拒绝弹窗请求
                """,
            buttonTitle: "打开自动化设置",
            buttonAction: {
                permissionManager.openAutomationSettings()
            },
            isButtonDisabled: false
        )
    }
    
    // MARK: - Tools
    
    private var toolsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("工具可用性")
                .font(.headline)
            
            Text("以下工具用于 Agent 的自动化操作，非必需但可提升兼容性")
                .font(.caption)
                .foregroundColor(.secondary)
            
            HStack(spacing: 20) {
                ToolStatusPill(
                    name: "CGEvent (Quartz)",
                    isAvailable: permissionManager.quartzAvailable,
                    tip: "进程内键鼠模拟 API，最快最可靠"
                )
                ToolStatusPill(
                    name: "cliclick",
                    isAvailable: permissionManager.cliclickAvailable,
                    tip: permissionManager.cliclickAvailable
                        ? "路径: \(permissionManager.cliclickPath)"
                        : "安装: brew install cliclick"
                )
                ToolStatusPill(
                    name: "osascript",
                    isAvailable: permissionManager.osascriptAvailable,
                    tip: "AppleScript, macOS 内置"
                )
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
    }
    
    // MARK: - Formatter
    
    private var timeFormatter: DateFormatter {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f
    }
}


// MARK: - Permission Row Component

struct PermissionRow: View {
    let icon: String
    let title: String
    let description: String
    let isGranted: Bool?
    let guidance: String
    let buttonTitle: String
    let buttonAction: () -> Void
    var secondaryButtonTitle: String? = nil
    var secondaryAction: (() -> Void)? = nil
    var isButtonDisabled: Bool = false
    var extraContent: AnyView? = nil
    var statusOverride: String? = nil
    
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                // 状态图标
                Image(systemName: icon)
                    .font(.system(size: 20))
                    .foregroundColor(statusColor)
                    .frame(width: 30)
                
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 8) {
                        Text(title)
                            .font(.headline)
                        
                        // 状态标签
                        Text(statusText)
                            .font(.caption2)
                            .fontWeight(.medium)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 2)
                            .background(statusColor.opacity(0.15))
                            .foregroundColor(statusColor)
                            .cornerRadius(4)
                    }
                    
                    Text(description)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                
                Spacer()
            }
            
            // 引导文本
            Text(guidance)
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(NSColor.textBackgroundColor).opacity(0.5))
                .cornerRadius(6)
                .fixedSize(horizontal: false, vertical: true)
            
            // 额外内容（如 Python 路径）
            if let extra = extraContent {
                extra
            }
            
            // 操作按钮
            HStack(spacing: 8) {
                Button(action: buttonAction) {
                    Label(buttonTitle, systemImage: isGranted == true ? "checkmark.circle" : "arrow.right.circle")
                }
                .buttonStyle(.borderedProminent)
                .tint(isGranted == true ? .green : .blue)
                .disabled(isButtonDisabled)
                
                if let secondaryTitle = secondaryButtonTitle, let secondaryAction = secondaryAction {
                    Button(action: secondaryAction) {
                        Label(secondaryTitle, systemImage: "gear")
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
    }
    
    private var statusColor: Color {
        if let granted = isGranted {
            return granted ? .green : .orange
        }
        return .blue
    }
    
    private var statusText: String {
        if let override = statusOverride {
            return override
        }
        if let granted = isGranted {
            return granted ? "已授权" : "未授权"
        }
        return "需手动检查"
    }
}


// MARK: - Tool Status Pill

struct ToolStatusPill: View {
    let name: String
    let isAvailable: Bool
    let tip: String
    
    var body: some View {
        VStack(spacing: 4) {
            HStack(spacing: 4) {
                Circle()
                    .fill(isAvailable ? Color.green : Color.gray)
                    .frame(width: 8, height: 8)
                Text(name)
                    .font(.caption)
                    .fontWeight(.medium)
            }
            Text(isAvailable ? "可用" : "不可用")
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color(NSColor.controlBackgroundColor))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(isAvailable ? Color.green.opacity(0.3) : Color.gray.opacity(0.3), lineWidth: 1)
        )
        .cornerRadius(6)
        .help(tip)
    }
}


#Preview {
    PermissionSettingsContent()
        .frame(width: 600, height: 700)
}
