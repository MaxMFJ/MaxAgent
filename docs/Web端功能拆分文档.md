# Chow Duck Web 端功能拆分文档

> 基于 Mac Agent App 完整分析，确保 Web 端与 Mac App 体验一致。
> 
> **实现进度**：✅ 已完成 | 🔧 部分完成 | ❌ 未完成
> 
> 截至最近更新：**P0 全部完成、P1 大部分完成、P2 大部分待做**

---

## 一、总体架构

### 技术栈建议
- **前端框架**: React 18 + TypeScript
- **UI 库**: Tailwind CSS（实现赛博朋克主题）
- **状态管理**: Zustand（轻量、支持中间件）
- **WebSocket**: 原生 WebSocket + 自动重连
- **Markdown 渲染**: react-markdown + rehype-highlight
- **图表**: recharts（监控仪表板）
- **构建工具**: Vite

### 布局对标
Mac App 采用 `HSplitView` 三栏布局，Web 端对应：
```
┌─────────────────────────────────────────────────────────┐
│  工具栏（服务状态 | 通知铃铛 | 监控 | 工具面板 | 设置） │
├──────────┬──────────────────────┬────────────┬──────────┤
│  侧边栏  │      聊天区域        │  工具面板  │ 系统消息 │
│ (对话列表)│  (消息列表+输入框)   │ (可隐藏)   │ (可隐藏) │
│  200-300px│      自适应          │ 250-400px  │ 280-420px│
└──────────┴──────────────────────┴────────────┴──────────┘
```

---

## 二、功能模块拆分（共 9 大模块、50 个功能点）

### 模块 1：主布局与导航框架

| # | 功能点 | 描述 | 对标 Mac 文件 | 优先级 | 状态 |
|---|--------|------|--------------|--------|------|
| 1.1 | 三栏可调布局 | 左侧边栏(200-300px) + 中间聊天(自适应) + 右侧工具面板(250-400px，可隐藏) + 系统消息面板(280-420px，可隐藏) | ContentView.swift | P0 | ✅ |
| 1.2 | 顶部工具栏 | 服务状态指示灯(后端+Ollama)、系统消息铃铛(未读数)、监控仪表板按钮、工具面板切换、设置按钮 | ContentView.swift toolbar | P0 | ✅ |
| 1.3 | 赛博朋克主题 | 深色背景(#0A0A14)、Cyan高亮(#00E5FF)、等宽字体、霓虹光效、边框发光 | CyberColor/CyberpunkTheme | P0 | ✅ |
| 1.4 | 响应式适配 | 窗口最小 800x500，面板可折叠，移动端适配 | - | P1 | ✅ |

### 模块 2：对话侧边栏

| # | 功能点 | 描述 | 对标 Mac 文件 | 优先级 | 状态 |
|---|--------|------|--------------|--------|------|
| 2.1 | 对话列表 | 显示所有对话（标题、更新时间、消息数），当前选中高亮 | SidebarView.swift | P0 | ✅ |
| 2.2 | 新建对话 | 点击 "+" 按钮创建新对话，自动选中 | SidebarView.swift | P0 | ✅ |
| 2.3 | 选择对话 | 点击切换到对应对话，加载历史消息 | SidebarView.swift | P0 | ✅ |
| 2.4 | 删除对话 | 右键菜单删除，删除后自动选中下一个 | SidebarView.swift | P0 | ✅ |
| 2.5 | 连接状态 | 底部显示 WebSocket 连接状态（绿点/红点 + 文字），断开时显示"重连"按钮 | SidebarView.swift | P0 | ✅ |
| 2.6 | 对话持久化 | localStorage 保存对话数据（与 Mac App 的 UserDefaults 对标） | AgentViewModel | P0 | ✅ |
| 2.7 | 自动标题 | 首条用户消息前30字符作为对话标题 | AgentViewModel | P1 | ✅ |

### 模块 3：聊天对话核心

| # | 功能点 | 描述 | 对标 Mac 文件 | 优先级 | 状态 |
|---|--------|------|--------------|--------|------|
| 3.1 | 消息列表 | 用户消息(右侧蓝色气泡) + 助手消息(左侧深色气泡+头像) | ChatView/MessageBubble | P0 | ✅ |
| 3.2 | 流式输出 | WebSocket 实时接收 content chunk，逐字渲染 | AgentViewModel | P0 | ✅ |
| 3.3 | Markdown 渲染 | 支持标题、列表、粗体、斜体、链接、表格 | RichMarkdownView | P0 | ✅ |
| 3.4 | 代码块高亮 | 支持语法高亮、复制按钮、语言标签 | CodeBlockView | P0 | ✅ |
| 3.5 | 思考块折叠 | `<think>` 标签内容可折叠展示 | ThinkingBlockView | P1 | ✅ |
| 3.6 | 图片展示 | 支持 Base64 图片、本地路径图片(通过后端代理)、URL 图片 | ImageDisplayView/Base64ImageView | P0 | ✅ |
| 3.7 | "正在思考" 指示器 | 流式输出时显示加载动画 + "正在思考..." | TypingIndicator | P0 | ✅ |
| 3.8 | 模型信息 | 消息底部显示模型名称 + Token 用量 | AssistantMessageContent footer | P1 | ✅ |
| 3.9 | 消息操作 | 复制全文、编辑(用户消息)、删除 | MessageBubble contextMenu | P0 | ✅ |
| 3.10 | 自动滚动 | 新消息自动滚底，用户手动上滚时暂停 | ChatView scrollToBottom | P0 | ✅ |
| 3.11 | 欢迎页 | 无消息时显示 Logo + 功能介绍（文件管理、终端命令、应用控制、系统信息、剪贴板） | WelcomeView | P1 | ✅ |
| 3.12 | 错误横幅 | 顶部可关闭的错误提示条 | ErrorBannerView | P0 | ✅ |

### 模块 4：输入交互

| # | 功能点 | 描述 | 对标 Mac 文件 | 优先级 | 状态 |
|---|--------|------|--------------|--------|------|
| 4.1 | 多行输入框 | 自适应高度(36-120px)，Enter发送，Shift+Enter换行 | InputBar/CustomTextEditor | P0 | ✅ |
| 4.2 | 发送按钮 | 蓝色上箭头，无内容/未连接时灰色禁用 | InputBar | P0 | ✅ |
| 4.3 | 停止按钮 | 加载中时切换为红色停止按钮，点击终止当前任务 | InputBar | P0 | ✅ |
| 4.4 | 自主执行按钮 | 🤖 机器人按钮(Cmd+Shift+Enter)，触发自主任务模式 | InputBar | P0 | ✅ |
| 4.5 | 语音输入按钮 | 麦克风按钮，Web Speech API，静音自动发送 | InputBar/VoiceInputService | P2 | ❌ |
| 4.6 | 快捷键 | Cmd+N 新建对话、Cmd+, 设置、Cmd+Enter 发送 | MacAgentApp commands | P1 | ✅ |

### 模块 5：工具面板（右侧可隐藏）

| # | 功能点 | 描述 | 对标 Mac 文件 | 优先级 | 状态 |
|---|--------|------|--------------|--------|------|
| 5.1 | Tab 切换 | 矩阵 / 历史 / 任务 / 日志 4个标签 | ToolPanelView | P0 | ✅ |
| 5.2 | 工具矩阵 | 3列网格展示所有工具（系统工具 + 生成工具），芯片样式卡片 | ToolMatrixView | P0 | ✅ |
| 5.3 | 工具详情 | 点击展开：名称、描述、参数数量、状态(ONLINE/DYNAMIC) | ToolDetailPanel | P1 | ✅ |
| 5.4 | 调用历史 | 最近10条工具调用记录，可展开查看参数和结果 | ToolHistoryView | P0 | ✅ |
| 5.5 | 自主任务面板 | 任务进度（状态/耗时/动作数/成功率）+ 模型信息 + 执行日志 | AutonomousTaskView | P0 | ✅ |
| 5.6 | 运行时日志 | 实时工具执行日志（时间戳、级别、工具名、内容） | ExecutionLogsView | P1 | ✅ |

### 模块 6：系统消息面板（右侧可隐藏）

| # | 功能点 | 描述 | 对标 Mac 文件 | 优先级 | 状态 |
|---|--------|------|--------------|--------|------|
| 6.1 | 通知铃铛 | 工具栏铃铛图标，显示未读数角标 | NotificationBellButton | P0 | ✅ |
| 6.2 | 消息列表 | 按时间倒序展示系统通知（图标+标题+内容+时间） | SystemMessageView | P0 | ✅ |
| 6.3 | 分类Tab | 全部 / 系统错误 / 进化状态 / 任务完成 / 其他 | SystemMessageTab | P1 | ✅ |
| 6.4 | 已读/未读 | 未读高亮+蓝点，点击标为已读 | SystemMessageRow | P1 | ✅ |
| 6.5 | 批量操作 | 全部标为已读、清空所有、复制当前列表 | SystemMessageView menu | P1 | ✅ |

### 模块 7：设置面板（模态弹窗/抽屉）

| # | 功能点 | 描述 | 对标 Mac 文件 | 优先级 | 状态 |
|---|--------|------|--------------|--------|------|
| 7.1 | Tab 导航 | 服务/远程/模型/通用/邮件/工具/权限/关于 共8个Tab | SettingsView | P0 | 🔧 实现4Tab(模型/通用/服务/关于) |
| 7.2 | 模型配置 | AI提供商选择(DeepSeek/NewAPI/ChatGPT/Gemini/Claude/Ollama/LM Studio) + 各自配置表单(API Key/Base URL/Model) | ModelSettingsContent | P0 | ✅ |
| 7.3 | 远程回退策略 | 选择远程模型时使用的云端提供商 | ModelSettingsContent | P1 | ❌ |
| 7.4 | LangChain 开关 | 切换对话引擎，安装依赖按钮 | GeneralSettingsContent | P2 | ❌ |
| 7.5 | 语音设置 | TTS 开关、STT 静音/超时参数 | GeneralSettingsContent | P2 | ❌ |
| 7.6 | 邮件SMTP配置 | 服务器/端口/邮箱/授权码 | MailSettingsContent | P2 | ❌ |
| 7.7 | GitHub Token | 用于开放技能源 | GeneralSettingsContent | P2 | ❌ |
| 7.8 | 工具审批 | 显示待审批动态工具，审批按钮 | ToolSettingsContent | P1 | ❌ |
| 7.9 | 服务管理 | 后端/Ollama 服务启停状态、日志查看 | ServiceManagerView | P1 | 🔧 仅健康检查按钮 |
| 7.10 | Tunnel 管理 | Cloudflare Tunnel 启停、状态、URL、QR码、局域网信息 | TunnelView | P2 | ❌ |
| 7.11 | 权限检测 | 显示权限状态（Web端可简化为后端权限检测结果展示） | PermissionSettingsView | P2 | ❌ |
| 7.12 | 关于页 | 版本号、功能图标 | AboutContent | P2 | ✅ |
| 7.13 | 连接状态 | 当前连接状态 + 重连按钮 | GeneralSettingsContent | P0 | ✅ |

### 模块 8：监控仪表板（独立页面/弹窗）

| # | 功能点 | 描述 | 对标 Mac 文件 | 优先级 | 状态 |
|---|--------|------|--------------|--------|------|
| 8.1 | EXEC - 执行时间轴 | AI 步骤可视化（pending/executing/success/failed），自动滚动 | ExecutionTimelineView | P1 | ✅ |
| 8.2 | EXEC - Neural Stream | LLM 实时输出面板（打字光标、LIVE标签） | NeuralStreamPanel | P1 | ✅ |
| 8.3 | EXEC - 侧边仪表盘 | Token 用量、迭代次数、耗时、工具调用次数 | TimelineSidebar | P1 | 🔧 部分指标 |
| 8.4 | SYS - 系统状态 | 服务健康（后端/WS/向量库/本地LLM/EvoMap 5个指示灯） | SystemStatusDashboardView | P1 | ✅ |
| 8.5 | SYS - LLM 信息卡 | 当前提供商、模型名、连接状态 | LLMInfoCard | P1 | ✅ |
| 8.6 | SYS - 活动趋势 | Token消耗迷你折线图 | ActivitySparklineCard | P2 | ❌ |
| 8.7 | STATS - 用量总览 | 总请求/成功数/总Token/输入Token/输出Token/RPM/TPM | UsageStatisticsView | P2 | ❌ |
| 8.8 | STATS - 趋势图表 | 请求趋势(RPM)、Token趋势(TPM)、模型消耗分布、模型调用排行 | RequestTrendCard 等 | P2 | ❌ |
| 8.9 | HIST - 历史记录 | Episode 列表（任务描述/成功率/迭代/Token/工具/时间） | HistoryAnalysisView | P2 | ❌ |
| 8.10 | HIST - 聚合统计 | 总任务/成功率/平均轮次/工具排行 | HistoryStatsPanel | P2 | ❌ |
| 8.11 | LOGS - 日志流 | 工具日志/系统日志/系统通知 三源切换，搜索+级别过滤 | LogStreamView | P1 | ✅ |
| 8.12 | 底部状态栏 | 后端状态、WS连接数、LLM流式指示、模型名、刷新时间 | CyberStatusBar | P2 | ❌ |

### 模块 9：文件下载功能

| # | 功能点 | 描述 | 对标 Mac/iOS 文件 | 优先级 | 状态 |
|---|--------|------|------------------|--------|------|
| 9.1 | 智能路径检测 | 从 AI 回复中自动提取文件路径（3 策略：行级/内联/反引号），支持含空格路径 | MarkdownParser.extractFilePaths / FileDownloadView.detectFilePathsInText | P0 | ✅ |
| 9.2 | 路径验证 | 验证提取的路径：以/开头、≥2层目录、有扩展名(≤10字符)、排除图片格式、排除URL和Markdown链接 | MarkdownParser.validateFilePath / FileDownloadView.validateFilePath | P0 | ✅ |
| 9.3 | 文件信息卡片 | 显示文件图标(Emoji映射40+扩展名)、文件名、大小、扩展名、完整路径 | FileDownloadView.swift / FileDownloadView.m | P0 | ✅ |
| 9.4 | 文件下载 | 点击卡片触发浏览器下载，通过 GET /files/download?path= 获取文件 | FileDownloadView.swift / FileDownloadView.m | P0 | ✅ |
| 9.5 | 文件信息获取 | 从后端 GET /files/info?path= 获取文件元数据(名称/大小/扩展名/图标/是否存在) | backend/routes/files.py | P0 | ✅ |
| 9.6 | 文件预览 | GET /files/preview?path= 获取文本文件前 5000 字符预览 | backend/routes/files.py | P2 | ✅ |
| 9.7 | 悬停交互 | 鼠标悬停时卡片边框发光、背景高亮（赛博朋克风格） | FileDownloadView.swift | P1 | ✅ |
| 9.8 | 加载状态 | 获取文件信息时显示骨架屏动画 | FileDownloadCard.tsx | P0 | ✅ |

#### 后端 API 端点

```
GET /files/info?path=/absolute/path    → { name, path, size, sizeFormatted, extension, icon, exists, isFile, modifiedAt }
GET /files/download?path=/absolute/path → 文件流下载 (Content-Disposition: attachment)
GET /files/preview?path=/absolute/path  → { content, truncated }
```

#### Web 端实现文件

| 文件 | 职责 |
|------|------|
| `web/src/utils/filePaths.ts` | extractFilePaths() 3策略检测 + validateFilePath() 验证 + getFileIcon() 图标映射 |
| `web/src/components/FileDownloadCard.tsx` | 文件下载卡片组件（加载状态、悬停效果、点击下载） |
| `web/src/components/MessageBubble.tsx` | 在消息气泡中集成 FileDownloadCard |
| `web/src/services/api.ts` | getFileInfo() / getFileDownloadUrl() / getFilePreview() |

---

## 三、通信协议详细规格

### 3.1 WebSocket 连接

**地址**: `ws://127.0.0.1:8765/ws`

#### 客户端→服务端消息

```typescript
// 聊天消息
{ type: "chat", content: string, session_id?: string }

// 自主任务
{ type: "autonomous_task", task: string, session_id?: string, 
  enable_model_selection?: boolean, prefer_local?: boolean }

// 停止任务
{ type: "stop", session_id?: string }

// 恢复自主任务
{ type: "resume_task", session_id: string }

// 恢复聊天流
{ type: "resume_chat", session_id: string }

// 清除会话
{ type: "clear_session", session_id: string }

// 心跳回复
{ type: "pong" }
```

#### 服务端→客户端消息

```typescript
// 连接成功
{ type: "connected", session_id: string, 
  has_running_task: boolean, running_task_id?: string,
  has_running_chat: boolean, running_chat_task_id?: string,
  has_buffered_chat?: boolean }

// 流式文本
{ type: "content", content: string }

// 工具调用
{ type: "tool_call", tool_name: string, tool_args: Record<string, any> }

// 工具结果
{ type: "tool_result", tool_name: string, success: boolean, result: string }

// 执行日志
{ type: "execution_log", tool_name: string, action_id?: string, 
  level: string, message: string }

// LLM 请求开始
{ type: "llm_request_start", provider: string, model: string, iteration: number }

// LLM 请求结束
{ type: "llm_request_end", provider: string, model: string, iteration: number,
  latency_ms: number, usage: { prompt_tokens, completion_tokens, total_tokens },
  response_preview?: string, error?: string }

// 自主任务 - 任务开始
{ type: "task_start", task_id: string, task: string }

// 自主任务 - 模型选择
{ type: "model_selected", model_type: "local"|"remote", reason: string, 
  task_type: string, complexity: number }

// 自主任务 - 动作规划
{ type: "action_plan", action: { action_id, action_type, reasoning, params }, 
  iteration: number }

// 自主任务 - 动作执行中
{ type: "action_executing", action_id: string, action_type: string }

// 自主任务 - 动作结果
{ type: "action_result", action_id: string, success: boolean, 
  output?: string, error?: string }

// 自主任务 - 反思
{ type: "reflect_start" }
{ type: "reflect_result", reflection: string }

// 自主任务 - 完成
{ type: "task_complete", task_id: string, success: boolean, 
  summary: string, total_actions: number }

// 截图/图片
{ type: "image", base64: string, mime_type: string, path?: string }
{ type: "screenshot", screenshot_path: string, image_base64: string, mime_type: string }

// 完成/停止/错误
{ type: "done", model?: string, usage?: { prompt_tokens, completion_tokens, total_tokens } }
{ type: "stopped" }
{ type: "error", message: string }

// 重试
{ type: "retry", message: string }

// 心跳
{ type: "server_ping" }

// 系统通知
{ type: "system_notification", notification: SystemNotification, unread_count: number }

// 工具更新
{ type: "tools_updated" }

// 全局监控事件
{ type: "monitor_event", source_session: string, task_id: string, 
  task_type: string, event: any }

// Chat 恢复结果
{ type: "resume_chat_result", found: boolean, task_id?: string, 
  status?: string, last_message_id?: string }

// 升级
{ type: "upgrade_complete", plan?: string, loaded_tools?: string[] }
{ type: "upgrade_error", error: string }
```

### 3.2 REST API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/health` | 健康检查(status/provider/model/evomap) |
| GET | `/server-status` | 服务器状态 |
| GET | `/connections` | WebSocket 连接统计 |
| GET | `/config` | 获取 LLM 配置 |
| POST | `/config` | 更新 LLM 配置 |
| POST | `/config/install-langchain` | 安装 LangChain 依赖 |
| GET | `/config/smtp` | 获取 SMTP 配置 |
| POST | `/config/smtp` | 更新 SMTP 配置 |
| GET | `/config/github` | 获取 GitHub 配置 |
| POST | `/config/github` | 更新 GitHub 配置 |
| GET | `/tools` | 获取工具列表 |
| GET | `/tools/pending` | 获取待审批工具 |
| POST | `/tools/approve` | 审批工具 |
| POST | `/tools/reload` | 重载工具 |
| POST | `/chat` | 非流式聊天 |
| GET | `/system-messages` | 获取系统消息(?limit=&category=) |
| POST | `/system-messages/{id}/read` | 标记已读 |
| POST | `/system-messages/read-all` | 全部标为已读 |
| DELETE | `/system-messages` | 清空系统消息 |
| GET | `/memory/status` | 向量记忆状态 |
| GET | `/local-llm/status` | 本地 LLM 状态 |
| GET | `/model-selector/stats` | 模型选择器统计 |
| GET | `/monitor/episodes` | 历史执行记录(?count=) |
| GET | `/monitor/statistics` | 执行统计聚合 |
| GET | `/usage-stats/overview` | 用量统计总览 |
| GET | `/usage-stats/model-analysis` | 模型分析 |
| GET | `/tunnel/status` | Tunnel 状态 |
| POST | `/tunnel/start` | 启动 Tunnel |
| POST | `/tunnel/stop` | 停止 Tunnel |
| POST | `/tunnel/restart` | 重启 Tunnel |
| GET | `/tunnel/lan-info` | 局域网信息 |
| GET | `/permissions/status` | 权限状态 |
| GET | `/logs/backend` | 后端日志 |

---

## 四、数据模型 (TypeScript 类型)

```typescript
// 消息
interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  timestamp: string; // ISO 8601
  toolCalls?: ToolCall[];
  isStreaming: boolean;
  modelName?: string;
  attachments?: MessageAttachment[];
  tokenUsage?: TokenUsage;
}

interface MessageAttachment {
  type: 'base64_image' | 'local_file' | 'url';
  data: string;
  mimeType?: string;
  fileName?: string;
}

interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

// 对话
interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: string;
  updatedAt: string;
}

// 工具
interface ToolDefinition {
  name: string;
  description: string;
  parameters: Record<string, any>;
  category?: string;
  source?: 'system' | 'generated';
}

interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, any>;
  result?: ToolResult;
}

interface ToolResult {
  success: boolean;
  output: string;
}

// 系统通知
interface SystemNotification {
  id: string;
  level: 'info' | 'warning' | 'error';
  title: string;
  content: string;
  source: string;
  category: 'system_error' | 'evolution' | 'task' | 'info';
  timestamp: string;
  read: boolean;
}

// 任务进度
interface TaskProgress {
  id: string;
  taskDescription: string;
  status: 'running' | 'completed' | 'failed';
  currentIteration: number;
  totalActions: number;
  successfulActions: number;
  failedActions: number;
  startTime: string;
  endTime?: string;
  summary?: string;
}

// 动作日志
interface ActionLogEntry {
  id: string;
  actionId: string;
  actionType: string;
  reasoning: string;
  status: 'pending' | 'executing' | 'success' | 'failed';
  output?: string;
  error?: string;
  timestamp: string;
  iteration: number;
}

// 执行日志
interface ExecutionLogEntry {
  id: string;
  timestamp: string;
  level: string;
  message: string;
  toolName: string;
}

// 配置
interface BackendConfig {
  provider: string;
  model: string;
  base_url?: string;
  has_api_key: boolean;
  langchain_compat: boolean;
  langchain_installed: boolean;
  remote_fallback_provider?: string;
  cloud_providers_configured?: CloudProviderConfigured[];
}

interface CloudProviderConfigured {
  provider: string;
  base_url?: string;
  model: string;
  has_api_key: boolean;
}

// 待审批工具
interface PendingTool {
  tool_name: string;
  filename: string;
}
```

---

## 五、用户旅程流程

### 5.1 首次打开
1. 打开 Web 页面 → 建立 WebSocket 连接(ws://127.0.0.1:8765/ws)
2. 收到 `connected` 消息 → 更新连接状态为"已连接"
3. 加载工具列表(GET /tools)、配置(GET /config)、系统消息
4. 显示欢迎页(WelcomeView) → 用户看到功能介绍
5. 自动创建一个新对话

### 5.2 普通聊天
1. 用户在输入框输入文字 → Enter 发送
2. 用户消息添加到对话 → 创建空助手消息(isStreaming=true)
3. 通过 WebSocket 发送 `{type:"chat", content, session_id}`
4. 逐步接收 `content` chunk → 更新助手消息内容
5. 收到 `done` → 标记 isStreaming=false，显示模型名和 Token
6. 期间可能收到 `tool_call` → 更新工具面板历史Tab
7. 期间可能收到 `image` → 在消息中内联显示图片

### 5.3 自主任务执行
1. 用户输入任务描述 → 点击 🤖 按钮
2. 用户消息加前缀 "🤖 [自主任务]" → 创建助手消息 "正在启动自主执行..."
3. 通过 WebSocket 发送 `{type:"autonomous_task", task, session_id}`
4. 依次接收事件流:
   - `model_selected` → 显示选择的模型类型/原因
   - `task_start` → 更新任务进度面板
   - `llm_request_start/end` → 更新 LLM 请求日志
   - `action_plan` → 显示步骤规划
   - `action_executing` → 步骤执行中
   - `action_result` → 步骤结果（成功/失败）
   - `reflect_start/result` → 反思分析
   - `task_complete` → 任务完成统计
5. 聊天消息中逐步追加格式化的执行日志
6. 工具面板"任务"Tab 实时显示进度

### 5.4 断线重连
1. WebSocket 断开 → 状态变为"未连接"，红色指示灯
2. 自动尝试重连（指数退避）
3. 重连成功 → 收到 `connected` 消息
4. 检查 `has_running_task` / `has_running_chat` / `has_buffered_chat`
5. 如有运行中任务 → 发送 `resume_task` 或 `resume_chat` 恢复
6. 继续接收流式输出

### 5.5 设置配置
1. 点击设置按钮 → 打开设置弹窗
2. 切换 Tab 查看各项设置
3. 修改 AI 提供商 → 自动同步到后端 (POST /config)
4. 配置 SMTP → 保存同步 (POST /config/smtp)
5. 安装 LangChain → POST /config/install-langchain
6. 关闭设置 → 回到主界面

---

## 六、赛博朋克主题色值

```css
:root {
  /* 背景 */
  --cyber-bg0: #0A0A14;        /* 最深背景 */
  --cyber-bg1: #0F0F1A;        /* 侧边栏/面板背景 */
  --cyber-bg2: #16162A;        /* 卡片/气泡背景 */
  --cyber-bg-highlight: #1E1E3A; /* 悬停高亮 */
  
  /* 主色调 */
  --cyber-cyan: #00E5FF;        /* 主高亮色 */
  --cyber-cyan-dim: rgba(0, 229, 255, 0.5);
  --cyber-purple: #B388FF;      /* 紫色（LLM活动） */
  --cyber-green: #00E676;       /* 成功/在线 */
  --cyber-red: #FF5252;         /* 错误/停止 */
  --cyber-orange: #FFB74D;      /* 警告/执行中 */
  --cyber-yellow: #FFD740;      /* 特殊状态 */
  
  /* 文字 */
  --cyber-text-primary: #E0E0FF;  /* 主要文字 */
  --cyber-text-second: rgba(224, 224, 255, 0.6); /* 次要文字 */
  
  /* 边框 */
  --cyber-border: rgba(0, 229, 255, 0.12);
  
  /* 字体 */
  --font-mono: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
}
```

---

## 七、开发优先级与迭代计划

### Phase 1 - 核心功能 (P0) — ✅ 全部完成
1. ✅ 主布局框架 + 赛博朋克主题
2. ✅ WebSocket 连接管理 + 自动重连
3. ✅ 对话侧边栏（新建/选择/删除/持久化）
4. ✅ 聊天对话（消息列表/流式输出/Markdown/代码块/图片）
5. ✅ 输入栏（多行/发送/停止/自主任务）
6. ✅ 错误提示
7. ✅ 设置面板（模型配置 + 连接状态）

### Phase 2 - 完整体验 (P1) — 🔧 大部分完成
8. ✅ 工具面板（矩阵/历史/任务/日志）
9. ✅ 系统消息面板 + 通知铃铛 + 分类Tab
10. ✅ 监控仪表板（执行时间轴/日志流/系统状态）
11. 🔧 设置完善（✅ 模型配置 / ❌ 工具审批 / ❌ 远程回退 / 🔧 服务管理）
12. ✅ 思考块折叠/模型信息/自动标题
13. ✅ 快捷键支持（Cmd+N、Cmd+,、Cmd+Shift+Enter）
14. ✅ 响应式适配

### Phase 3 - 进阶功能 (P2) — ❌ 待做
15. ❌ 语音输入/TTS
16. ❌ 监控统计图表（STATS/HIST标签）
17. ❌ Tunnel 管理
18. ❌ 邮件配置
19. ❌ LangChain 管理
20. ❌ 权限检测展示
21. ❌ 历史任务分析

---

## 八、Web 端与 Mac App 差异点

| 场景 | Mac App | Web 端方案 |
|------|---------|-----------|
| 本地文件图片 | 直接读取本地路径 | 通过后端 API 代理读取（需新增 `/files/read` 端点）|
| TTS 朗读 | macOS 原生 AVSpeechSynthesizer | Web Speech API (speechSynthesis) |
| 语音输入 | macOS SFSpeechRecognizer | Web Speech API (SpeechRecognition) |
| 服务启停 | ProcessManager 直接管理进程 | 仅显示状态，后端需提供 API |
| 系统权限 | 直接检测 macOS 权限 | 通过 GET /permissions/status 获取 |
| 对话存储 | UserDefaults (本地) | localStorage / IndexedDB |
| 设置存储 | @AppStorage (本地) | localStorage + 后端 /config 同步 |
| 截图预览 | NSImage 直接加载本地路径 | Base64 编码通过 WebSocket 传输（已支持）|
| 进程管理 | 启停 backend/ollama | Web 端只读状态，或通过后端 API 控制 |
| 剪贴板 | NSPasteboard | navigator.clipboard API |
| 键盘快捷键 | macOS native (Cmd+N 等) | document.addEventListener('keydown') |
