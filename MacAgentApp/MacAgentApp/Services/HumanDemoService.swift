import Foundation
import AppKit
import CoreGraphics

// MARK: - 人工演示数据模型

/// 演示概要（列表用）
struct DemoSummary: Codable, Identifiable {
    let id: String
    let task_description: String
    let status: String
    let event_count: Int
    let step_count: Int
    let created_at: Double
    let duration_seconds: Double
    let tags: [String]
    let generated_capsule_id: String
}

/// 压缩后的步骤
struct DemoStepItem: Codable, Identifiable {
    let id: String
    let action_type: String
    let description: String
}

/// 学习结果
struct DemoLearnResult: Codable {
    let ok: Bool
    let inferred_goal: String?
    let summary: String?
    let confidence: Double?
    let suggestions: [String]?
    let capsule_id: String?
    let has_capsule: Bool?
    let session_status: String?
    let error: String?
}

/// 审批结果
struct DemoApproveResult: Codable {
    let ok: Bool
    let capsule_id: String?
    let error: String?
}

// MARK: - 人工演示服务

@MainActor
class HumanDemoService: ObservableObject {
    @Published var demos: [DemoSummary] = []
    @Published var isRecording: Bool = false
    @Published var activeDemoId: String?
    @Published var activeEventCount: Int = 0
    @Published var isLoading: Bool = false
    @Published var isLearning: Bool = false
    @Published var errorMessage: String?
    @Published var learnResult: DemoLearnResult?
    @Published var keyboardCaptureWorking: Bool = true  // 键盘捕获是否正常

    private let urlSession: URLSession
    private var baseURL: String
    private var statusPollTask: Task<Void, Never>?
    private var mouseMonitor: Any?
    private var keyMonitor: Any?
    private var keyTapPort: CFMachPort?
    private var keyTapSource: CFRunLoopSource?
    private var localEventCount: Int = 0
    /// 节流：上次发送事件的时间（避免滚动/移动产生过多请求）
    private var lastScrollSendTime: TimeInterval = 0
    /// 上次点击时焦点输入框的值（用于检测文本变化）
    private var lastFocusedValue: String = ""
    private var lastFocusedRole: String = ""

    init(baseURL: String = "http://127.0.0.1:\(PortConfiguration.defaultBackendPort)") {
        self.baseURL = baseURL
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        self.urlSession = URLSession(configuration: config)
    }

    func updateBaseURL(_ url: String) {
        self.baseURL = url
    }

    // MARK: - 录制控制

    func startDemo(taskDescription: String, tags: [String] = []) async {
        guard let url = URL(string: "\(baseURL)/demos/start") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = [
            "session_id": "default",
            "task_description": taskDescription,
            "tags": tags,
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (data, _) = try await urlSession.data(for: request)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let ok = json["ok"] as? Bool, ok,
               let demoId = json["demo_id"] as? String {
                isRecording = true
                activeDemoId = demoId
                activeEventCount = 0
                errorMessage = nil
                startEventMonitors()
                startStatusPolling()
            }
        } catch {
            errorMessage = "启动演示录制失败: \(error.localizedDescription)"
        }
    }

    func stopDemo() async {
        // 在停止前最后一次检测文本输入
        detectTextInput()

        guard let url = URL(string: "\(baseURL)/demos/stop") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = ["session_id": "default"]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (_, _) = try await urlSession.data(for: request)
            stopEventMonitors()
            stopStatusPolling()
            isRecording = false
            activeDemoId = nil
            activeEventCount = 0
            await fetchDemos()
        } catch {
            errorMessage = "停止演示失败: \(error.localizedDescription)"
        }
    }

    func checkStatus() async {
        guard let url = URL(string: "\(baseURL)/demos/status?session_id=default") else { return }
        do {
            let (data, _) = try await urlSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                let recording = json["recording"] as? Bool ?? false
                isRecording = recording
                if recording {
                    activeDemoId = json["demo_id"] as? String
                    activeEventCount = json["event_count"] as? Int ?? 0
                } else {
                    stopStatusPolling()
                }
            }
        } catch { }
    }

    func startStatusPolling() {
        stopStatusPolling()
        statusPollTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                guard !Task.isCancelled else { break }
                await checkStatus()
            }
        }
    }

    func stopStatusPolling() {
        statusPollTask?.cancel()
        statusPollTask = nil
    }

    // MARK: - 全局事件监听（NSEvent + CGEventTap）

    /// Mac App 拥有辅助功能权限，在此捕获全局事件并转发给后端
    private func startEventMonitors() {
        stopEventMonitors()
        localEventCount = 0

        // 检查辅助功能权限
        let axTrusted = AXIsProcessTrusted()
        print("[HumanDemoService] 辅助功能权限: \(axTrusted)")

        // 鼠标点击（NSEvent 全局监听，不需要 Input Monitoring 权限）
        mouseMonitor = NSEvent.addGlobalMonitorForEvents(
            matching: [.leftMouseDown, .rightMouseDown]
        ) { [weak self] event in
            guard let self = self else { return }
            let loc = NSEvent.mouseLocation
            let screenHeight = NSScreen.main?.frame.height ?? 0
            let x = loc.x
            let y = screenHeight - loc.y
            let button = event.type == .rightMouseDown ? "right" : "left"
            let clickCount = event.clickCount

            // 在点击前，检查上次焦点元素是否有文本变化（推断键盘输入）
            self.detectTextInput()

            // AX 查询：获取点击位置的语义元素信息
            let axService = AccessibilityService.shared
            let elementInfo = axService.getElementAtPosition(x: Float(x), y: Float(y))

            // 获取当前前台应用信息
            let frontApp = NSWorkspace.shared.frontmostApplication
            let appName = frontApp?.localizedName ?? ""

            // 构建语义上下文
            var eventData: [String: Any] = [
                "raw_x": Int(x), "raw_y": Int(y),
                "button": button, "click_count": clickCount,
                "app_name": appName,
            ]

            if let info = elementInfo {
                eventData["ui_role"] = info.role
                eventData["ui_title"] = info.title
                eventData["ui_value"] = info.value
                eventData["ui_label"] = info.label
                eventData["ui_description"] = info.description
                eventData["ui_identifier"] = info.identifier
                eventData["ui_subrole"] = info.subrole
                eventData["ui_role_description"] = info.roleDescription

                // 获取父元素层级路径
                let elementPath = self.getElementHierarchyPath(x: Float(x), y: Float(y))
                eventData["element_path"] = elementPath

                // 记录当前焦点值（用于后续文本输入检测）
                self.lastFocusedValue = info.value
                self.lastFocusedRole = info.role
            }

            Task { @MainActor [weak self] in
                guard let self = self else { return }
                self.localEventCount += 1
                self.activeEventCount = self.localEventCount
            }

            self.sendEvent(type: "mouse_click", data: eventData)
        }

        // 键盘：优先 CGEventTap（辅助功能权限即可），失败则回退 NSEvent
        let tapOk = startCGEventTap()
        if !tapOk {
            print("[HumanDemoService] CGEventTap 失败，回退到 NSEvent 键盘监听")
            keyMonitor = NSEvent.addGlobalMonitorForEvents(
                matching: [.keyDown]
            ) { [weak self] event in
                guard let self = self else { return }
                print("[HumanDemoService] NSEvent keyDown: \(event.characters ?? "nil"), keyCode=\(event.keyCode)")
                self.handleKeyDown(
                    chars: event.characters ?? "",
                    keyCode: Int(event.keyCode),
                    flags: event.modifierFlags
                )
            }
            print("[HumanDemoService] NSEvent keyMonitor 已注册: \(keyMonitor != nil)")
        }

        // 3秒后检查键盘监听是否工作，如果没有收到任何键盘事件则提示用户
        let startCount = localEventCount
        Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 5_000_000_000) // 5秒
            guard let self = self, self.isRecording else { return }
            if self.localEventCount == startCount && !tapOk {
                print("[HumanDemoService] 警告：CGEventTap 失败且5秒内未收到事件，可能需要 Input Monitoring 权限")
                self.keyboardCaptureWorking = false
            }
        }
    }

    /// 通用键盘事件处理
    private func handleKeyDown(chars: String, keyCode: Int, flags: NSEvent.ModifierFlags) {
        print("[HumanDemoService] handleKeyDown: chars='\(chars)', keyCode=\(keyCode)")

        // 收到键盘事件说明权限正常
        Task { @MainActor [weak self] in
            self?.keyboardCaptureWorking = true
        }

        var modList: [String] = []
        if flags.contains(.command) { modList.append("cmd") }
        if flags.contains(.option) { modList.append("alt") }
        if flags.contains(.control) { modList.append("ctrl") }
        if flags.contains(.shift) { modList.append("shift") }

        Task { @MainActor [weak self] in
            guard let self = self else { return }
            self.localEventCount += 1
            self.activeEventCount = self.localEventCount
        }

        self.sendEvent(type: "key_press", data: [
            "text": chars,
            "key_code": keyCode,
            "modifiers": modList,
        ])
    }

    /// 使用 CGEventTap 捕获键盘事件（辅助功能权限足够）
    /// 返回 true 表示成功启动
    @discardableResult
    private func startCGEventTap() -> Bool {
        let eventMask: CGEventMask = (1 << CGEventType.keyDown.rawValue)

        let selfPtr = Unmanaged.passUnretained(self as AnyObject).toOpaque()

        // 尝试 cgAnnotatedSessionEventTap（macOS 更宽松的 tap 点）
        var tap = CGEvent.tapCreate(
            tap: .cgAnnotatedSessionEventTap,
            place: .headInsertEventTap,
            options: .listenOnly,
            eventsOfInterest: eventMask,
            callback: { (proxy, type, event, refcon) -> Unmanaged<CGEvent>? in
                guard let refcon = refcon else { return Unmanaged.passUnretained(event) }
                let service = Unmanaged<AnyObject>.fromOpaque(refcon).takeUnretainedValue() as! HumanDemoService

                if type == .keyDown {
                    let keyCode = event.getIntegerValueField(.keyboardEventKeycode)
                    let flags = event.flags
                    print("[HumanDemoService] CGEventTap keyDown: keyCode=\(keyCode)")

                    var nsFlags = NSEvent.ModifierFlags()
                    if flags.contains(.maskCommand) { nsFlags.insert(.command) }
                    if flags.contains(.maskAlternate) { nsFlags.insert(.option) }
                    if flags.contains(.maskControl) { nsFlags.insert(.control) }
                    if flags.contains(.maskShift) { nsFlags.insert(.shift) }

                    var chars = ""
                    if let nsEvent = NSEvent(cgEvent: event) {
                        chars = nsEvent.characters ?? ""
                    }

                    service.handleKeyDown(chars: chars, keyCode: Int(keyCode), flags: nsFlags)
                } else if type == .tapDisabledByUserInput || type == .tapDisabledByTimeout {
                    if let tapPort = service.keyTapPort {
                        CGEvent.tapEnable(tap: tapPort, enable: true)
                    }
                }

                return Unmanaged.passUnretained(event)
            },
            userInfo: selfPtr
        )

        // 如果 annotated tap 也失败，尝试 session tap
        if tap == nil {
            print("[HumanDemoService] cgAnnotatedSessionEventTap 失败，尝试 cgSessionEventTap")
            tap = CGEvent.tapCreate(
                tap: .cgSessionEventTap,
                place: .headInsertEventTap,
                options: .listenOnly,
                eventsOfInterest: eventMask,
                callback: { (proxy, type, event, refcon) -> Unmanaged<CGEvent>? in
                    guard let refcon = refcon else { return Unmanaged.passUnretained(event) }
                    let service = Unmanaged<AnyObject>.fromOpaque(refcon).takeUnretainedValue() as! HumanDemoService

                    if type == .keyDown {
                        let keyCode = event.getIntegerValueField(.keyboardEventKeycode)
                        let flags = event.flags
                        print("[HumanDemoService] CGEventTap(session) keyDown: keyCode=\(keyCode)")

                        var nsFlags = NSEvent.ModifierFlags()
                        if flags.contains(.maskCommand) { nsFlags.insert(.command) }
                        if flags.contains(.maskAlternate) { nsFlags.insert(.option) }
                        if flags.contains(.maskControl) { nsFlags.insert(.control) }
                        if flags.contains(.maskShift) { nsFlags.insert(.shift) }

                        var chars = ""
                        if let nsEvent = NSEvent(cgEvent: event) {
                            chars = nsEvent.characters ?? ""
                        }

                        service.handleKeyDown(chars: chars, keyCode: Int(keyCode), flags: nsFlags)
                    } else if type == .tapDisabledByUserInput || type == .tapDisabledByTimeout {
                        if let tapPort = service.keyTapPort {
                            CGEvent.tapEnable(tap: tapPort, enable: true)
                        }
                    }

                    return Unmanaged.passUnretained(event)
                },
                userInfo: selfPtr
            )
        }

        guard let validTap = tap else {
            print("[HumanDemoService] CGEventTap 创建失败（两种 tap 模式都不行，macOS 可能要求 Input Monitoring 权限）")
            return false
        }

        keyTapPort = validTap
        let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, validTap, 0)
        keyTapSource = source
        CFRunLoopAddSource(CFRunLoopGetCurrent(), source, .commonModes)
        CGEvent.tapEnable(tap: validTap, enable: true)
        print("[HumanDemoService] CGEventTap 键盘监听已启动")
        return true
    }

    private func stopEventMonitors() {
        if let m = mouseMonitor { NSEvent.removeMonitor(m); mouseMonitor = nil }
        if let k = keyMonitor { NSEvent.removeMonitor(k); keyMonitor = nil }
        if let source = keyTapSource {
            CFRunLoopRemoveSource(CFRunLoopGetCurrent(), source, .commonModes)
            keyTapSource = nil
        }
        if let tap = keyTapPort {
            CGEvent.tapEnable(tap: tap, enable: false)
            keyTapPort = nil
        }
    }

    /// 异步发送事件到后端 POST /demos/event（fire-and-forget）
    private func sendEvent(type: String, data: [String: Any]) {
        guard let url = URL(string: "\(baseURL)/demos/event") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 5
        let body: [String: Any] = [
            "session_id": "default",
            "event_type": type,
            "data": data,
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        // Fire-and-forget
        Task.detached {
            _ = try? await URLSession.shared.data(for: request)
        }
    }

    // MARK: - AX 语义辅助

    /// 获取指定位置元素的层级路径（从根到目标）
    private func getElementHierarchyPath(x: Float, y: Float) -> String {
        let systemWide = AXUIElementCreateSystemWide()
        var element: AXUIElement?
        let result = AXUIElementCopyElementAtPosition(systemWide, x, y, &element)
        guard result == .success, let elem = element else { return "" }

        var path: [String] = []
        var current: AXUIElement? = elem

        // 从当前元素向上遍历到 AXApplication
        for _ in 0..<10 {
            guard let el = current else { break }
            let role: String? = {
                var ref: AnyObject?
                AXUIElementCopyAttributeValue(el, kAXRoleAttribute as CFString, &ref)
                return ref as? String
            }()
            let title: String? = {
                var ref: AnyObject?
                AXUIElementCopyAttributeValue(el, kAXTitleAttribute as CFString, &ref)
                return ref as? String
            }()

            let roleStr = role ?? "?"
            let titleStr = (title != nil && !title!.isEmpty) ? "('\(title!)')" : ""
            path.insert("\(roleStr)\(titleStr)", at: 0)

            if roleStr == "AXApplication" { break }

            var parentRef: AnyObject?
            if AXUIElementCopyAttributeValue(el, kAXParentAttribute as CFString, &parentRef) == .success,
               let parent = parentRef {
                current = (parent as! AXUIElement)
            } else {
                break
            }
        }

        return path.joined(separator: " > ")
    }

    /// 检测焦点元素的文本变化（用于推断键盘输入）
    /// 在下一次点击时调用，比较当前焦点元素的 value 和上次记录的 value
    private func detectTextInput() {
        // 获取当前焦点元素
        let systemWide = AXUIElementCreateSystemWide()
        var focusedRef: AnyObject?
        AXUIElementCopyAttributeValue(systemWide, kAXFocusedUIElementAttribute as CFString, &focusedRef)

        guard let focused = focusedRef else { return }
        let focusedElement = focused as! AXUIElement

        // 读取当前值
        var valueRef: AnyObject?
        AXUIElementCopyAttributeValue(focusedElement, kAXValueAttribute as CFString, &valueRef)
        let currentValue = valueRef as? String ?? ""

        // 读取 role
        var roleRef: AnyObject?
        AXUIElementCopyAttributeValue(focusedElement, kAXRoleAttribute as CFString, &roleRef)
        let currentRole = roleRef as? String ?? ""

        // 如果值有变化且是文本输入区域，发送 text_input 事件
        let textRoles = ["AXTextField", "AXTextArea", "AXSearchField", "AXComboBox"]
        if !lastFocusedValue.isEmpty || !currentValue.isEmpty {
            if currentValue != lastFocusedValue && textRoles.contains(currentRole) {
                let typedText = currentValue
                let frontApp = NSWorkspace.shared.frontmostApplication
                let appName = frontApp?.localizedName ?? ""

                print("[HumanDemoService] 检测到文本输入: '\(typedText)' (role=\(currentRole))")

                Task { @MainActor [weak self] in
                    guard let self = self else { return }
                    self.localEventCount += 1
                    self.activeEventCount = self.localEventCount
                }

                self.sendEvent(type: "text_input", data: [
                    "typed_text": typedText,
                    "ui_role": currentRole,
                    "app_name": appName,
                ])
            }
        }
    }

    // MARK: - 权限引导

    /// 打开系统 Input Monitoring 权限设置
    func openInputMonitoringSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent") {
            NSWorkspace.shared.open(url)
        }
    }

    // MARK: - 演示管理

    func fetchDemos() async {
        guard let url = URL(string: "\(baseURL)/demos/list") else { return }
        isLoading = true
        defer { isLoading = false }

        do {
            let (data, _) = try await urlSession.data(from: url)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let demosArr = json["demos"] as? [[String: Any]] {
                demos = demosArr.compactMap { d in
                    guard let id = d["id"] as? String else { return nil }
                    return DemoSummary(
                        id: id,
                        task_description: d["task_description"] as? String ?? "",
                        status: d["status"] as? String ?? "",
                        event_count: d["event_count"] as? Int ?? 0,
                        step_count: d["step_count"] as? Int ?? 0,
                        created_at: d["created_at"] as? Double ?? 0,
                        duration_seconds: d["duration_seconds"] as? Double ?? 0,
                        tags: d["tags"] as? [String] ?? [],
                        generated_capsule_id: d["generated_capsule_id"] as? String ?? ""
                    )
                }
            }
        } catch {
            errorMessage = "获取演示列表失败: \(error.localizedDescription)"
        }
    }

    func deleteDemo(id: String) async {
        guard let url = URL(string: "\(baseURL)/demos/\(id)") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"

        do {
            let (_, _) = try await urlSession.data(for: request)
            demos.removeAll { $0.id == id }
        } catch {
            errorMessage = "删除失败: \(error.localizedDescription)"
        }
    }

    // MARK: - LLM 学习

    func learnFromDemo(id: String, autoApprove: Bool = false) async {
        guard let url = URL(string: "\(baseURL)/demos/\(id)/learn") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 120
        let body: [String: Any] = ["auto_approve": autoApprove]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        isLearning = true
        defer { isLearning = false }

        do {
            let (data, _) = try await urlSession.data(for: request)
            learnResult = try JSONDecoder().decode(DemoLearnResult.self, from: data)
            await fetchDemos()
        } catch {
            errorMessage = "LLM 学习失败: \(error.localizedDescription)"
        }
    }

    func approveCapsule(id: String) async -> DemoApproveResult? {
        guard let url = URL(string: "\(baseURL)/demos/\(id)/approve") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        do {
            let (data, _) = try await urlSession.data(for: request)
            let result = try JSONDecoder().decode(DemoApproveResult.self, from: data)
            if result.ok {
                await fetchDemos()
            }
            return result
        } catch {
            errorMessage = "审批失败: \(error.localizedDescription)"
            return nil
        }
    }
}
