# MacAgent iOS 客户端

Objective-C 编写的 iOS 聊天客户端，用于远程连接 Mac 上的 MacAgent 后端服务。

## 功能特性

- WebSocket 实时通信
- 流式消息显示
- 工具调用状态展示
- 扫码连接配置
- Token 认证支持
- 自动重连机制

## 系统要求

- iOS 15.0+
- Xcode 15.0+

## 项目结构

```
iOSAgentApp/
├── AppDelegate.h/m          # 应用代理
├── SceneDelegate.h/m        # 场景代理
├── main.m                   # 入口
├── Services/
│   └── WebSocketService.h/m # WebSocket 通信服务
├── Models/
│   ├── Message.h/m          # 消息模型
│   └── ServerConfig.h/m     # 服务器配置
├── ViewControllers/
│   ├── ChatViewController.h/m    # 聊天主界面
│   └── SettingsViewController.h/m # 设置界面
├── Views/
│   ├── MessageCell.h/m      # 消息单元格
│   └── InputView.h/m        # 输入栏
└── Resources/
    ├── Assets.xcassets      # 资源文件
    └── LaunchScreen.storyboard
```

## 使用方法

### 1. 在 Mac 上启动后端和 Tunnel

1. 启动 MacAgent 后端服务
2. 打开 MacAgent 设置 -> 远程
3. 点击「启动 Tunnel」
4. 等待生成公网地址和二维码

### 2. 在 iOS 上连接

1. 打开 iOSAgentApp
2. 点击设置图标
3. 扫描 Mac 上显示的二维码，或手动输入地址
4. 点击「Connect」
5. 开始聊天！

## 通信协议

### WebSocket 连接

```
wss://xxx.trycloudflare.com/ws?client_type=ios&token=xxx
```

### 消息格式

发送聊天消息：
```json
{
  "type": "chat",
  "content": "你好",
  "session_id": "xxx"
}
```

接收内容流：
```json
{
  "type": "content",
  "content": "你好！"
}
```

工具调用：
```json
{
  "type": "tool_call",
  "name": "screenshot",
  "call_id": "xxx",
  "arguments": "{}"
}
```

## 开发说明

项目使用 Objective-C 编写，采用 UIKit 框架。

### WebSocket 实现

使用 `NSURLSessionWebSocketTask` (iOS 13+) 原生 WebSocket 支持：

- 自动心跳保活 (10秒间隔)
- 断线自动重连 (指数退避)
- JSON 消息序列化

### 界面实现

- `ChatViewController`: UITableView + 自定义 cell
- `InputView`: 自适应高度的输入框
- `MessageCell`: 气泡样式消息

## License

MIT
iOS App 多 Agent 协作的 WebSocket 实现分析报告
一、相关文件路径列表
iOS 客户端核心文件
WebSocket 通信层：
- /iOSAgentApp/iOSAgentApp/Services/WebSocketService.h - WebSocket 服务接口定义
- /iOSAgentApp/iOSAgentApp/Services/WebSocketService.m - WebSocket 实现（663行）
消息和会话管理：
- /iOSAgentApp/iOSAgentApp/Models/Message.h/m - 消息模型
- /iOSAgentApp/iOSAgentApp/Models/Conversation.h/m - 会话模型
- /iOSAgentApp/iOSAgentApp/Models/ConversationManager.h/m - 会话管理器
Agent 协作相关：
- /iOSAgentApp/iOSAgentApp/Models/Duck.h/m - Duck（子Agent）模型
- /iOSAgentApp/iOSAgentApp/Models/ActionLogEntry.h/m - 任务执行日志和进度
- /iOSAgentApp/iOSAgentApp/Services/DuckApiService.h/m - Duck API 服务
UI 层：
- /iOSAgentApp/iOSAgentApp/ViewControllers/ChatViewController.h/m - 主聊天界面（1807行）
- /iOSAgentApp/iOSAgentApp/Views/AgentLiveView.h/m - Agent 实时执行面板
- /iOSAgentApp/iOSAgentApp/Views/TaskProgressView.h/m - 任务进度视图
- /iOSAgentApp/iOSAgentApp/Views/MessageCell.h/m - 消息展示单元
后端服务文件
WebSocket 处理：
- /backend/ws_handler.py - WebSocket 主处理器（1653行）
- /backend/connection_manager.py - 连接管理器（239行）
任务调度：
- /backend/services/duck_task_scheduler.py - Duck 任务调度器
- /backend/services/duck_protocol.py - Duck 协议定义
- /backend/services/duck_registry.py - Duck 注册表
工具：
- /backend/tools/delegate_duck_tool.py - Duck 委派工具
- /backend/tools/duck_status_tool.py - Duck 状态查询工具
---
二、关键代码片段
1. WebSocket 连接和消息处理
iOS 端连接建立（WebSocketService.m）：
- (void)connect {
    if (self.connectionState == WebSocketConnectionStateConnecting || 
        self.connectionState == WebSocketConnectionStateConnected) {
        return;
    }
    
    NSURL *url = [[ServerConfig sharedConfig] webSocketURL];
    self.shouldReconnect = YES;
    [self updateConnectionState:WebSocketConnectionStateConnecting];
    
    self.webSocketTask = [self.session webSocketTaskWithURL:url];
    [self.webSocketTask resume];
    [self receiveMessage];
}
- (void)receiveMessage {
    __weak typeof(self) weakSelf = self;
    [self.webSocketTask receiveMessageWithCompletionHandler:^(NSURLSessionWebSocketMessage *message, NSError *error) {
        __strong typeof(weakSelf) strongSelf = weakSelf;
        if (error) {
            [strongSelf handleDisconnection];
            return;
        }
        if (message.type == NSURLSessionWebSocketMessageTypeString) {
            [strongSelf handleStringMessage:message.string];
        }
        [strongSelf receiveMessage];  // 递归接收下一条消息
    }];
}
消息分发处理（WebSocketService.m 303-595行）：
- (void)handleStringMessage:(NSString *)string {
    NSData *data = [string dataUsingEncoding:NSUTF8StringEncoding];
    NSDictionary *json = [NSJSONSerialization JSONObjectWithData:data options:0 error:&error];
    NSString *type = json[@"type"];
    
    if ([type isEqualToString:@"connected"]) {
        // 连接确认，包含 session_id, has_running_task 等
        self.clientId = json[@"client_id"];
        self.sessionId = json[@"session_id"];
        self.hasRunningTask = json[@"has_running_task"];
        [self.delegate webSocketService:self didConnectWithClientId:...];
    }
    else if ([type isEqualToString:@"content"]) {
        // 流式内容
        [self.delegate webSocketService:self didReceiveContent:content];
    }
    else if ([type isEqualToString:@"duck_task_complete"]) {
        // Duck 任务完成广播
        [self.delegate webSocketService:self 
            didReceiveDuckTaskComplete:content 
            success:success 
            sessionId:sessionId];
    }
    // ... 其他消息类型处理
}
2. Duck 任务完成通知机制
后端广播 duck_task_complete（ws_handler.py 123-131行）：
async def _run_agent_and_broadcast_result(session_id, prompt, chat_runner, task_id, label="Duck"):
    """
    运行主 Agent，收集完整响应后作为 duck_task_complete 广播。
    解决：run_stream 产生的 chunk 消息在客户端空闲 WS 循环中无法被处理的问题。
    """
    full_text = ""
    tool_calls_used = []
    
    async for chunk in chat_runner.run_stream(prompt, session_id=session_id):
        if chunk.get("type") == "chunk":
            full_text += chunk.get("content", "")
        elif chunk.get("type") == "tool_call":
            tool_calls_used.append(chunk.get("tool_name", ""))
    
    # 作为 duck_task_complete 发送（Mac 客户端在 idle 状态时能正确接收）
    await connection_manager.broadcast_to_session(session_id, {
        "type": "duck_task_complete",
        "task_id": task_id,
        "success": True,
        "content": summary_content,
        "session_id": session_id,
        "duck_id": label,
    })
iOS 端接收处理（ChatViewController.m 1363-1390行）：
- (void)webSocketService:(WebSocketService *)service 
    didReceiveDuckTaskComplete:(NSString *)content 
    success:(BOOL)success 
    sessionId:(NSString *)sessionId {
    
    dispatch_async(dispatch_get_main_queue(), ^{
        ConversationManager *manager = [ConversationManager sharedManager];
        Conversation *conv = nil;
        
        // 根据 session_id 查找对应会话
        for (Conversation *c in manager.conversations) {
            if ([c.conversationId isEqualToString:sessionId]) {
                conv = c;
                break;
            }
        }
        
        if (!conv) return;
        
        // 创建新的 assistant 消息
        Message *msg = [Message assistantMessage];
        msg.content = content;
        msg.status = success ? MessageStatusComplete : MessageStatusError;
        msg.modelName = @"Duck";
        [conv.messages addObject:msg];
        
        conv.updatedAt = [NSDate date];
        [manager saveConversations];
        
        // 更新 UI
        if (manager.currentConversation == conv) {
            [self.tableView reloadData];
            [self scrollToBottom];
        }
    });
}
3. Chat 消息更新逻辑
流式内容节流更新（ChatViewController.m 1041-1101行）：
- (void)webSocketService:(WebSocketService *)service didReceiveContent:(NSString *)content {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.currentAssistantMessage) {
            [self.currentAssistantMessage appendContent:content];
            [self throttledUpdateStreamingCell];  // 节流更新
        }
    });
}
// 节流更新：每 180ms 最多刷新一次，避免阻塞主线程
- (void)throttledUpdateStreamingCell {
    NSDate *now = [NSDate date];
    if (self.lastStreamingUIUpdateTime && 
        [now timeIntervalSinceDate:self.lastStreamingUIUpdateTime] < 0.18) {
        // 节流期间：标记有待更新，稍后触发
        if (!self.hasPendingStreamingUpdate) {
            self.hasPendingStreamingUpdate = YES;
            dispatch_after(..., ^{
                [self flushStreamingCellUpdate];
            });
        }
        return;
    }
    [self flushStreamingCellUpdate];
}
- (void)flushStreamingCellUpdate {
    // TTS 处理
    if ([[NSUserDefaults standardUserDefaults] boolForKey:kUserDefaultsTTSEnabled]) {
        [[TTSService sharedService] appendAndSpeakStreamedContent:full];
    }
    
    // 直接更新 cell 内容，避免 reloadRows 丢失缓存
    MessageCell *cell = [self.tableView cellForRowAtIndexPath:indexPath];
    if (cell) {
        [cell configureWithMessage:self.currentAssistantMessage];
    }
    
    // 每 6 次节流更新才刷新行高
    self.streamingHeightUpdateCounter++;
    if (self.streamingHeightUpdateCounter % 6 == 0) {
        [self.tableView beginUpdates];
        [self.tableView endUpdates];
    }
    
    [self scrollToBottomDuringStreaming];
}
消息完成处理（ChatViewController.m 1160-1200行）：
- (void)webSocketServiceDidCompleteSend:(WebSocketService *)service 
    modelName:(NSString *)modelName 
    tokenUsage:(NSDictionary *)tokenUsage {
    
    dispatch_async(dispatch_get_main_queue(), ^{
        self.inputView.loading = NO;
        
        if (self.currentAssistantMessage) {
            self.currentAssistantMessage.status = MessageStatusComplete;
            self.currentAssistantMessage.modelName = modelName;
            
            [self.tableView reloadRowsAtIndexPaths:@[indexPath] withRowAnimation:UITableViewRowAnimationNone];
            
            self.currentAssistantMessage = nil;
            
            ConversationManager *manager = [ConversationManager sharedManager];
            manager.currentConversation.updatedAt = [NSDate date];
            [manager saveConversations];
        }
    });
}
4. Agent 协作相关代码
chat_to_duck 直聊（ws_handler.py 1262-1418行）：
async def _handle_chat_to_duck(message: dict, websocket: WebSocket, current_session_id: str):
    """
    用户直聊子 Duck：向本地 Duck (内存队列) 或远程 Duck (WebSocket) 转发任务。
    结果通过 _duck_direct_chat_callbacks 路由回发起方的 WebSocket。
    """
    duck_id = message.get("duck_id")
    content = message.get("content")
    
    # 检查 Duck 状态
    duck = await registry.get(duck_id)
    if not duck or duck.status == DuckStatus.OFFLINE:
        await safe_send_json(websocket, {
            "type": "chat_to_duck_error",
            "error": "该 Duck 已离线"
        })
        return
    
    task_id = f"dctask_{uuid.uuid4().hex[:8]}"
    _duck_direct_chat_callbacks[task_id] = websocket
    
    # 通知客户端：任务已接受
    await safe_send_json(websocket, {
        "type": "chat_to_duck_accepted",
        "duck_id": duck_id,
        "task_id": task_id,
    })
    
    # 任务完成回调
    async def _on_task_done(task):
        target_ws = _duck_direct_chat_callbacks.pop(task_id, None)
        if target_ws:
            await safe_send_json(target_ws, {
                "type": "chat_to_duck_result",
                "duck_id": duck_id,
                "task_id": task_id,
                "success": task.status == TaskStatus.COMPLETED,
                "output": task.output,
            })
    
    # 提交任务
    if duck.is_local:
        await scheduler.submit(description=content, callback=_on_task_done, ...)
    else:
        await send_to_duck(duck_id, task_message)
iOS 端发送和接收（ChatViewController.m）：
// 发送消息到 Duck
- (void)inputView:(InputView *)inputView didSendMessage:(NSString *)message {
    ConversationManager *manager = [ConversationManager sharedManager];
    Conversation *currentConv = manager.currentConversation;
    
    if (currentConv.targetType == ConversationTargetTypeDuck && 
        currentConv.targetDuckId.length > 0) {
        [[WebSocketService sharedService] 
            sendChatToDuck:message 
            duckId:currentConv.targetDuckId 
            sessionId:currentConv.conversationId];
    } else {
        [[WebSocketService sharedService] 
            sendChatMessage:message 
            sessionId:currentConv.conversationId];
    }
}
// 接收 Duck 任务接受确认（1348-1361行）
- (void)webSocketService:(WebSocketService *)service 
    didAcceptChatToDuck:(NSString *)duckId 
    taskId:(NSString *)taskId {
    
    if (self.currentAssistantMessage) {
        self.currentAssistantMessage.content = @"🦆 Duck 正在处理中…";
        [self.tableView reloadRowsAtIndexPaths:...];
    }
}
// 接收 Duck 任务结果（1392-1422行）
- (void)webSocketService:(WebSocketService *)service 
    didReceiveChatToDuckResult:(NSString *)output 
    duckId:(NSString *)duckId 
    taskId:(NSString *)taskId 
    success:(BOOL)success 
    error:(NSString *)errorMessage {
    
    self.inputView.loading = NO;
    if (self.currentAssistantMessage) {
        if (success && output.length > 0) {
            self.currentAssistantMessage.content = output;
        } else {
            self.currentAssistantMessage.content = @"❌ Duck 未返回结果";
        }
        self.currentAssistantMessage.status = MessageStatusComplete;
    }
}
---
三、当前消息流程
1. 普通 Chat 流程
┌─────────────┐                    ┌──────────────┐                    ┌─────────────┐
│  iOS 客户端  │                    │  后端 Server  │                    │  LLM API    │
└─────────────┘                    └──────────────┘                    └─────────────┘
       │                                    │                                   │
       │ 1. sendChatMessage                 │                                   │
       ├───────────────────────────────────>│                                   │
       │    type: chat                      │                                   │
       │    content: "用户输入"              │                                   │
       │    session_id: xxx                 │                                   │
       │                                    │                                   │
       │ 2. task_start (monitor_event)      │                                   │
       │<───────────────────────────────────┤                                   │
       │    显示 AgentLiveView              │                                   │
       │                                    │                                   │
       │                                    │ 3. run_stream()                   │
       │                                    ├──────────────────────────────────>│
       │                                    │                                   │
       │ 4. content (流式 chunks)           │<──────────────────────────────────┤
       │<───────────────────────────────────┤    streaming response             │
       │    逐字追加到 currentAssistantMsg   │                                   │
       │    节流更新 UI (180ms)             │                                   │
       │                                    │                                   │
       │ 5. tool_call (monitor_event)       │                                   │
       │<───────────────────────────────────┤                                   │
       │    更新 AgentLiveView 工具调用     │                                   │
       │                                    │                                   │
       │ 6. done                            │                                   │
       │<───────────────────────────────────┤                                   │
       │    标记消息为 Complete             │                                   │
       │    隐藏 loading，保存会话          │                                   │
       │                                    │                                   │
2. Chat to Duck 直聊流程
┌─────────────┐        ┌──────────────┐        ┌─────────────┐        ┌────────────┐
│  iOS 客户端  │        │  后端 Server  │        │ Duck Worker │        │   子任务    │
└─────────────┘        └──────────────┘        └─────────────┘        └────────────┘
       │                       │                        │                     │
       │ 1. sendChatToDuck     │                        │                     │
       ├──────────────────────>│                        │                     │
       │   duck_id: "coder"    │                        │                     │
       │   content: "写代码"    │                        │                     │
       │                       │                        │                     │
       │                       │ 2. 检查 Duck 状态      │                     │
       │                       │   (online/busy?)       │                     │
       │                       ├───────────────────────>│                     │
       │                       │                        │                     │
       │ 3. chat_to_duck_accepted                      │                     │
       │<──────────────────────┤                        │                     │
       │   显示 "Duck 处理中"   │                        │                     │
       │                       │                        │                     │
       │                       │ 4. submit task         │                     │
       │                       ├───────────────────────>│                     │
       │                       │   (本地队列/WebSocket) │                     │
       │                       │                        │                     │
       │                       │                        │ 5. 执行任务         │
       │                       │                        ├────────────────────>│
       │                       │                        │                     │
       │                       │                        │<────────────────────┤
       │                       │                        │   任务完成          │
       │                       │                        │                     │
       │                       │ 6. callback            │                     │
       │                       │<───────────────────────┤                     │
       │                       │                        │                     │
       │ 7. chat_to_duck_result│                        │                     │
       │<──────────────────────┤                        │                     │
       │   success: true       │                        │                     │
       │   output: "代码结果"   │                        │                     │
       │                       │                        │                     │
3. Duck Task Complete 广播流程
┌─────────────┐        ┌──────────────┐        ┌─────────────┐
│ iOS 客户端 A │        │  后端 Server  │        │ iOS 客户端 B │
│ (发起者)     │        │              │        │  (同会话)    │
└─────────────┘        └──────────────┘        └─────────────┘
       │                       │                        │
       │                       │ Duck 任务完成后钩子     │
       │                       │ _on_duck_task_complete │
       │                       │         ↓              │
       │                       │ _run_agent_and_broadcast_result
       │                       │         ↓              │
       │                       │ 收集 run_stream 完整响应
       │                       │         ↓              │
       │ duck_task_complete    │                        │
       │<──────────────────────┴───────────────────────>│
       │   type: duck_task_complete                     │
       │   session_id: xxx                              │
       │   content: "Duck 完成的工作"                    │
       │   success: true                                │
       │                       │                        │
       │ 创建新 assistant msg   │                        │ 创建新 assistant msg
       │ 追加到会话             │                        │ 追加到会话
       │ 刷新 UI               │                        │ 刷新 UI
       │                       │                        │
---
四、可能存在的问题
1. ⚠️ 消息去重机制不完善
问题描述：
- iOS 端在重连恢复时可能收到重复的 duck_task_complete 消息
- 当前实现了 displayedMessageIds 去重集合（1458行），但仅用于 resume_chat
- duck_task_complete 广播没有使用消息去重机制
影响：
- 重连后可能在同一会话中显示重复的 Duck 完成消息
- 用户体验混乱
建议修复：
- (void)webSocketService:(WebSocketService *)service 
    didReceiveDuckTaskComplete:(NSString *)content 
    success:(BOOL)success 
    sessionId:(NSString *)sessionId {
    
    // 添加去重检查
    NSString *msgId = [NSString stringWithFormat:@"duck_%@_%@", 
                      sessionId, [content md5Hash]];
    if ([self.displayedMessageIds containsObject:msgId]) {
        NSLog(@"[Chat] Duplicate duck_task_complete, skipping");
        return;
    }
    [self.displayedMessageIds addObject:msgId];
    
    // ... 原有处理逻辑
}
2. ⚠️ Session ID 不匹配导致消息丢失
问题描述：
- iOS 端本地会话 ID 与后端 session_id 可能不一致（App 重启场景）
- didConnectWithClientId 方法会检测不匹配并调用 createNewSession（983-1012行）
- 但 duck_task_complete 广播只根据 session_id 路由，不会重新同步
影响：
- 重启后收到的 duck_task_complete 可能找不到对应会话
- 消息被丢弃（1374行 if (!conv) return;）
建议修复：
// 在 duck_task_complete 处理中添加会话创建逻辑
if (!conv) {
    // 尝试创建或恢复会话
    conv = [[ConversationManager sharedManager] 
            getOrCreateConversationWithId:sessionId];
    if (!conv) {
        NSLog(@"[Chat] Cannot find/create conversation for session %@", sessionId);
        return;
    }
}
3. ⚠️ 流式更新时的内存泄漏风险
问题描述：
- throttledUpdateStreamingCell 使用 dispatch_after 创建延迟任务（1058-1062行）
- 如果用户快速切换会话或退出界面，self 可能已释放但延迟任务仍执行
影响：
- 潜在的崩溃或内存泄漏
建议修复：
- (void)throttledUpdateStreamingCell {
    // ... 现有代码
    if (!self.hasPendingStreamingUpdate) {
        self.hasPendingStreamingUpdate = YES;
        __weak typeof(self) weakSelf = self;  // 添加弱引用
        dispatch_after(..., ^{
            __strong typeof(weakSelf) strongSelf = weakSelf;
            if (!strongSelf) return;  // 检查 self 是否已释放
            strongSelf.hasPendingStreamingUpdate = NO;
            [strongSelf flushStreamingCellUpdate];
        });
    }
}
4. ⚠️ chat_to_duck_result 状态判断错误
问题描述：
- 1392-1422行的 didReceiveChatToDuckResult 方法中，成功时也设置为 MessageStatusError（1400行）
if (success && output.length > 0) {
    self.currentAssistantMessage.content = output;
    self.currentAssistantMessage.status = MessageStatusError;  // ❌ 应该是 Complete
}
影响：
- 成功的 Duck 任务结果被标记为错误状态
- UI 显示异常（可能显示红色错误样式）
建议修复：
if (success && output.length > 0) {
    self.currentAssistantMessage.content = output;
    self.currentAssistantMessage.status = MessageStatusComplete;  // ✅ 修正
} else {
    NSString *msg = errorMessage.length > 0 ? errorMessage : @"Duck 未返回结果";
    self.currentAssistantMessage.content = [NSString stringWithFormat:@"❌ %@", msg];
    self.currentAssistantMessage.status = MessageStatusError;
}
5. ⚠️ 后端 broadcast_to_session 可能丢失离线客户端的消息
问题描述：
- connection_manager.py 的 broadcast_to_session 只向当前在线的客户端发送（101-114行）
- 如果客户端暂时断线，duck_task_complete 等重要消息会丢失
- 没有消息队列或持久化机制
影响：
- 用户重连后看不到断线期间 Duck 完成的任务
- 多设备协作时，离线设备重连后无法同步状态
建议修复：
# 在后端添加消息缓冲队列
class ConnectionManager:
    def __init__(self):
        # ... 现有代码
        self._message_buffer: Dict[str, List[Dict]] = {}  # session_id -> messages
    
    async def broadcast_to_session(self, session_id: str, message: dict, ...):
        # 缓冲重要消息（duck_task_complete, done 等）
        if message.get("type") in ["duck_task_complete", "done", "chat_to_duck_result"]:
            if session_id not in self._message_buffer:
                self._message_buffer[session_id] = []
            self._message_buffer[session_id].append({
                "message": message,
                "timestamp": datetime.now(),
            })
            # 限制缓冲区大小
            self._message_buffer[session_id] = self._message_buffer[session_id][-50:]
        
        # ... 原有广播逻辑
    
    async def on_client_reconnect(self, client_id: str, session_id: str):
        """客户端重连时推送缓冲消息"""
        if session_id in self._message_buffer:
            conn = self.get_connection(client_id)
            for buffered in self._message_buffer[session_id]:
                await safe_send_json(conn.websocket, buffered["message"])
6. ⚠️ AgentLiveView 状态不同步
问题描述：
- showAgentLiveViewForChat 创建占位 TaskProgress（1650-1656行）
- 但如果后续收到 monitor_event 的 task_start，可能会创建新的 TaskProgress 覆盖
- 导致状态不连续
影响：
- Agent Live 面板显示闪烁或数据丢失
建议修复：
- (void)webSocketService:(WebSocketService *)service 
    didReceiveMonitorEvent:(NSDictionary *)event 
    sessionId:(NSString *)sessionId 
    taskId:(NSString *)taskId 
    taskType:(NSString *)taskType {
    
    NSString *evType = event[@"type"];
    if ([evType isEqualToString:@"task_start"]) {
        [self showAgentLiveView];
        
        // 检查是否已有占位 TaskProgress
        if (!self.agentLiveView.taskProgress || 
            [self.agentLiveView.taskProgress.taskId isEqualToString:@"chat"]) {
            // 创建新的 TaskProgress
            self.agentLiveView.taskProgress = [TaskProgress progressWithTaskId:taskId ...];
        } else {
            // 更新现有 TaskProgress
            [self.agentLiveView.taskProgress handleTaskStart:event];
        }
    }
}
7. ⚠️ WebSocket 重连时的竞态条件
问题描述：
- didConnectWithClientId 中同时检测 session 不匹配和 hasRunningChat（983-1012行）
- 如果在 createNewSession 和 resumeChat 之间收到新消息，可能导致状态不一致
建议修复：
- (void)webSocketService:(WebSocketService *)service didConnectWithClientId:... {
    dispatch_async(dispatch_get_main_queue(), ^{
        // 使用串行队列确保操作顺序
        if (localSessionId && ![localSessionId isEqualToString:sessionId]) {
            [[WebSocketService sharedService] createNewSession:localSessionId];
            
            // 在 createNewSession 完成后再 resume
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)), 
                          dispatch_get_main_queue(), ^{
                if (self.currentAssistantMessage) {
                    [[WebSocketService sharedService] resumeChat:localSessionId];
                }
            });
        }
    });
}
---
五、总结和建议
优点：
1. ✅ 模块化设计：WebSocket 服务、消息管理、UI 层职责清晰
2. ✅ 流式优化：节流更新机制（180ms）有效减少 UI 卡顿
3. ✅ 多端协作：支持多客户端同时连接同一会话
4. ✅ 断线重连：自动重连和任务恢复机制完善
5. ✅ 实时监控：AgentLiveView 提供任务执行可见性
主要问题：
1. ❌ 消息去重不完善：duck_task_complete 可能重复显示
2. ❌ Session 同步问题：重启后消息可能丢失
3. ❌ 状态判断错误：chat_to_duck_result 成功时设置为 Error
4. ❌ 消息持久化缺失：离线期间的消息无法恢复
5. ⚠️ 内存管理风险：延迟任务可能导致泄漏
优化建议：
1. 引入消息 ID 机制：为所有重要消息添加唯一 ID，客户端去重
2. 会话状态同步：客户端重连时主动请求会话状态，避免丢失
3. 消息缓冲队列：后端缓存最近 N 条重要消息，重连时推送
4. 状态机设计：为 Duck 任务添加明确的状态流转（pending -> accepted -> running -> completed）
5. 监控和日志：添加详细的日志记录，方便调试多端协作问题
以上分析基于当前代码实现，希望对您理解和优化系统有所帮助！