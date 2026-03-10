import Foundation
import ApplicationServices
import AppKit

// MARK: - Batch Action Models

/// 单个动作请求
struct ActionRequest: Codable {
    let actionId: String
    let actionType: ActionType
    let parameters: [String: AnyCodable]
    let timeout: Double?
    let requiresFocus: Bool?
    
    enum ActionType: String, Codable {
        case focusApp = "focus_app"
        case focusWindow = "focus_window"
        case findElement = "find_element"
        case clickElement = "click_element"
        case clickPosition = "click_position"
        case setValue = "set_value"
        case pressAction = "press_action"
        case waitEvent = "wait_event"
        case getState = "get_state"
        case getElements = "get_elements"
        case getWindows = "get_windows"
        case keyPress = "key_press"
        case findText = "find_text"
    }
}

/// 错误策略
enum ErrorStrategy: String, Codable {
    case stopOnError = "stop_on_error"
    case continueOnError = "continue_on_error"
    case rollback = "rollback"
}

/// 批量动作请求
struct BatchRequest: Codable {
    let batchId: String
    let atomic: Bool
    let actions: [ActionRequest]
    let errorStrategy: ErrorStrategy?
    
    var strategy: ErrorStrategy { errorStrategy ?? (atomic ? .rollback : .stopOnError) }
}

/// 单个动作结果
struct ActionResult: Codable {
    let actionId: String
    let success: Bool
    let error: String?
    let data: [String: AnyCodable]?
    let stateVersion: UInt64
}

/// 批量执行结果
struct BatchResult: Codable {
    let batchId: String
    let success: Bool
    let results: [ActionResult]
    let finalStateVersion: UInt64
    let durationMs: Double
    let rolledBack: Bool?
}

// MARK: - Undo Log Entry

/// 记录一个可撤销操作（用于 rollback）
struct UndoEntry {
    let actionId: String
    let undoAction: () -> Void
}

// MARK: - ActionBatchExecutor
// Uses AnyCodable from Models/Message.swift

/// 批量动作事务执行器
/// 将多个 GUI 操作封装为一个事务，顺序执行，减少 IPC 往返
class ActionBatchExecutor {
    static let shared = ActionBatchExecutor()
    
    private let axService = AccessibilityService.shared
    private let stateStore = GUIStateStore.shared
    
    private init() {}
    
    // MARK: - Execute
    
    /// 执行单个动作
    func execute(action: ActionRequest) -> ActionResult {
        return performAction(action)
    }
    
    /// 执行批量动作（含 errorStrategy + rollback 支持）
    func executeBatch(batch: BatchRequest) -> BatchResult {
        let start = CFAbsoluteTimeGetCurrent()
        var results: [ActionResult] = []
        var overallSuccess = true
        var undoLog: [UndoEntry] = []
        var didRollback = false
        let strategy = batch.strategy
        
        // 如果需要 rollback，记录执行前的焦点状态
        let prevFocusedApp = NSWorkspace.shared.frontmostApplication
        
        for action in batch.actions {
            let result = performAction(action)
            results.append(result)
            
            if result.success {
                // 记录 undo（仅对有副作用的动作）
                if strategy == .rollback {
                    if let entry = buildUndoEntry(action: action, prevFocusedApp: prevFocusedApp) {
                        undoLog.append(entry)
                    }
                }
            } else {
                overallSuccess = false
                switch strategy {
                case .stopOnError:
                    break // 跳出 for loop 后面不会执行
                case .continueOnError:
                    continue
                case .rollback:
                    // 反序执行 undo
                    for entry in undoLog.reversed() {
                        entry.undoAction()
                    }
                    didRollback = true
                }
                if strategy != .continueOnError { break }
            }
        }
        
        let duration = (CFAbsoluteTimeGetCurrent() - start) * 1000
        
        return BatchResult(
            batchId: batch.batchId,
            success: overallSuccess,
            results: results,
            finalStateVersion: stateStore.version,
            durationMs: duration,
            rolledBack: didRollback ? true : nil
        )
    }
    
    /// 为给定动作创建 undo 条目（如果可逆）
    private func buildUndoEntry(action: ActionRequest, prevFocusedApp: NSRunningApplication?) -> UndoEntry? {
        switch action.actionType {
        case .focusApp:
            // undo: 切回之前的焦点应用
            guard let prev = prevFocusedApp else { return nil }
            return UndoEntry(actionId: action.actionId) {
                prev.activate()
            }
        case .setValue:
            // undo: 恢复旧值（需提前读取）
            let params = action.parameters.mapValues { $0.value }
            if let appName = params["app_name"] as? String,
               let role = params["role"] as? String? {
                let title = params["title"] as? String
                let oldValue = self.axService.getValue(appName: appName, role: role, title: title)
                if let old = oldValue {
                    return UndoEntry(actionId: action.actionId) {
                        _ = self.axService.setValue(appName: appName, role: role, title: title, value: old)
                    }
                }
            }
            return nil
        default:
            // 其它动作（click, keyPress 等）不可撤销
            return nil
        }
    }
    
    // MARK: - Action Dispatch
    
    private func performAction(_ action: ActionRequest) -> ActionResult {
        let params = action.parameters.mapValues { $0.value }
        
        switch action.actionType {
        case .focusApp:
            return executeFocusApp(actionId: action.actionId, params: params)
        case .focusWindow:
            return executeFocusWindow(actionId: action.actionId, params: params)
        case .findElement:
            return executeFindElement(actionId: action.actionId, params: params)
        case .clickElement:
            return executeClickElement(actionId: action.actionId, params: params)
        case .clickPosition:
            return executeClickPosition(actionId: action.actionId, params: params)
        case .setValue:
            return executeSetValue(actionId: action.actionId, params: params)
        case .pressAction:
            return executePressAction(actionId: action.actionId, params: params)
        case .waitEvent:
            return executeWaitEvent(actionId: action.actionId, params: params)
        case .getState:
            return executeGetState(actionId: action.actionId, params: params)
        case .getElements:
            return executeGetElements(actionId: action.actionId, params: params)
        case .getWindows:
            return executeGetWindows(actionId: action.actionId, params: params)
        case .keyPress:
            return executeKeyPress(actionId: action.actionId, params: params)
        case .findText:
            return executeFindText(actionId: action.actionId, params: params)
        }
    }
    
    // MARK: - Action Implementations
    
    private func executeFocusApp(actionId: String, params: [String: Any]) -> ActionResult {
        guard let appName = params["app_name"] as? String else {
            return ActionResult(actionId: actionId, success: false, error: "Missing app_name", data: nil, stateVersion: stateStore.version)
        }
        let workspace = NSWorkspace.shared
        for app in workspace.runningApplications where app.activationPolicy == .regular {
            let name = app.localizedName ?? ""
            if name.lowercased().contains(appName.lowercased()) {
                app.activate()
                return ActionResult(actionId: actionId, success: true, error: nil, data: [
                    "app_name": AnyCodable(name),
                    "pid": AnyCodable(Int(app.processIdentifier))
                ], stateVersion: stateStore.version)
            }
        }
        return ActionResult(actionId: actionId, success: false, error: "App not found: \(appName)", data: nil, stateVersion: stateStore.version)
    }
    
    private func executeFocusWindow(actionId: String, params: [String: Any]) -> ActionResult {
        guard let appName = params["app_name"] as? String else {
            return ActionResult(actionId: actionId, success: false, error: "Missing app_name", data: nil, stateVersion: stateStore.version)
        }
        guard let (_, axApp) = axService.findApp(name: appName) else {
            return ActionResult(actionId: actionId, success: false, error: "App not found", data: nil, stateVersion: stateStore.version)
        }
        let windowIndex = params["window_index"] as? Int ?? 0
        var windows: AnyObject?
        AXUIElementCopyAttributeValue(axApp, kAXWindowsAttribute as CFString, &windows)
        guard let winArray = windows as? [AXUIElement], windowIndex < winArray.count else {
            return ActionResult(actionId: actionId, success: false, error: "Window not found", data: nil, stateVersion: stateStore.version)
        }
        AXUIElementPerformAction(winArray[windowIndex], kAXRaiseAction as CFString)
        return ActionResult(actionId: actionId, success: true, error: nil, data: nil, stateVersion: stateStore.version)
    }
    
    private func executeFindElement(actionId: String, params: [String: Any]) -> ActionResult {
        guard let appName = params["app_name"] as? String else {
            return ActionResult(actionId: actionId, success: false, error: "Missing app_name", data: nil, stateVersion: stateStore.version)
        }
        let role = params["role"] as? String
        let title = params["title"] as? String
        let maxCount = params["max_count"] as? Int ?? 50
        
        guard var elements = axService.getFlatElements(appName: appName, maxDepth: 5) else {
            return ActionResult(actionId: actionId, success: false, error: "App/window not found", data: nil, stateVersion: stateStore.version)
        }
        
        if let role = role, !role.isEmpty {
            let lower = role.lowercased()
            elements = elements.filter { $0.role.lowercased().contains(lower) }
        }
        if let title = title, !title.isEmpty {
            let lower = title.lowercased()
            elements = elements.filter {
                $0.title.lowercased().contains(lower)
                || $0.label.lowercased().contains(lower)
                || $0.description.lowercased().contains(lower)
                || $0.identifier.lowercased().contains(lower)
            }
        }
        
        let limited = Array(elements.prefix(maxCount))
        let encoded = limited.map { elem -> [String: AnyCodable] in
            var d: [String: AnyCodable] = [
                "role": AnyCodable(elem.role),
                "title": AnyCodable(elem.title),
                "label": AnyCodable(elem.label),
                "identifier": AnyCodable(elem.identifier),
                "enabled": AnyCodable(elem.enabled),
            ]
            if let c = elem.center {
                d["center_x"] = AnyCodable(c.x)
                d["center_y"] = AnyCodable(c.y)
            }
            return d
        }
        
        return ActionResult(actionId: actionId, success: true, error: nil, data: [
            "count": AnyCodable(encoded.count),
            "total": AnyCodable(elements.count),
            "elements": AnyCodable(encoded.map { dict in dict.mapValues { $0.value } })
        ], stateVersion: stateStore.version)
    }
    
    private func executeClickElement(actionId: String, params: [String: Any]) -> ActionResult {
        guard let appName = params["app_name"] as? String else {
            return ActionResult(actionId: actionId, success: false, error: "Missing app_name", data: nil, stateVersion: stateStore.version)
        }
        let role = params["role"] as? String
        let title = params["title"] as? String
        let visionFallback = params["vision_fallback"] as? Bool ?? true
        
        let success = axService.performAction(appName: appName, role: role, title: title, action: kAXPressAction as String)
        if success {
            return ActionResult(actionId: actionId, success: true, error: nil, data: nil, stateVersion: stateStore.version)
        }
        
        // Vision fallback: 如果 AX 找不到元素，尝试 OCR 识别并坐标点击
        if visionFallback, let searchText = title ?? role {
            if let pid = NSWorkspace.shared.runningApplications.first(where: { $0.localizedName == appName })?.processIdentifier {
                let matches = VisionFallbackService.shared.findTextInApp(pid: pid, searchText: searchText)
                if let best = matches.first {
                    let point = best.center
                    let mouseDown = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: point, mouseButton: .left)
                    let mouseUp = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: point, mouseButton: .left)
                    mouseDown?.post(tap: .cghidEventTap)
                    mouseUp?.post(tap: .cghidEventTap)
                    return ActionResult(actionId: actionId, success: true, error: nil, data: [
                        "fallback": AnyCodable("vision_ocr"),
                        "matched_text": AnyCodable(best.text),
                        "confidence": AnyCodable(best.confidence),
                        "x": AnyCodable(point.x),
                        "y": AnyCodable(point.y)
                    ], stateVersion: stateStore.version)
                }
            }
        }
        
        return ActionResult(actionId: actionId, success: false, error: "Element not found or action failed (AX + Vision)", data: nil, stateVersion: stateStore.version)
    }
    
    private func executeClickPosition(actionId: String, params: [String: Any]) -> ActionResult {
        guard let x = (params["x"] as? Double) ?? (params["x"] as? Int).map({ Double($0) }),
              let y = (params["y"] as? Double) ?? (params["y"] as? Int).map({ Double($0) }) else {
            return ActionResult(actionId: actionId, success: false, error: "Missing x or y", data: nil, stateVersion: stateStore.version)
        }
        
        // 使用 CGEvent 进行坐标点击
        let point = CGPoint(x: x, y: y)
        let mouseDown = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: point, mouseButton: .left)
        let mouseUp = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: point, mouseButton: .left)
        mouseDown?.post(tap: .cghidEventTap)
        mouseUp?.post(tap: .cghidEventTap)
        
        return ActionResult(actionId: actionId, success: true, error: nil, data: [
            "x": AnyCodable(x), "y": AnyCodable(y)
        ], stateVersion: stateStore.version)
    }
    
    private func executeSetValue(actionId: String, params: [String: Any]) -> ActionResult {
        guard let appName = params["app_name"] as? String,
              let value = params["value"] as? String else {
            return ActionResult(actionId: actionId, success: false, error: "Missing app_name or value", data: nil, stateVersion: stateStore.version)
        }
        let role = params["role"] as? String
        let title = params["title"] as? String
        
        let success = axService.setValue(appName: appName, role: role, title: title, value: value)
        return ActionResult(actionId: actionId, success: success, error: success ? nil : "Set value failed", data: nil, stateVersion: stateStore.version)
    }
    
    private func executePressAction(actionId: String, params: [String: Any]) -> ActionResult {
        guard let appName = params["app_name"] as? String else {
            return ActionResult(actionId: actionId, success: false, error: "Missing app_name", data: nil, stateVersion: stateStore.version)
        }
        let role = params["role"] as? String
        let title = params["title"] as? String
        let actionName = params["action_name"] as? String ?? (kAXPressAction as String)
        
        let success = axService.performAction(appName: appName, role: role, title: title, action: actionName)
        return ActionResult(actionId: actionId, success: success, error: success ? nil : "Action failed", data: nil, stateVersion: stateStore.version)
    }
    
    private func executeWaitEvent(actionId: String, params: [String: Any]) -> ActionResult {
        // wait_event 在同步上下文中以 30ms 短等待实现
        // 实际事件驱动通过 event stream 订阅实现
        let timeoutMs = params["timeout_ms"] as? Int ?? 500
        let usecs = useconds_t(min(timeoutMs, 2000) * 1000)
        usleep(usecs)
        return ActionResult(actionId: actionId, success: true, error: nil, data: [
            "waited_ms": AnyCodable(timeoutMs)
        ], stateVersion: stateStore.version)
    }
    
    private func executeGetState(actionId: String, params: [String: Any]) -> ActionResult {
        let sinceVersion = (params["since_version"] as? Int).map { UInt64($0) }
        
        if let sv = sinceVersion, sv < stateStore.version {
            let diff = stateStore.getDiff(sinceVersion: sv)
            let eventDicts = diff.events.map { e -> [String: Any] in
                ["event_type": e.eventType, "app_name": e.appName, "pid": Int(e.pid),
                 "element_role": e.elementRole, "element_title": e.elementTitle, "timestamp": e.timestamp]
            }
            return ActionResult(actionId: actionId, success: true, error: nil, data: [
                "type": AnyCodable("diff"),
                "from_version": AnyCodable(Int(diff.fromVersion)),
                "to_version": AnyCodable(Int(diff.toVersion)),
                "focus_changed": AnyCodable(diff.focusChanged),
                "events": AnyCodable(eventDicts)
            ], stateVersion: stateStore.version)
        }
        
        let snapshot = stateStore.getSnapshot()
        return ActionResult(actionId: actionId, success: true, error: nil, data: [
            "type": AnyCodable("snapshot"),
            "version": AnyCodable(Int(snapshot.version)),
            "focused_app": AnyCodable(snapshot.focusedAppName),
            "focused_app_pid": AnyCodable(Int(snapshot.focusedAppPid)),
            "focused_element_role": AnyCodable(snapshot.focusedElementRole),
            "focused_element_title": AnyCodable(snapshot.focusedElementTitle),
            "window_count": AnyCodable(snapshot.windows.count)
        ], stateVersion: stateStore.version)
    }
    
    private func executeGetElements(actionId: String, params: [String: Any]) -> ActionResult {
        return executeFindElement(actionId: actionId, params: params)
    }
    
    private func executeGetWindows(actionId: String, params: [String: Any]) -> ActionResult {
        guard let appName = params["app_name"] as? String else {
            return ActionResult(actionId: actionId, success: false, error: "Missing app_name", data: nil, stateVersion: stateStore.version)
        }
        guard let windows = axService.getWindowInfo(appName: appName) else {
            return ActionResult(actionId: actionId, success: false, error: "App not found", data: nil, stateVersion: stateStore.version)
        }
        let encoded = windows.map { w -> [String: Any] in
            var d: [String: Any] = ["title": w.title, "focused": w.focused, "minimized": w.minimized, "full_screen": w.fullScreen]
            if let p = w.position { d["position"] = ["x": p.x, "y": p.y] }
            if let s = w.size { d["size"] = ["width": s.width, "height": s.height] }
            return d
        }
        return ActionResult(actionId: actionId, success: true, error: nil, data: [
            "windows": AnyCodable(encoded)
        ], stateVersion: stateStore.version)
    }
    
    private func executeKeyPress(actionId: String, params: [String: Any]) -> ActionResult {
        guard let text = params["text"] as? String else {
            return ActionResult(actionId: actionId, success: false, error: "Missing text", data: nil, stateVersion: stateStore.version)
        }
        
        // 使用 CGEvent 进行键盘输入
        let src = CGEventSource(stateID: .hidSystemState)
        for char in text {
            let str = String(char)
            let keyDown = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: true)
            let keyUp = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: false)
            
            var unichar = [UniChar]()
            for cu in str.utf16 { unichar.append(cu) }
            keyDown?.keyboardSetUnicodeString(stringLength: unichar.count, unicodeString: &unichar)
            keyUp?.keyboardSetUnicodeString(stringLength: unichar.count, unicodeString: &unichar)
            
            keyDown?.post(tap: .cghidEventTap)
            keyUp?.post(tap: .cghidEventTap)
        }
        
        return ActionResult(actionId: actionId, success: true, error: nil, data: [
            "typed": AnyCodable(text)
        ], stateVersion: stateStore.version)
    }
    
    // MARK: - Vision Fallback Actions
    
    private func executeFindText(actionId: String, params: [String: Any]) -> ActionResult {
        guard let searchText = params["text"] as? String else {
            return ActionResult(actionId: actionId, success: false, error: "Missing text", data: nil, stateVersion: stateStore.version)
        }
        
        let matches: [TextMatch]
        if let appName = params["app_name"] as? String,
           let pid = NSWorkspace.shared.runningApplications.first(where: { $0.localizedName == appName })?.processIdentifier {
            matches = VisionFallbackService.shared.findTextInApp(pid: pid, searchText: searchText)
        } else {
            matches = VisionFallbackService.shared.findText(searchText, in: VisionFallbackService.shared.captureMainScreen())
        }
        
        let encoded = matches.map { m -> [String: Any] in
            ["text": m.text, "confidence": m.confidence,
             "x": m.center.x, "y": m.center.y,
             "rect": ["x": m.rect.origin.x, "y": m.rect.origin.y,
                       "width": m.rect.width, "height": m.rect.height]]
        }
        
        return ActionResult(actionId: actionId, success: !matches.isEmpty, error: matches.isEmpty ? "Text not found on screen" : nil, data: [
            "matches": AnyCodable(encoded),
            "count": AnyCodable(matches.count)
        ], stateVersion: stateStore.version)
    }
}
