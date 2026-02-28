# iOS Agent App：后台任务与系统消息 - 技术方案

> 需求：iOS 端支持后台任务保持在线、后端可主动推送（如定时任务触发时），手机端新增「系统信息」栏目。

---

## 一、需求分析

| 需求 | 说明 |
|------|------|
| 后台任务 | 应用退到后台时尽量保持连接或能及时恢复，以便接收服务端推送 |
| 后端主动推送 | 后端通过 WebSocket 主动下发消息（如定时任务触发、系统通知） |
| 系统信息栏目 | 手机端新增「系统信息」入口，集中展示收到的系统消息 |

---

## 二、现状

### 2.1 后端能力（已具备）

- **WebSocket 广播**：`connection_manager.broadcast_all()` 可向所有在线客户端推送
- **系统消息服务**：`SystemMessageService` 存储系统消息，并通过 `_push()` 广播 `system_notification` 类型
- **消息格式**：
  ```json
  {
    "type": "system_notification",
    "notification": {
      "id": "uuid",
      "level": "info|warning|error",
      "title": "标题",
      "content": "内容",
      "source": "来源",
      "category": "system_error|evolution|task|info",
      "timestamp": "ISO8601",
      "read": false
    },
    "unread_count": 3
  }
  ```
- **触发场景**：自主任务完成/错误、工具升级、自愈、定时任务等均可调用 `add_info/add_warning/add_error` 推送

### 2.2 iOS 现状

- **WebSocket**：`WebSocketService` 已解析 `system_notification`，通过 delegate 回调 `didReceiveSystemNotification:unreadCount:`
- **ChatViewController**：仅 `NSLog` 打印，**无 UI 展示**
- **后台**：无 Background Modes，退到后台后 WebSocket 会被系统挂起，连接断开

---

## 三、技术方案

### 3.1 后台任务（保持在线）

iOS 对后台网络有严格限制，无法像 Mac 一样长期保持 WebSocket。采用组合策略：

| 能力 | 作用 | 实现 |
|------|------|------|
| **Background Task** | 退到后台时争取约 3 分钟完成收尾 | `beginBackgroundTaskWithName` |
| **BGAppRefreshTask** | 系统在合适时机唤醒 App 做短暂刷新 | `BGTaskScheduler` 注册 `com.macagent.ios.refresh` |
| **快速重连** | 回到前台时立即重连 | 已有 `viewDidAppear` 中 `connect` |

**说明**：

- WebSocket 在后台会被挂起，无法长期保持。BGAppRefreshTask 由系统调度（通常 15–30 分钟一次），唤醒后短暂运行，可重连、拉取未读系统消息并展示本地通知。
- 若需「强实时」推送（如秒级），需引入 APNs，后端在关键事件时发 Push，iOS 收到后唤醒并处理。本方案先不涉及 APNs。

### 3.2 后端主动推送（沿用现有能力）

- 后端已通过 `system_notification` 广播，无需改动
- 定时任务、自主任务完成等场景，继续使用 `SystemMessageService.add_*` 即可
- iOS 端需：1）持久化收到的系统消息；2）在「系统信息」栏目展示

### 3.3 系统信息栏目

| 模块 | 职责 |
|------|------|
| **SystemMessage**（Model） | 本地系统消息模型，与后端 JSON 对应 |
| **SystemMessageStore** | 本地持久化（UserDefaults 或 JSON 文件） |
| **SystemMessagesViewController** | 列表展示系统消息，支持分类、已读/未读 |
| **入口** | 导航栏按钮（如铃铛图标 + 未读数角标） |

---

## 四、实现清单

### 4.1 Info.plist

- 添加 `UIBackgroundModes` → `fetch`（用于 BGAppRefreshTask）

### 4.2 AppDelegate

- 注册 `BGAppRefreshTask` 标识符
- 在 `application:didFinishLaunchingWithOptions:` 中调用 `BGTaskScheduler` 注册

### 4.3 后台任务服务（新建）

- `BackgroundTaskService`：封装 `beginBackgroundTask`、`BGAppRefreshTask` 调度
- 刷新任务逻辑：重连 WebSocket → 等待几秒收包 → 如有新系统消息则发本地通知 → 结束任务

### 4.4 系统消息模块（新建）

- `SystemMessage.h/m`：模型（id, level, title, content, source, category, timestamp, read）
- `SystemMessageStore.h/m`：增删改查 + 持久化
- `SystemMessagesViewController.h/m`：列表 UI，按时间倒序，支持分类筛选、标记已读

### 4.5 WebSocketService 与 ChatViewController

- `didReceiveSystemNotification`：将消息写入 `SystemMessageStore`，并通知 UI 更新（角标等）
- 在 ChatViewController 导航栏增加「系统信息」入口（铃铛 + 未读数）

### 4.6 本地化

- 新增 `system_messages`、`system_message_title` 等文案

---

## 五、数据流

```
后端定时任务/自主任务完成
    → SystemMessageService.add_info/add_warning/add_error
    → broadcast_all(system_notification)
    → iOS WebSocket 收到
    → SystemMessageStore 持久化
    → 更新角标、刷新系统信息列表
```

---

## 六、依赖与限制

- **iOS 版本**：保持 iOS 15.0+（BGTaskScheduler 需 iOS 13+）
- **后台刷新**：系统决定唤醒时机，无法保证固定间隔
- **无 APNs**：不依赖推送证书，纯 WebSocket + 本地通知，实时性依赖前台或 BG 刷新

---

## 七、确认事项

请确认以下点后再进入编码：

1. **后台策略**：是否接受「BGAppRefreshTask + 退后台 3 分钟延长时间」的组合，而不引入 APNs？
2. **系统信息入口**：是否采用导航栏铃铛图标 + 未读角标，点击进入系统信息列表？
3. **分类展示**：是否需要在系统信息列表内按 category（系统错误、进化、任务、其他）做 Tab 或筛选？

确认后即可按此方案实施。
