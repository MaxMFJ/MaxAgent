import Foundation
import Combine
import AppKit

/// 权限管理器 - 检测并管理 macOS 权限状态
@MainActor
class PermissionManager: ObservableObject {
    static let shared = PermissionManager()
    
    // MARK: - Published State
    
    /// App 本身的辅助功能权限
    @Published var appAccessibilityGranted: Bool = false
    /// Python 进程的辅助功能权限
    @Published var pythonAccessibilityGranted: Bool = false
    /// 屏幕录制权限
    @Published var screenRecordingGranted: Bool = false
    /// Quartz (CGEvent) 可用
    @Published var quartzAvailable: Bool = false
    /// cliclick 可用
    @Published var cliclickAvailable: Bool = false
    /// osascript 可用
    @Published var osascriptAvailable: Bool = false
    /// 自动化 (Automation) 权限
    @Published var automationGranted: Bool = false
    
    /// Python 可执行文件路径（已解析，可能在 .app 包内）
    @Published var pythonPath: String = ""
    /// Python venv 路径（未解析符号链接，用于显示给用户）
    @Published var pythonPathVenv: String = ""
    /// cliclick 路径
    @Published var cliclickPath: String = ""
    /// 是否正在检测
    @Published var isChecking: Bool = false
    /// 上次检测时间
    @Published var lastCheckTime: Date?
    
    /// 已保存的 Python 路径（用于检测路径变更）
    private var lastKnownPythonPath: String {
        get { UserDefaults.standard.string(forKey: "lastKnownPythonPath") ?? "" }
        set { UserDefaults.standard.set(newValue, forKey: "lastKnownPythonPath") }
    }
    /// Python 路径是否发生变更
    @Published var pythonPathChanged: Bool = false
    
    private var pollingTask: Task<Void, Never>?
    
    private init() {}
    
    // MARK: - Check Permissions
    
    /// 刷新所有权限状态
    func refreshAll() {
        guard !isChecking else { return }
        isChecking = true
        
        // 1. 检查 App 本身的辅助功能权限（本地检测）
        checkAppAccessibility()
        
        // 2. 从后端 API 获取 Python 进程的权限状态
        Task {
            await fetchBackendPermissions()
            isChecking = false
            lastCheckTime = Date()
        }
    }
    
    /// 检查 App 本身的辅助功能权限
    func checkAppAccessibility() {
        appAccessibilityGranted = AXIsProcessTrusted()
    }
    
    /// 从后端 API 获取 Python 进程的权限状态
    func fetchBackendPermissions() async {
        do {
            let url = URL(string: "http://127.0.0.1:\(PortConfiguration.shared.backendPort)/permissions/status")!
            var request = URLRequest(url: url)
            request.timeoutInterval = 5
            
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                return
            }
            
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                // Python path
                if let path = json["python_path"] as? String {
                    pythonPath = path
                }
                if let venvPath = json["python_path_venv"] as? String {
                    pythonPathVenv = venvPath
                }
                // 用 venv 路径检测变更（更稳定）
                let displayPath = pythonPathVenv.isEmpty ? pythonPath : pythonPathVenv
                if !displayPath.isEmpty {
                    if !lastKnownPythonPath.isEmpty && lastKnownPythonPath != displayPath {
                        pythonPathChanged = true
                    }
                    lastKnownPythonPath = displayPath
                }
                
                // Accessibility
                if let ax = json["accessibility"] as? [String: Any] {
                    pythonAccessibilityGranted = ax["granted"] as? Bool ?? false
                }
                
                // Screen Recording
                if let sr = json["screen_recording"] as? [String: Any] {
                    screenRecordingGranted = sr["granted"] as? Bool ?? false
                }
                
                // Automation
                if let auto_ = json["automation"] as? [String: Any] {
                    automationGranted = auto_["granted"] as? Bool ?? false
                }
                
                // Quartz
                if let q = json["quartz"] as? [String: Any] {
                    quartzAvailable = q["available"] as? Bool ?? false
                }
                
                // cliclick
                if let c = json["cliclick"] as? [String: Any] {
                    cliclickAvailable = c["available"] as? Bool ?? false
                    cliclickPath = c["path"] as? String ?? ""
                }
                
                // osascript
                if let o = json["osascript"] as? [String: Any] {
                    osascriptAvailable = o["available"] as? Bool ?? false
                }
            }
        } catch {
            // 后端未运行，静默处理
        }
    }
    
    // MARK: - Open System Settings
    
    /// 打开辅助功能设置
    func openAccessibilitySettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility") {
            NSWorkspace.shared.open(url)
        }
    }
    
    /// 打开屏幕录制设置
    func openScreenRecordingSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture") {
            NSWorkspace.shared.open(url)
        }
    }
    
    /// 打开自动化设置
    func openAutomationSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation") {
            NSWorkspace.shared.open(url)
        }
    }
    
    /// 请求 App 辅助功能权限（弹窗）
    func requestAppAccessibility() {
        let options = [kAXTrustedCheckOptionPrompt.takeRetainedValue() as String: true] as CFDictionary
        let trusted = AXIsProcessTrustedWithOptions(options)
        appAccessibilityGranted = trusted
    }
    
    // MARK: - Polling
    
    /// 开始定期轮询权限状态（每 30 秒）
    func startPolling() {
        stopPolling()
        pollingTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 30_000_000_000)
                checkAppAccessibility()
                await fetchBackendPermissions()
                lastCheckTime = Date()
            }
        }
    }
    
    func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }
    
    // MARK: - Helpers
    
    /// 总体权限就绪状态（所有关键权限已授予）
    var allCriticalPermissionsGranted: Bool {
        appAccessibilityGranted && pythonAccessibilityGranted && screenRecordingGranted && automationGranted
    }
    
    /// 用于显示给用户的 Python 路径（优先 venv 路径）
    var pythonDisplayPath: String {
        if !pythonPathVenv.isEmpty { return pythonPathVenv }
        return pythonPath
    }
    
    /// Python 路径的显示名（简化为文件名）
    var pythonDisplayName: String {
        let path = pythonDisplayPath
        if path.isEmpty { return "未检测到" }
        return (path as NSString).lastPathComponent
    }
    
    /// Python 路径是否位于 .app 包内（不方便通过文件浏览器导航）
    var pythonPathIsInsideAppBundle: Bool {
        return pythonPath.contains(".app/")
    }
}
