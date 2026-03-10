import Foundation
import ApplicationServices

// MARK: - Data Models

/// 表示一个 AX UI 元素的可序列化结构
struct AXElementInfo: Codable {
    let role: String
    let roleDescription: String
    let title: String
    let value: String
    let label: String
    let description: String
    let enabled: Bool
    let focused: Bool
    let position: CGPointCodable?
    let size: CGSizeCodable?
    let identifier: String
    let subrole: String
    let children: [AXElementInfo]?
    
    /// 元素中心坐标（方便点击）
    var center: CGPointCodable? {
        guard let p = position, let s = size else { return nil }
        return CGPointCodable(x: p.x + s.width / 2, y: p.y + s.height / 2)
    }
}

struct CGPointCodable: Codable {
    let x: Double
    let y: Double
}

struct CGSizeCodable: Codable {
    let width: Double
    let height: Double
}

/// 表示一个窗口信息
struct AXWindowInfo: Codable {
    let title: String
    let position: CGPointCodable?
    let size: CGSizeCodable?
    let focused: Bool
    let minimized: Bool
    let fullScreen: Bool
}

/// 表示一个应用进程信息
struct AXAppInfo: Codable {
    let name: String
    let pid: pid_t
    let bundleId: String?
    let windows: [AXWindowInfo]
}

// MARK: - AccessibilityService

/// 原生 Accessibility API 服务 — 封装 AXUIElement
/// 不依赖 AppleScript，直接使用 macOS AX API 进行 UI 元素树遍历与属性读取
class AccessibilityService {
    static let shared = AccessibilityService()
    
    private init() {}
    
    // MARK: - Permission
    
    /// 检查当前进程是否有辅助功能权限
    var isTrusted: Bool {
        AXIsProcessTrusted()
    }
    
    // MARK: - Application Discovery
    
    /// 获取所有正在运行的应用（有窗口的）
    func listRunningApps() -> [AXAppInfo] {
        let workspace = NSWorkspace.shared
        return workspace.runningApplications.compactMap { app in
            guard app.activationPolicy == .regular,
                  let name = app.localizedName else { return nil }
            let axApp = AXUIElementCreateApplication(app.processIdentifier)
            let windows = getWindowInfos(for: axApp)
            return AXAppInfo(
                name: name,
                pid: app.processIdentifier,
                bundleId: app.bundleIdentifier,
                windows: windows
            )
        }
    }
    
    /// 通过名称查找应用的 PID
    func findApp(name: String) -> (pid_t, AXUIElement)? {
        let workspace = NSWorkspace.shared
        let lowerName = name.lowercased()
        for app in workspace.runningApplications {
            guard app.activationPolicy == .regular,
                  let localName = app.localizedName else { continue }
            if localName.lowercased() == lowerName
                || localName.lowercased().contains(lowerName)
                || (app.bundleIdentifier?.lowercased().contains(lowerName) ?? false) {
                let axApp = AXUIElementCreateApplication(app.processIdentifier)
                return (app.processIdentifier, axApp)
            }
        }
        return nil
    }
    
    // MARK: - Window Info
    
    /// 获取一个 AXUIElement (application) 的窗口列表
    func getWindowInfos(for app: AXUIElement) -> [AXWindowInfo] {
        guard let windows: [AXUIElement] = getAttribute(app, attribute: kAXWindowsAttribute) else {
            return []
        }
        return windows.map { win in
            let title: String = getAttribute(win, attribute: kAXTitleAttribute) ?? ""
            let focused: Bool = getAttribute(win, attribute: kAXFocusedAttribute) ?? false
            let minimized: Bool = getAttribute(win, attribute: kAXMinimizedAttribute) ?? false
            let fullScreen: Bool = getAttribute(win, attribute: "AXFullScreen") ?? false
            let position = getPosition(win)
            let size = getSize(win)
            return AXWindowInfo(
                title: title,
                position: position,
                size: size,
                focused: focused,
                minimized: minimized,
                fullScreen: fullScreen
            )
        }
    }
    
    /// 获取指定应用名称的窗口信息
    func getWindowInfo(appName: String) -> [AXWindowInfo]? {
        guard let (_, axApp) = findApp(name: appName) else { return nil }
        return getWindowInfos(for: axApp)
    }
    
    // MARK: - Element Tree
    
    /// 获取指定应用窗口中的 UI 元素树
    /// - Parameters:
    ///   - appName: 应用名称
    ///   - maxDepth: 最大递归深度（防止无限递归），默认 5
    ///   - windowIndex: 窗口索引，默认 0（第一个窗口）
    /// - Returns: 扁平化或树状的元素列表
    func getElementTree(appName: String, maxDepth: Int = 5, windowIndex: Int = 0) -> [AXElementInfo]? {
        guard let (_, axApp) = findApp(name: appName) else { return nil }
        guard let windows: [AXUIElement] = getAttribute(axApp, attribute: kAXWindowsAttribute),
              windowIndex < windows.count else { return nil }
        let window = windows[windowIndex]
        return getChildElements(of: window, depth: 0, maxDepth: maxDepth)
    }
    
    /// 获取指定应用窗口中所有元素的扁平列表（不包含层级）
    func getFlatElements(appName: String, maxDepth: Int = 5, windowIndex: Int = 0) -> [AXElementInfo]? {
        guard let (_, axApp) = findApp(name: appName) else { return nil }
        guard let windows: [AXUIElement] = getAttribute(axApp, attribute: kAXWindowsAttribute),
              windowIndex < windows.count else { return nil }
        let window = windows[windowIndex]
        var result: [AXElementInfo] = []
        collectFlatElements(of: window, into: &result, depth: 0, maxDepth: maxDepth)
        return result
    }
    
    // MARK: - Element Actions
    
    /// 通过 AX API 执行元素的 Action（如按按钮）
    func performAction(appName: String, role: String?, title: String?, action: String = kAXPressAction as String, windowIndex: Int = 0) -> Bool {
        guard let (_, axApp) = findApp(name: appName) else { return false }
        guard let windows: [AXUIElement] = getAttribute(axApp, attribute: kAXWindowsAttribute),
              windowIndex < windows.count else { return false }
        let window = windows[windowIndex]
        
        guard let element = findElement(in: window, role: role, title: title, depth: 0, maxDepth: 10) else {
            return false
        }
        let result = AXUIElementPerformAction(element, action as CFString)
        return result == .success
    }
    
    /// 通过 AX API 设置元素的值（如输入文本框）
    func setValue(appName: String, role: String?, title: String?, value: String, windowIndex: Int = 0) -> Bool {
        guard let (_, axApp) = findApp(name: appName) else { return false }
        guard let windows: [AXUIElement] = getAttribute(axApp, attribute: kAXWindowsAttribute),
              windowIndex < windows.count else { return false }
        let window = windows[windowIndex]
        
        guard let element = findElement(in: window, role: role, title: title, depth: 0, maxDepth: 10) else {
            return false
        }
        // 先聚焦
        AXUIElementSetAttributeValue(element, kAXFocusedAttribute as CFString, kCFBooleanTrue)
        let result = AXUIElementSetAttributeValue(element, kAXValueAttribute as CFString, value as CFTypeRef)
        return result == .success
    }
    
    /// 通过 AX API 读取元素当前值
    func getValue(appName: String, role: String?, title: String?, windowIndex: Int = 0) -> String? {
        guard let (_, axApp) = findApp(name: appName) else { return nil }
        guard let windows: [AXUIElement] = getAttribute(axApp, attribute: kAXWindowsAttribute),
              windowIndex < windows.count else { return nil }
        let window = windows[windowIndex]
        guard let element = findElement(in: window, role: role, title: title, depth: 0, maxDepth: 10) else {
            return nil
        }
        return getValueAsString(element)
    }
    
    /// 获取当前聚焦元素信息
    func getFocusedElement() -> AXElementInfo? {
        let systemWide = AXUIElementCreateSystemWide()
        guard let focused: AXUIElement = getAttribute(systemWide, attribute: kAXFocusedUIElementAttribute) else {
            return nil
        }
        return buildElementInfo(from: focused, includeChildren: false)
    }
    
    /// 获取指定屏幕坐标处的元素
    func getElementAtPosition(x: Float, y: Float) -> AXElementInfo? {
        let systemWide = AXUIElementCreateSystemWide()
        var element: AXUIElement?
        let result = AXUIElementCopyElementAtPosition(systemWide, x, y, &element)
        guard result == .success, let elem = element else { return nil }
        return buildElementInfo(from: elem, includeChildren: false)
    }
    
    // MARK: - Private Helpers
    
    /// 递归获取子元素（树状）
    private func getChildElements(of element: AXUIElement, depth: Int, maxDepth: Int) -> [AXElementInfo] {
        guard depth < maxDepth else { return [] }
        guard let children: [AXUIElement] = getAttribute(element, attribute: kAXChildrenAttribute) else {
            return []
        }
        return children.compactMap { child in
            buildElementInfo(from: child, includeChildren: true, depth: depth + 1, maxDepth: maxDepth)
        }
    }
    
    /// 递归收集扁平元素列表
    private func collectFlatElements(of element: AXUIElement, into result: inout [AXElementInfo], depth: Int, maxDepth: Int) {
        guard depth < maxDepth else { return }
        guard let children: [AXUIElement] = getAttribute(element, attribute: kAXChildrenAttribute) else {
            return
        }
        for child in children {
            if let info = buildElementInfo(from: child, includeChildren: false) {
                result.append(info)
            }
            collectFlatElements(of: child, into: &result, depth: depth + 1, maxDepth: maxDepth)
        }
    }
    
    /// 从 AXUIElement 构建 AXElementInfo
    private func buildElementInfo(from element: AXUIElement, includeChildren: Bool, depth: Int = 0, maxDepth: Int = 5) -> AXElementInfo? {
        let role: String = getAttribute(element, attribute: kAXRoleAttribute) ?? ""
        let roleDesc: String = getAttribute(element, attribute: kAXRoleDescriptionAttribute) ?? ""
        let title: String = getAttribute(element, attribute: kAXTitleAttribute) ?? ""
        let label: String = getAttribute(element, attribute: "AXLabel") ?? ""
        let desc: String = getAttribute(element, attribute: kAXDescriptionAttribute) ?? ""
        let enabled: Bool = getAttribute(element, attribute: kAXEnabledAttribute) ?? true
        let focused: Bool = getAttribute(element, attribute: kAXFocusedAttribute) ?? false
        let identifier: String = getAttribute(element, attribute: "AXIdentifier") ?? ""
        let subrole: String = getAttribute(element, attribute: kAXSubroleAttribute) ?? ""
        let position = getPosition(element)
        let size = getSize(element)
        
        // 读取 value（可能是各种类型）
        let value = getValueAsString(element)
        
        let children: [AXElementInfo]? = includeChildren ? getChildElements(of: element, depth: depth, maxDepth: maxDepth) : nil
        
        return AXElementInfo(
            role: role,
            roleDescription: roleDesc,
            title: title,
            value: value,
            label: label,
            description: desc,
            enabled: enabled,
            focused: focused,
            position: position,
            size: size,
            identifier: identifier,
            subrole: subrole,
            children: children
        )
    }
    
    /// 递归搜索匹配的元素
    private func findElement(in parent: AXUIElement, role: String?, title: String?, depth: Int, maxDepth: Int) -> AXUIElement? {
        guard depth < maxDepth else { return nil }
        guard let children: [AXUIElement] = getAttribute(parent, attribute: kAXChildrenAttribute) else {
            return nil
        }
        for child in children {
            let childRole: String = getAttribute(child, attribute: kAXRoleAttribute) ?? ""
            let childTitle: String = getAttribute(child, attribute: kAXTitleAttribute) ?? ""
            let childDesc: String = getAttribute(child, attribute: kAXDescriptionAttribute) ?? ""
            let childLabel: String = getAttribute(child, attribute: "AXLabel") ?? ""
            let childIdentifier: String = getAttribute(child, attribute: "AXIdentifier") ?? ""
            
            var roleMatch = true
            if let role = role, !role.isEmpty {
                roleMatch = childRole.lowercased().contains(role.lowercased())
            }
            var titleMatch = false
            if let title = title, !title.isEmpty {
                let lowerTitle = title.lowercased()
                titleMatch = childTitle.lowercased().contains(lowerTitle)
                    || childDesc.lowercased().contains(lowerTitle)
                    || childLabel.lowercased().contains(lowerTitle)
                    || childIdentifier.lowercased().contains(lowerTitle)
            } else {
                titleMatch = true // 未指定 title 则不做过滤
            }
            
            if roleMatch && titleMatch {
                return child
            }
            if let found = findElement(in: child, role: role, title: title, depth: depth + 1, maxDepth: maxDepth) {
                return found
            }
        }
        return nil
    }
    
    // MARK: - AXUIElement Attribute Helpers
    
    /// 通用属性读取
    private func getAttribute<T>(_ element: AXUIElement, attribute: String) -> T? {
        var value: AnyObject?
        let result = AXUIElementCopyAttributeValue(element, attribute as CFString, &value)
        guard result == .success else { return nil }
        return value as? T
    }
    
    /// 读取 position（AXValue 类型）
    private func getPosition(_ element: AXUIElement) -> CGPointCodable? {
        var value: AnyObject?
        let result = AXUIElementCopyAttributeValue(element, kAXPositionAttribute as CFString, &value)
        guard result == .success, let axValue = value else { return nil }
        var point = CGPoint.zero
        guard AXValueGetValue(axValue as! AXValue, .cgPoint, &point) else { return nil }
        return CGPointCodable(x: Double(point.x), y: Double(point.y))
    }
    
    /// 读取 size（AXValue 类型）
    private func getSize(_ element: AXUIElement) -> CGSizeCodable? {
        var value: AnyObject?
        let result = AXUIElementCopyAttributeValue(element, kAXSizeAttribute as CFString, &value)
        guard result == .success, let axValue = value else { return nil }
        var size = CGSize.zero
        guard AXValueGetValue(axValue as! AXValue, .cgSize, &size) else { return nil }
        return CGSizeCodable(width: Double(size.width), height: Double(size.height))
    }
    
    /// 将 AXValue 转为可读字符串
    private func getValueAsString(_ element: AXUIElement) -> String {
        var value: AnyObject?
        let result = AXUIElementCopyAttributeValue(element, kAXValueAttribute as CFString, &value)
        guard result == .success, let val = value else { return "" }
        if let s = val as? String { return s }
        if let n = val as? NSNumber { return n.stringValue }
        return "\(val)"
    }
}

// MARK: - NSWorkspace (imported to avoid adding AppKit to imports list)
import AppKit
