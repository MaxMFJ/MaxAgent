# iOS 端 WebSocket 协议更新日志

## 更新日期：2026-02-26

## 更新原因
后台 WebSocket 协议进行了升级，iOS 端需要同步更新以支持最新的协议特性和消息类型。

---

## 一、新增客户端发送消息类型

### 1. `resume_chat` - 恢复 Chat 流任务
**用途**：断线重连后恢复中断的 chat 对话流

**发送时机**：
- 客户端重连后收到 `connected` 消息
- `connected.has_running_chat` 为 `true` 时自动发送

**消息格式**：
```json
{
  "type": "resume_chat",
  "session_id": "conversation_id"
}
```

**响应消息**：
- `resume_chat_result` - 恢复结果
- `resume_chat_streaming` - 开始恢复流式输出
- 后续流式 chunk（`content`, `tool_call`, `tool_result` 等）

---

## 二、新增服务端响应消息类型

### 1. `web_augmentation` - 网络增强思考
**说明**：Agent 使用网络搜索增强回答时发送

**字段**：
```json
{
  "type": "web_augmentation",
  "augmentation_type": "search|browse",
  "query": "搜索关键词",
  "success": true
}
```

**iOS 处理**：在日志中记录，可选择性显示给用户

---

### 2. `execution_log` - 工具执行日志
**说明**：工具执行过程中的详细日志

**字段**：
```json
{
  "type": "execution_log",
  "tool_name": "read_file",
  "action_id": "action_123",
  "level": "info|warning|error",
  "message": "日志内容"
}
```

**iOS 处理**：
- 目前仅记录到控制台
- 未来可扩展为在 UI 中展示工具执行详情

---

### 3. `system_notification` - 系统通知
**说明**：服务端推送的系统级通知（升级完成、错误提醒等）

**字段**：
```json
{
  "type": "system_notification",
  "notification": {
    "id": "msg_id",
    "title": "通知标题",
    "content": "通知内容",
    "category": "SYSTEM_ERROR|EVOLUTION|...",
    "timestamp": "2026-02-26T10:00:00",
    "read": false
  },
  "unread_count": 5
}
```

**iOS 处理**：
- 目前仅记录
- 未来可实现通知中心功能

---

### 4. `tools_updated` - 工具列表更新
**说明**：服务端工具列表发生变化时广播

**字段**：
```json
{
  "type": "tools_updated"
}
```

**iOS 处理**：
- 接收通知后可刷新工具列表
- 目前仅记录日志

---

### 5. `resume_chat_result` - Chat 恢复结果
**说明**：`resume_chat` 请求的响应

**成功情况**：
```json
{
  "type": "resume_chat_result",
  "session_id": "conversation_id",
  "found": true,
  "task_id": "chat_xxx",
  "status": "running|completed",
  "buffered_count": 15
}
```

**失败情况**：
```json
{
  "type": "resume_chat_result",
  "session_id": "conversation_id",
  "found": false,
  "message": "没有找到该会话的 chat 任务记录"
}
```

---

### 6. `resume_chat_streaming` - Chat 恢复流式开始
**说明**：服务端开始回放缓冲的 chat chunk

**字段**：
```json
{
  "type": "resume_chat_streaming",
  "task_id": "chat_xxx",
  "message": "Chat 任务仍在执行中，后续输出将实时推送"
}
```

---

## 三、协议字段增强

### 1. `connected` 消息增强
**原有字段**：
- `client_id`
- `session_id`
- `has_running_task`
- `running_task_id`

**新增字段**：
- `has_running_chat`: `boolean` - 是否有运行中的 chat 流
- `running_chat_task_id`: `string?` - 运行中的 chat 任务 ID
- `server_status`: `string` - 服务端状态（normal/busy/upgrading）
- `unread_system_messages`: `number` - 未读系统消息数
- `clients_in_session`: `string[]` - 当前会话中的所有客户端 ID

**更新说明**：
- iOS 端现在会在收到 `connected` 时检查 `has_running_chat`
- 如果为 `true` 且当前会话匹配，自动发送 `resume_chat` 请求

---

### 2. `done` 消息增强
**原有字段**：
- `model`: `string?` - 使用的模型名称

**新增字段**：
```json
{
  "type": "done",
  "model": "gpt-4o",
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 300,
    "total_tokens": 450
  }
}
```

**iOS 处理**：
- 现在会记录 token 使用量
- 可在未来扩展为显示成本统计

---

## 四、代码变更清单

### 4.1 WebSocketService.h
**新增委托方法**：
```objective-c
// Token 使用量
- (void)webSocketServiceDidCompleteSend:(WebSocketService *)service 
                               modelName:(nullable NSString *)modelName 
                              tokenUsage:(nullable NSDictionary<NSString *, NSNumber *> *)tokenUsage;

// 连接增强
- (void)webSocketService:(WebSocketService *)service 
    didConnectWithClientId:(NSString *)clientId 
                 sessionId:(NSString *)sessionId 
           hasRunningTask:(BOOL)hasRunningTask 
            runningTaskId:(nullable NSString *)runningTaskId 
          hasRunningChat:(BOOL)hasRunningChat;

// 新消息类型
- (void)webSocketService:(WebSocketService *)service 
  didReceiveWebAugmentation:(NSString *)augmentationType 
                      query:(NSString *)query;

- (void)webSocketService:(WebSocketService *)service 
  didReceiveExecutionLog:(NSString *)toolName 
                   level:(NSString *)level 
                 message:(NSString *)message;

- (void)webSocketService:(WebSocketService *)service 
  didReceiveSystemNotification:(NSDictionary *)notification 
                   unreadCount:(NSInteger)unreadCount;

- (void)webSocketServiceDidReceiveToolsUpdated:(WebSocketService *)service;

- (void)webSocketService:(WebSocketService *)service 
     didResumeChatWithId:(NSString *)taskId 
           bufferedCount:(NSInteger)bufferedCount;
```

**新增方法**：
```objective-c
- (void)resumeChat:(NSString *)sessionId;
```

---

### 4.2 WebSocketService.m
**新增实现**：
1. `resumeChat:` - 发送 resume_chat 消息
2. 在 `handleStringMessage:` 中添加对以下类型的处理：
   - `web_augmentation`
   - `execution_log`
   - `system_notification`
   - `tools_updated`
   - `resume_chat_result`
   - `resume_chat_streaming`
3. 更新 `connected` 消息解析，提取新增字段
4. 更新 `done` 消息解析，提取 token usage

---

### 4.3 ChatViewController.m
**更新委托实现**：
1. `didConnectWithClientId:sessionId:hasRunningTask:runningTaskId:hasRunningChat:`
   - 检测 `hasRunningChat`
   - 自动调用 `resumeChat:` 恢复会话
2. `webSocketServiceDidCompleteSend:modelName:tokenUsage:`
   - 记录 token 使用量
3. 新增空实现（仅日志记录）：
   - `didReceiveWebAugmentation:query:`
   - `didReceiveExecutionLog:level:message:`
   - `didReceiveSystemNotification:unreadCount:`
   - `webSocketServiceDidReceiveToolsUpdated:`
   - `didResumeChatWithId:bufferedCount:`

---

## 五、测试建议

### 5.1 断线重连 Chat 恢复
**测试步骤**：
1. 发起一个较长的对话（确保会持续几秒）
2. 在对话进行中断开 Wi-Fi
3. 立即重新连接 Wi-Fi
4. 观察是否自动恢复对话输出

**预期行为**：
- 重连后自动发送 `resume_chat`
- 收到 `resume_chat_result` 成功响应
- 继续显示缓冲的 chunk 和后续输出

---

### 5.2 Token 使用量显示
**测试步骤**：
1. 发送一条消息并等待完成
2. 查看控制台日志

**预期日志**：
```
[Chat] Token usage: 450
```

---

### 5.3 Web 增强功能
**测试步骤**：
1. 询问需要实时信息的问题（如"今天天气如何"）
2. 观察控制台日志

**预期日志**：
```
[Chat] Web augmentation: type=search, query=今天天气
```

---

## 六、向后兼容性

### 兼容性说明
- ✅ **向后兼容**：所有新增字段和消息类型均为可选
- ✅ **优雅降级**：如果后台不发送新字段，iOS 端不会崩溃
- ✅ **旧版本后台**：iOS 端可以与旧版本后台正常通信，只是不支持新特性

### 检查点
- [x] 新增的委托方法都标记为 `@optional`
- [x] 消息字段解析使用安全的 `json[@"key"]` 语法
- [x] 缺失字段时使用合理的默认值（如 `?: @""`, `boolValue` 等）

---

## 七、未来扩展建议

### 7.1 系统通知中心
- 在 UI 中实现通知列表
- 支持标记已读
- 分类展示（系统错误、进化日志、工具更新）

### 7.2 工具执行详情
- 在消息气泡中展开显示工具执行日志
- 区分 info/warning/error 级别
- 支持折叠/展开

### 7.3 Token 成本统计
- 记录每条消息的 token 使用量
- 展示对话总成本
- 不同模型的价格计算

### 7.4 Web 增强提示
- 显示"正在搜索..."加载状态
- 展示搜索查询内容
- 标记"包含网络搜索结果"

---

## 八、相关文档
- [后台 WebSocket 协议文档](../backend/ws_handler.py)
- [Mac 端协议实现参考](../MacAgentApp/MacAgentApp/Services/BackendService.swift)
- [iOS 端上下文污染解决方案](./iOS端上下文污染解决方案.md)

---

## 九、变更总结

### 新增功能
1. ✅ Chat 断线重连自动恢复
2. ✅ Token 使用量统计
3. ✅ Web 增强思考支持
4. ✅ 工具执行日志记录
5. ✅ 系统通知接收（基础）
6. ✅ 工具更新通知

### 协议完整性
- **客户端发送**: 8/14 完全支持（聊天、任务、会话管理）
- **服务端响应**: 15/20+ 完全支持（核心功能）

### 开发状态
- ✅ 核心协议更新完成
- ✅ 代码编译通过
- ⏳ 实际设备测试待进行
- ⏳ UI 展示优化待扩展

---

**最后更新**：2026-02-26  
**更新人**：iOS Agent  
**版本**：v2.0
