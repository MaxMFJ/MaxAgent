# iOS 端上下文污染问题解决方案

## 问题描述

iOS 端使用全局 `session_id`，导致新对话继承旧对话的上下文，造成上下文污染。

## 解决方案

实施完整的会话管理系统（与 Mac 端保持一致）。

## 已完成的修改

### 1. 创建新模型文件

#### Conversation.h & Conversation.m
- 会话模型，包含 conversationId、title、messages、时间戳等
- 支持 NSCoding/NSSecureCoding 序列化

#### ConversationManager.h & ConversationManager.m
- 单例管理器，负责会话的 CRUD
- 使用 NSUserDefaults 持久化
- 管理当前选中的会话

### 2. 修改 Message 模型
- 添加 NSCoding/NSSecureCoding 支持
- 实现序列化/反序列化方法

### 3. 修改 WebSocketService
- 所有方法添加 `sessionId` 参数：
  - `sendChatMessage:sessionId:`
  - `sendAutonomousTask:sessionId:`
  - `clearSession:sessionId:`
  - `sendStopStream:sessionId:`
  - `resumeTask:sessionId:`
- 移除对全局 `[ServerConfig sharedConfig].sessionId` 的依赖

### 4. 重构 ChatViewController
- 移除本地 `messages` 数组，改为从 ConversationManager 获取
- 添加 `createNewConversation` 方法
- 添加 `showConversationList` 方法显示会话列表
- 添加 `switchToConversation:` 方法切换会话
- 添加 `updateTitle` 方法动态更新导航栏标题
- 更新所有消息操作方法以使用当前会话的 messages
- 更新导航栏：添加"新建对话"和"对话列表"按钮

### 5. 创建 ConversationListViewController
- 专门的会话列表界面
- 支持会话选择、删除、新建
- 显示会话标题、消息数量、更新时间
- 支持左滑删除
- 使用代理模式通知 ChatViewController

### 6. 本地化支持
- 添加中英文字符串：
  - `new_conversation`: 新对话 / New Conversation
  - `conversations`: 对话列表 / Conversations
  - `select_conversation`: 选择一个对话 / Select a conversation
  - `messages`: 条消息 / messages

### 7. Xcode 项目配置
- 已添加新文件到 project.pbxproj
- 已配置编译源文件列表

## 核心改进

### 上下文隔离
- ✅ 每个会话有独立的 UUID
- ✅ 每个会话维护独立的消息列表
- ✅ 后端通过不同的 session_id 隔离上下文

### 会话持久化
- ✅ 会话列表持久化到 UserDefaults
- ✅ 应用重启后恢复会话

### 用户体验
- ✅ 可以创建多个独立对话
- ✅ 可以在对话之间切换
- ✅ 每个对话的历史记录独立保存
- ✅ 清空聊天只清空当前对话，不影响其他对话
- ✅ 导航栏显示当前会话标题
- ✅ 会话列表显示消息数量和更新时间

## UI 改进

### 导航栏布局
```
左侧：[对话列表] [清空]
标题：当前会话标题
右侧：[设置] [新建对话]
```

### 会话列表界面
- 每行显示：会话标题、消息数量、更新时间
- 当前会话有勾选标记和加粗字体
- 支持左滑删除
- 顶部有新建按钮

## 技术细节

### Session ID 流转
```
用户发送消息
    → ChatViewController 获取 currentConversation.conversationId
    → WebSocketService 发送带 session_id 的消息到后端
    → 后端使用 session_id 隔离上下文
    → 响应时带上 session_id
    → ChatViewController 更新对应会话的消息
```

### 数据流
```
ConversationManager (单例)
    ├── conversations: [Conversation]
    └── currentConversation: Conversation
            ├── conversationId: UUID (用作后端 session_id)
            ├── title: String (首条消息前30字符)
            ├── messages: [Message]
            ├── createdAt: Date
            └── updatedAt: Date
```

### 代理模式
```
ConversationListViewController
    ↓ (delegate)
ChatViewController
    - didSelectConversation: 切换会话并刷新 UI
    - didDeleteConversation: 删除会话后更新 UI
```

## 与 Mac 端对比

| 特性 | Mac 端 (SwiftUI) | iOS 端 (Objective-C) | 状态 |
|------|------------------|---------------------|------|
| 多会话管理 | ✅ | ✅ | 已实现 |
| 会话持久化 | ✅ UserDefaults | ✅ NSUserDefaults | 已实现 |
| 独立 session_id | ✅ | ✅ | 已实现 |
| 会话切换 UI | ✅ 侧边栏 | ✅ 专门列表页 | 已实现 |
| 上下文隔离 | ✅ | ✅ | 已实现 |
| 动态标题 | ✅ | ✅ | 已实现 |
| 左滑删除 | - | ✅ | 已实现 |

## 使用说明

### 创建新对话
1. 点击右上角的"笔记本"图标（square.and.pencil）
2. 自动创建新会话并切换到该会话
3. 新会话有独立的 UUID 作为 session_id

### 切换会话
1. 点击左上角的"气泡"图标（text.bubble）
2. 选择要切换的会话
3. 当前会话会显示勾选标记

### 删除会话
方法一：在会话列表中左滑删除
方法二：在会话列表中进入编辑模式删除

### 清空当前会话
1. 点击左上角的"垃圾桶"图标
2. 确认清空
3. 只清空当前会话的消息，不影响其他会话

## 测试清单

### 功能测试
- [ ] 创建新对话，验证生成新的 conversationId
- [ ] 在新对话中发送消息，验证不受旧对话影响
- [ ] 切换到旧对话，验证历史消息正确显示
- [ ] 删除会话，验证数据正确清理
- [ ] 清空会话，验证只清空当前会话
- [ ] 应用重启，验证会话列表恢复

### 上下文隔离测试
- [ ] 在对话 A 中发送"你好，我叫张三"
- [ ] 创建新对话 B，发送"我叫什么名字？"
- [ ] 验证 AI 回复不知道（上下文隔离成功）
- [ ] 切换回对话 A，发送"我叫什么名字？"
- [ ] 验证 AI 正确回答"张三"（上下文保持成功）

### UI 测试
- [ ] 验证导航栏按钮布局正确
- [ ] 验证会话列表显示正确
- [ ] 验证当前会话标记正确
- [ ] 验证标题动态更新
- [ ] 验证左滑删除功能

### 并发测试
- [ ] Mac 端和 iOS 端同时连接同一个后端
- [ ] 验证各自的会话独立
- [ ] 验证不会互相干扰

## 注意事项

1. **编译前确认**：
   - 所有新文件已添加到 Xcode 项目
   - project.pbxproj 正确配置
   - 无语法错误

2. **迁移现有数据**：
   - 首次运行会自动创建一个新会话
   - 旧的消息数据可能丢失（因为之前没有会话管理）
   - 建议在更新说明中提醒用户

3. **后续优化方向**：
   - 会话重命名功能
   - 会话搜索功能
   - 会话导出/分享功能
   - 会话标签/分组功能

## 文件清单

### 新增文件
- `Models/Conversation.h`
- `Models/Conversation.m`
- `Models/ConversationManager.h`
- `Models/ConversationManager.m`
- `ViewControllers/ConversationListViewController.h`
- `ViewControllers/ConversationListViewController.m`

### 修改文件
- `Models/Message.h` - 添加 NSCoding 支持
- `Models/Message.m` - 实现序列化方法
- `Services/WebSocketService.h` - 方法签名添加 sessionId
- `Services/WebSocketService.m` - 实现改用传入的 sessionId
- `ViewControllers/ChatViewController.m` - 完整重构会话管理
- `Resources/zh-Hans.lproj/Localizable.strings` - 添加本地化
- `Resources/Base.lproj/Localizable.strings` - 添加本地化
- `iOSAgentApp.xcodeproj/project.pbxproj` - 添加新文件引用

## 代码质量

- ✅ 遵循 Objective-C 编码规范
- ✅ 使用单例模式管理全局状态
- ✅ 使用代理模式解耦组件
- ✅ 正确的内存管理（ARC）
- ✅ 完整的错误处理
- ✅ 国际化支持
- ✅ 与 Mac 端保持一致的架构

