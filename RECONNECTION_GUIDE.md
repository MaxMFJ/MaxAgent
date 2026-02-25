# 断线重连 + 任务恢复功能说明

## 功能概述

实现了 WebSocket 断线重连后自动恢复正在执行的自主任务（autonomous task）功能。即使客户端断线，服务端任务仍会在后台继续执行，客户端重连后可恢复实时输出。

---

## 服务端改动（Backend）

### 1. `app_state.py` - 任务追踪器

新增 `AutoTaskStatus` 枚举和 `TaskTracker` 类：

```python
class AutoTaskStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    STOPPED = "stopped"

class TaskTracker:
    """
    管理所有自主任务的生命周期。
    任务与 session_id 关联，断线后可通过 session_id 恢复。
    """
    - register(task_id, session_id, description, asyncio_task)
    - record_chunk(task_id, chunk)  # 缓冲最近 500 条输出
    - finish(task_id, status)
    - get_by_session(session_id)
    - get_buffered_chunks(task_id)
```

### 2. `ws_handler.py` - 核心改动

#### (1) autonomous_task 改为非阻塞

- 原来：`await autonomous_agent.run_autonomous()` **阻塞**主循环，导致无法处理 ping/pong
- 现在：`asyncio.create_task(_autonomous_task_worker())` 后台执行，主循环继续

#### (2) 新增 `resume_task` 消息处理

```python
async def _handle_resume_task(message, websocket, session_id):
    tracker = get_task_tracker()
    tt = tracker.get_by_session(session_id)
    
    if tt:
        # 回放缓冲的历史 chunks
        for chunk in tracker.get_buffered_chunks(tt.task_id):
            await safe_send_json(websocket, chunk)
        
        # 后续输出通过 session 广播自动送达
```

#### (3) 服务端心跳

- 每 30 秒发送 `server_ping`，客户端回复 `pong`
- 配合 uvicorn 的 `ws_ping_interval=30` 双向保活

### 3. `main.py` - uvicorn 配置

```python
uvicorn.run(
    ws_ping_interval=30,  # 原来是 None
    ws_ping_timeout=60,
)
```

---

## macOS 客户端改动（Swift）

### 1. `BackendService.swift`

#### 新增属性

```swift
private var currentSessionId: String?
private var hasRunningTask: Bool = false
private var runningTaskId: String?
var onTaskDetected: ((Bool, String?) -> Void)?
```

#### 连接时监听 `connected` 消息

```swift
func connect() async {
    // ...
    await listenForConnectedMessage()  // 新增
}

private func listenForConnectedMessage() async {
    // 解析 connected 消息，检查 has_running_task
    if hasRunningTask {
        onTaskDetected?(hasRunningTask, runningTaskId)
    }
}
```

#### 新增 `resumeTask` 方法

```swift
func resumeTask(sessionId: String) -> AsyncThrowingStream<StreamChunk, Error> {
    // 发送 resume_task 消息
    // 接收历史 chunks + 实时流
}
```

#### 处理新消息类型

- `server_ping` → 回复 `pong`
- `autonomous_task_accepted` → 任务已接受
- `resume_result` → 恢复结果
- `resume_streaming` → 历史回放完成

### 2. `AgentViewModel.swift`

#### 订阅任务检测回调

```swift
backendService.onTaskDetected = { [weak self] hasRunningTask, taskId in
    if hasRunningTask {
        Task {
            await self?.resumeAutonomousTask(sessionId: sessionId, taskId: taskId)
        }
    }
}
```

#### 新增恢复方法

```swift
private func resumeAutonomousTask(sessionId: String, taskId: String?) async {
    // 调用 backendService.resumeTask()
    // 处理回放的历史 chunks
    // 显示恢复进度
}
```

---

## iOS 客户端改动（Objective-C）

### 1. `WebSocketService.h`

#### 新增属性

```objc
@property (nonatomic, assign) BOOL hasRunningTask;
@property (nonatomic, copy, nullable) NSString *runningTaskId;
```

#### 新增代理方法

```objc
- (void)webSocketService:(WebSocketService *)service 
      didDetectRunningTask:(NSString *)taskId;

- (void)webSocketService:(WebSocketService *)service 
      didResumeTaskWithId:(NSString *)taskId 
              description:(NSString *)taskDescription;

- (void)webSocketService:(WebSocketService *)service 
          taskResumeDidFail:(NSString *)message;
```

#### 新增方法

```objc
- (void)resumeTask:(NSString *)sessionId;
```

### 2. `WebSocketService.m`

#### 处理 `connected` 消息

```objc
if ([type isEqualToString:@"connected"]) {
    self.hasRunningTask = [json[@"has_running_task"] boolValue];
    self.runningTaskId = json[@"running_task_id"];
    
    if (self.hasRunningTask && self.runningTaskId) {
        [self.delegate webSocketService:self 
                    didDetectRunningTask:self.runningTaskId];
    }
}
```

#### 处理新消息类型

```objc
else if ([type isEqualToString:@"server_ping"]) {
    [self sendJSONMessage:@{@"type": @"pong"}];
}
else if ([type isEqualToString:@"autonomous_task_accepted"]) {
    // 任务已接受
}
else if ([type isEqualToString:@"resume_result"]) {
    BOOL found = [json[@"found"] boolValue];
    if (found) {
        [self.delegate webSocketService:self 
                      didResumeTaskWithId:json[@"task_id"]
                              description:json[@"task_description"]];
    } else {
        [self.delegate webSocketService:self 
                        taskResumeDidFail:json[@"message"]];
    }
}
```

#### 实现 `resumeTask` 方法

```objc
- (void)resumeTask:(NSString *)sessionId {
    NSDictionary *message = @{
        @"type": @"resume_task",
        @"session_id": sessionId ?: [ServerConfig sharedConfig].sessionId
    };
    [self sendJSONMessage:message];
}
```

---

## 使用流程

### 客户端视角

1. **启动 App 并连接**
   - 收到 `connected` 消息
   - 检查 `has_running_task` 字段

2. **检测到运行中任务**
   - iOS: 触发 `didDetectRunningTask:` 回调
   - macOS: 触发 `onTaskDetected` 闭包

3. **自动恢复任务**
   - 调用 `resumeTask(sessionId)`
   - 服务端回放历史输出（最多 500 条 chunks）
   - 后续输出实时推送

4. **任务继续执行**
   - 客户端显示恢复进度
   - 用户可继续查看任务执行

### 服务端视角

1. **任务启动**
   - 注册到 `TaskTracker`
   - 每个 chunk 缓冲到 `TrackedTask.chunks`（deque, maxlen=500）

2. **客户端断线**
   - 任务仍在后台 `asyncio.Task` 中继续执行
   - 输出通过 `broadcast_to_session` 广播（但此时无客户端在线）

3. **客户端重连**
   - 发送 `connected`，包含 `has_running_task` 和 `running_task_id`
   - 客户端发送 `resume_task`
   - 回放缓冲的历史 chunks
   - 后续输出继续广播

---

## 测试方法

1. **启动后端**
   ```bash
   cd backend && ./start.sh
   ```

2. **连接客户端并启动自主任务**
   - macOS: 点击"自主执行"按钮，输入任务
   - iOS: 点击"🤖"按钮，输入任务

3. **模拟断线**
   - 关闭 App（macOS: Cmd+Q，iOS: 上滑退出）
   - 或者断开网络

4. **重新打开 App**
   - 客户端应自动检测到运行中的任务
   - 显示 "🔄 检测到任务正在运行，正在恢复..."
   - 历史输出回放
   - 后续输出实时推送

5. **验证任务继续执行**
   - 检查服务端日志，任务应未中断
   - 客户端应能看到完整的任务执行过程

---

## 注意事项

1. **缓冲限制**：只保留最近 500 条 chunks，超长任务可能丢失早期输出
2. **会话绑定**：任务与 `session_id` 绑定，换会话无法恢复
3. **服务端重启**：服务端重启后所有任务状态丢失（未持久化到磁盘）
4. **并发任务**：同一 session 同时只能有一个自主任务运行

---

## 新增消息类型总结

### 服务端 → 客户端

| 消息类型 | 字段 | 说明 |
|---------|------|------|
| `connected` | `has_running_task`, `running_task_id` | 连接成功，告知是否有运行中任务 |
| `autonomous_task_accepted` | `task_id`, `session_id` | 任务已接受 |
| `server_ping` | `timestamp` | 服务端心跳 |
| `resume_result` | `found`, `task_id`, `task_description`, `status`, `buffered_count` | 恢复结果 |
| `resume_streaming` | `task_id`, `message` | 历史回放完成，开始实时流 |

### 客户端 → 服务端

| 消息类型 | 字段 | 说明 |
|---------|------|------|
| `resume_task` | `session_id` | 请求恢复任务 |
| `pong` | - | 回复服务端心跳 |

---

## 文件清单

### 服务端
- ✅ `backend/app_state.py` - 新增 TaskTracker
- ✅ `backend/ws_handler.py` - 非阻塞任务 + resume_task 处理
- ✅ `backend/main.py` - uvicorn ping 配置

### macOS 客户端
- ✅ `MacAgentApp/MacAgentApp/Services/BackendService.swift`
- ✅ `MacAgentApp/MacAgentApp/ViewModels/AgentViewModel.swift`

### iOS 客户端
- ✅ `iOSAgentApp/iOSAgentApp/Services/WebSocketService.h`
- ✅ `iOSAgentApp/iOSAgentApp/Services/WebSocketService.m`

---

**完成时间**: 2026-02-25  
**作者**: Cursor AI Assistant
