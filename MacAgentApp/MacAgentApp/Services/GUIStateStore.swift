import Foundation
import ApplicationServices
import AppKit

// MARK: - ReadWriteLock

/// pthread_rwlock 包装器（并行读，互斥写）
final class ReadWriteLock {
    private var lock = pthread_rwlock_t()
    init() { pthread_rwlock_init(&lock, nil) }
    deinit { pthread_rwlock_destroy(&lock) }
    
    func readLock() { pthread_rwlock_rdlock(&lock) }
    func writeLock() { pthread_rwlock_wrlock(&lock) }
    func unlock() { pthread_rwlock_unlock(&lock) }
    
    func withReadLock<T>(_ body: () throws -> T) rethrows -> T {
        readLock(); defer { unlock() }; return try body()
    }
    func withWriteLock<T>(_ body: () throws -> T) rethrows -> T {
        writeLock(); defer { unlock() }; return try body()
    }
}

// MARK: - GUI State Models

/// 窗口状态
struct WindowState: Codable {
    let windowId: String
    let pid: Int32
    let appName: String
    let title: String
    var position: CGPointCodable?
    var size: CGSizeCodable?
    var focused: Bool
    var minimized: Bool
}

/// 元素索引条目
struct ElementEntry: Codable {
    let elementId: String
    let role: String
    let title: String
    let label: String
    let identifier: String
    let value: String
    let enabled: Bool
    let focused: Bool
    let position: CGPointCodable?
    let size: CGSizeCodable?
    let actions: [String]
    let parentId: String?
    let childIds: [String]?
}

/// GUI 完整状态快照
struct GUIState: Codable {
    let version: UInt64
    let timestamp: Double
    let focusedAppPid: Int32
    let focusedAppName: String
    let focusedWindowId: String?
    let focusedElementRole: String
    let focusedElementTitle: String
    let windows: [WindowState]
}

/// 状态差量（Diff）
struct GUIStateDiff: Codable {
    let fromVersion: UInt64
    let toVersion: UInt64
    let events: [AXEvent]
    let updatedWindows: [WindowState]?
    let focusChanged: Bool
}

// MARK: - GUIStateStore

/// GUI 状态缓存 — Swift 内维护唯一真相
/// 通过 AXObserver 事件增量更新，不做全量重建
class GUIStateStore {
    static let shared = GUIStateStore()
    
    /// 单调递增的版本号
    private(set) var version: UInt64 = 0
    
    /// 当前聚焦应用
    private(set) var focusedAppPid: pid_t = 0
    private(set) var focusedAppName: String = ""
    
    /// 当前聚焦窗口
    private(set) var focusedWindowTitle: String = ""
    
    /// 当前聚焦元素
    private(set) var focusedElementRole: String = ""
    private(set) var focusedElementTitle: String = ""
    
    /// 窗口状态表
    private var windowStates: [String: WindowState] = [:]
    
    /// 最近事件历史（环形缓冲）
    private var eventHistory: [AXEvent] = []
    private let maxHistory = 200
    
    /// 版本对应的事件，用于 diff
    private var versionEvents: [UInt64: [AXEvent]] = [:]
    private let maxVersionsKept = 50
    
    /// 历史快照环形缓冲区（最近 N 次完整快照）
    private var snapshotHistory: [GUIState] = []
    private let maxSnapshots = 20
    
    /// 读写锁（多 Agent 并发安全：并行读，互斥写）
    private let rwLock = ReadWriteLock()
    
    private init() {}
    
    // MARK: - Event Application
    
    /// 接收 AXObserver 事件并增量更新状态
    func applyEvent(_ event: AXEvent, element: AXUIElement) {
        rwLock.writeLock()
        defer { rwLock.unlock() }
        
        version += 1
        
        // 存入历史
        eventHistory.append(event)
        if eventHistory.count > maxHistory {
            eventHistory.removeFirst(eventHistory.count - maxHistory)
        }
        
        // 版本事件
        versionEvents[version] = [event]
        // 清理旧版本
        let minVersion = version > UInt64(maxVersionsKept) ? version - UInt64(maxVersionsKept) : 0
        versionEvents = versionEvents.filter { $0.key >= minVersion }
        
        // 根据事件类型更新缓存
        switch event.eventType {
        case kAXApplicationActivatedNotification as String:
            focusedAppPid = event.pid
            focusedAppName = event.appName
            
        case kAXApplicationDeactivatedNotification as String:
            if focusedAppPid == event.pid {
                focusedAppPid = 0
                focusedAppName = ""
            }
            
        case kAXFocusedWindowChangedNotification as String:
            focusedWindowTitle = event.elementTitle
            
        case kAXFocusedUIElementChangedNotification as String:
            focusedElementRole = event.elementRole
            focusedElementTitle = event.elementTitle
            
        case kAXWindowCreatedNotification as String:
            let windowId = "\(event.pid)_\(event.elementTitle)_\(version)"
            let ws = WindowState(
                windowId: windowId,
                pid: event.pid,
                appName: event.appName,
                title: event.elementTitle,
                position: nil,
                size: nil,
                focused: false,
                minimized: false
            )
            windowStates[windowId] = ws
            
        case kAXWindowMovedNotification as String,
             kAXWindowResizedNotification as String:
            updateWindowGeometry(element: element, pid: event.pid, title: event.elementTitle)
            
        case kAXUIElementDestroyedNotification as String:
            // 尝试清理窗口
            let prefix = "\(event.pid)_\(event.elementTitle)"
            windowStates = windowStates.filter { !$0.key.hasPrefix(prefix) }
            
        case kAXWindowMiniaturizedNotification as String:
            updateWindowMinimized(pid: event.pid, title: event.elementTitle, minimized: true)
            
        case kAXWindowDeminiaturizedNotification as String:
            updateWindowMinimized(pid: event.pid, title: event.elementTitle, minimized: false)
            
        default:
            break
        }
        
        // 每 10 版本自动保存一次快照（用于 undo/历史查询）
        if version % 10 == 0 {
            saveSnapshotLocked()
        }
    }
    
    /// 内部（已加锁时使用）：保存当前状态到历史
    private func saveSnapshotLocked() {
        let snap = GUIState(
            version: version,
            timestamp: Date().timeIntervalSince1970,
            focusedAppPid: focusedAppPid,
            focusedAppName: focusedAppName,
            focusedWindowId: nil,
            focusedElementRole: focusedElementRole,
            focusedElementTitle: focusedElementTitle,
            windows: Array(windowStates.values)
        )
        snapshotHistory.append(snap)
        if snapshotHistory.count > maxSnapshots {
            snapshotHistory.removeFirst(snapshotHistory.count - maxSnapshots)
        }
    }
    
    // MARK: - Query
    
    /// 获取完整的 GUI 状态快照
    func getSnapshot() -> GUIState {
        rwLock.readLock()
        defer { rwLock.unlock() }
        
        return GUIState(
            version: version,
            timestamp: Date().timeIntervalSince1970,
            focusedAppPid: focusedAppPid,
            focusedAppName: focusedAppName,
            focusedWindowId: nil,
            focusedElementRole: focusedElementRole,
            focusedElementTitle: focusedElementTitle,
            windows: Array(windowStates.values)
        )
    }
    
    /// 获取从某版本起的差量
    func getDiff(sinceVersion: UInt64) -> GUIStateDiff {
        rwLock.readLock()
        defer { rwLock.unlock() }
        
        var events: [AXEvent] = []
        for v in (sinceVersion + 1)...version {
            if let evts = versionEvents[v] {
                events.append(contentsOf: evts)
            }
        }
        
        let focusChanged = events.contains { e in
            e.eventType == (kAXApplicationActivatedNotification as String)
            || e.eventType == (kAXFocusedUIElementChangedNotification as String)
            || e.eventType == (kAXFocusedWindowChangedNotification as String)
        }
        
        return GUIStateDiff(
            fromVersion: sinceVersion,
            toVersion: version,
            events: events,
            updatedWindows: nil,
            focusChanged: focusChanged
        )
    }
    
    /// 获取最近 N 个事件
    func getRecentEvents(count: Int = 20) -> [AXEvent] {
        rwLock.readLock()
        defer { rwLock.unlock() }
        return Array(eventHistory.suffix(count))
    }
    
    /// 获取最近 N 个历史快照
    func getSnapshotHistory(count: Int = 10) -> [GUIState] {
        rwLock.readLock()
        defer { rwLock.unlock() }
        return Array(snapshotHistory.suffix(count))
    }
    
    /// 获取指定版本的历史快照（返回最接近且不超过该版本的快照）
    func getSnapshotAt(version targetVersion: UInt64) -> GUIState? {
        rwLock.readLock()
        defer { rwLock.unlock() }
        return snapshotHistory.last { $0.version <= targetVersion }
    }
    
    /// 手动触发保存当前快照
    func saveSnapshot() {
        rwLock.writeLock()
        defer { rwLock.unlock() }
        saveSnapshotLocked()
    }
    
    // MARK: - Internal Helpers
    
    private func updateWindowGeometry(element: AXUIElement, pid: pid_t, title: String) {
        let position = getPosition(element)
        let size = getSize(element)
        
        for (key, var ws) in windowStates where ws.pid == pid {
            if ws.title == title || title.isEmpty {
                ws.position = position
                ws.size = size
                windowStates[key] = ws
                return
            }
        }
    }
    
    private func updateWindowMinimized(pid: pid_t, title: String, minimized: Bool) {
        for (key, var ws) in windowStates where ws.pid == pid {
            if ws.title == title || title.isEmpty {
                ws.minimized = minimized
                windowStates[key] = ws
                return
            }
        }
    }
    
    private func getPosition(_ element: AXUIElement) -> CGPointCodable? {
        var value: AnyObject?
        let result = AXUIElementCopyAttributeValue(element, kAXPositionAttribute as CFString, &value)
        guard result == .success, let axValue = value else { return nil }
        var point = CGPoint.zero
        guard AXValueGetValue(axValue as! AXValue, .cgPoint, &point) else { return nil }
        return CGPointCodable(x: Double(point.x), y: Double(point.y))
    }
    
    private func getSize(_ element: AXUIElement) -> CGSizeCodable? {
        var value: AnyObject?
        let result = AXUIElementCopyAttributeValue(element, kAXSizeAttribute as CFString, &value)
        guard result == .success, let axValue = value else { return nil }
        var size = CGSize.zero
        guard AXValueGetValue(axValue as! AXValue, .cgSize, &size) else { return nil }
        return CGSizeCodable(width: Double(size.width), height: Double(size.height))
    }
}
