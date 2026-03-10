import Foundation
import ApplicationServices
import AppKit

// MARK: - AX Event Types

/// AX 事件通知结构
struct AXEvent: Codable {
    let eventType: String
    let appName: String
    let pid: Int32
    let elementRole: String
    let elementTitle: String
    let timestamp: Double
    let stateVersion: UInt64
    // 完整上下文（bounds + parent）
    let positionX: Double?
    let positionY: Double?
    let sizeWidth: Double?
    let sizeHeight: Double?
    let parentRole: String?
    let parentTitle: String?
    let value: String?
}

// MARK: - AXObserverManager

/// 管理 macOS AXObserver，持续监听 UI 变化事件
/// 不再需要 polling — 当 UI 变化时自动通知
class AXObserverManager: ObservableObject {
    static let shared = AXObserverManager()
    
    /// 事件回调
    var onEvent: ((AXEvent) -> Void)?
    
    /// 正在监听的应用 PID → observer
    private var observers: [pid_t: AXObserver] = [:]
    
    /// 监听的事件类型
    private let watchedNotifications: [String] = [
        kAXFocusedUIElementChangedNotification as String,
        kAXFocusedWindowChangedNotification as String,
        kAXWindowCreatedNotification as String,
        kAXWindowMovedNotification as String,
        kAXWindowResizedNotification as String,
        kAXWindowMiniaturizedNotification as String,
        kAXWindowDeminiaturizedNotification as String,
        kAXApplicationActivatedNotification as String,
        kAXApplicationDeactivatedNotification as String,
        kAXValueChangedNotification as String,
        kAXUIElementDestroyedNotification as String,
        kAXTitleChangedNotification as String,
        kAXSelectedTextChangedNotification as String,
    ]
    
    /// 应用名称缓存
    private(set) var appNames: [pid_t: String] = [:]
    
    /// 公开已观察应用名列表（供 UI 使用）
    var observedAppNames: [String] { Array(appNames.values) }
    
    private init() {}
    
    // MARK: - Start/Stop
    
    /// 开始监听指定应用
    func observe(pid: pid_t, appName: String? = nil) {
        guard observers[pid] == nil else { return }
        
        var observer: AXObserver?
        let result = AXObserverCreate(pid, axObserverCallback, &observer)
        guard result == .success, let obs = observer else {
            print("[AXObserver] Failed to create observer for PID \(pid): \(result.rawValue)")
            return
        }
        
        let axApp = AXUIElementCreateApplication(pid)
        for notification in watchedNotifications {
            AXObserverAddNotification(obs, axApp, notification as CFString, Unmanaged.passUnretained(self).toOpaque())
        }
        
        CFRunLoopAddSource(CFRunLoopGetMain(), AXObserverGetRunLoopSource(obs), .defaultMode)
        
        observers[pid] = obs
        if let name = appName {
            appNames[pid] = name
        } else {
            appNames[pid] = NSRunningApplication(processIdentifier: pid)?.localizedName ?? "Unknown"
        }
        
        print("[AXObserver] Now observing PID \(pid) (\(appNames[pid] ?? "?"))")
        
        // 扫描该应用已有的窗口，填充 windowStates（解决 app 比 MacAgentApp 先启动的情况）
        bootstrapExistingWindows(pid: pid, appName: appNames[pid] ?? "Unknown")
    }
    
    /// 停止监听指定应用
    func stopObserving(pid: pid_t) {
        guard let obs = observers.removeValue(forKey: pid) else { return }
        CFRunLoopRemoveSource(CFRunLoopGetMain(), AXObserverGetRunLoopSource(obs), .defaultMode)
        appNames.removeValue(forKey: pid)
        print("[AXObserver] Stopped observing PID \(pid)")
    }
    
    /// 监听所有当前 regular 应用
    func observeAllApps() {
        let workspace = NSWorkspace.shared
        for app in workspace.runningApplications where app.activationPolicy == .regular {
            observe(pid: app.processIdentifier, appName: app.localizedName)
        }
    }
    
    /// 停止全部监听
    func stopAll() {
        for pid in Array(observers.keys) {
            stopObserving(pid: pid)
        }
    }
    
    /// 已监听的应用数量
    var observedCount: Int { observers.count }
    
    /// 崩溃恢复 — 定期检查已观察进程是否还活着
    private var healthCheckTimer: Timer?
    
    /// 新应用检测定时器
    private var appScanTimer: Timer?
    
    /// 启动健康监控（Observer 崩溃恢复 + 新应用检测）
    func startHealthMonitoring() {
        // 每 10s 检查已观察进程
        healthCheckTimer = Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { [weak self] _ in
            self?.checkObserverHealth()
        }
        // 每 5s 扫描新应用
        appScanTimer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            self?.scanNewApps()
        }
    }
    
    func stopHealthMonitoring() {
        healthCheckTimer?.invalidate()
        healthCheckTimer = nil
        appScanTimer?.invalidate()
        appScanTimer = nil
    }
    
    private func checkObserverHealth() {
        let deadPids = observers.keys.filter { pid in
            NSRunningApplication(processIdentifier: pid) == nil
        }
        for pid in deadPids {
            print("[AXObserver] Process \(pid) (\(appNames[pid] ?? "?")) died, removing observer")
            stopObserving(pid: pid)
        }
    }
    
    private func scanNewApps() {
        let workspace = NSWorkspace.shared
        for app in workspace.runningApplications where app.activationPolicy == .regular {
            if observers[app.processIdentifier] == nil {
                observe(pid: app.processIdentifier, appName: app.localizedName)
            }
        }
    }
    
    // MARK: - Bootstrap Existing Windows
    
    /// 扫描应用已有的窗口，合成 WindowCreated 事件发给 GUIStateStore
    private func bootstrapExistingWindows(pid: pid_t, appName: String) {
        let axApp = AXUIElementCreateApplication(pid)
        var windowsValue: AnyObject?
        guard AXUIElementCopyAttributeValue(axApp, kAXWindowsAttribute as CFString, &windowsValue) == .success,
              let windows = windowsValue as? [AXUIElement] else { return }
        
        for window in windows {
            var titleStr = ""
            if let t: String = getAttribute(window, attribute: kAXTitleAttribute) {
                titleStr = t
            }
            
            // 合成一个 WindowCreated 事件
            let event = AXEvent(
                eventType: kAXWindowCreatedNotification as String,
                appName: appName,
                pid: pid,
                elementRole: "AXWindow",
                elementTitle: titleStr,
                timestamp: Date().timeIntervalSince1970,
                stateVersion: 0,
                positionX: nil,
                positionY: nil,
                sizeWidth: nil,
                sizeHeight: nil,
                parentRole: nil,
                parentTitle: nil,
                value: nil
            )
            onEvent?(event)
        }
        
        if !windows.isEmpty {
            print("[AXObserver] Bootstrapped \(windows.count) existing window(s) for PID \(pid) (\(appName))")
        }
    }
    
    // MARK: - Internal Callback
    
    fileprivate func handleNotification(observer: AXObserver, element: AXUIElement, notification: String) {
        let pid = pidFromElement(element)
        let appName = appNames[pid] ?? "Unknown"
        
        // 读取元素基本信息
        var role = ""
        var title = ""
        if let r: String = getAttribute(element, attribute: kAXRoleAttribute) {
            role = r
        }
        if let t: String = getAttribute(element, attribute: kAXTitleAttribute) {
            title = t
        }

        // 位置和大小
        var posX: Double? = nil
        var posY: Double? = nil
        var sizeW: Double? = nil
        var sizeH: Double? = nil
        var posValue: AnyObject?
        if AXUIElementCopyAttributeValue(element, kAXPositionAttribute as CFString, &posValue) == .success,
           let axVal = posValue {
            var pt = CGPoint.zero
            if AXValueGetValue(axVal as! AXValue, .cgPoint, &pt) {
                posX = Double(pt.x)
                posY = Double(pt.y)
            }
        }
        var sizeValue: AnyObject?
        if AXUIElementCopyAttributeValue(element, kAXSizeAttribute as CFString, &sizeValue) == .success,
           let axVal = sizeValue {
            var sz = CGSize.zero
            if AXValueGetValue(axVal as! AXValue, .cgSize, &sz) {
                sizeW = Double(sz.width)
                sizeH = Double(sz.height)
            }
        }

        // parent 信息
        var parentRole: String? = nil
        var parentTitle: String? = nil
        var parentRef: AnyObject?
        if AXUIElementCopyAttributeValue(element, kAXParentAttribute as CFString, &parentRef) == .success,
           let parent = parentRef {
            let parentElem = parent as! AXUIElement
            if let pr: String = getAttribute(parentElem, attribute: kAXRoleAttribute) { parentRole = pr }
            if let pt: String = getAttribute(parentElem, attribute: kAXTitleAttribute) { parentTitle = pt }
        }

        // 值
        let elementValue: String? = getAttribute(element, attribute: kAXValueAttribute)
        
        let event = AXEvent(
            eventType: notification,
            appName: appName,
            pid: pid,
            elementRole: role,
            elementTitle: title,
            timestamp: Date().timeIntervalSince1970,
            stateVersion: GUIStateStore.shared.version,
            positionX: posX,
            positionY: posY,
            sizeWidth: sizeW,
            sizeHeight: sizeH,
            parentRole: parentRole,
            parentTitle: parentTitle,
            value: elementValue
        )
        
        // 更新 GUIStateStore
        GUIStateStore.shared.applyEvent(event, element: element)
        
        // 通知订阅者
        onEvent?(event)
    }
    
    private func pidFromElement(_ element: AXUIElement) -> pid_t {
        var pid: pid_t = 0
        AXUIElementGetPid(element, &pid)
        return pid
    }
    
    private func getAttribute<T>(_ element: AXUIElement, attribute: String) -> T? {
        var value: AnyObject?
        let result = AXUIElementCopyAttributeValue(element, attribute as CFString, &value)
        guard result == .success else { return nil }
        return value as? T
    }
}

// MARK: - C Callback

/// AXObserver 的 C 函数回调
private func axObserverCallback(
    observer: AXObserver,
    element: AXUIElement,
    notification: CFString,
    refcon: UnsafeMutableRawPointer?
) {
    guard let refcon = refcon else { return }
    let manager = Unmanaged<AXObserverManager>.fromOpaque(refcon).takeUnretainedValue()
    manager.handleNotification(observer: observer, element: element, notification: notification as String)
}
