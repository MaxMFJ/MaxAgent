# Mac App UI 指南

Chow Duck Mac 应用设置面板包含 12 个页签，覆盖服务配置、安全审计、MCP 管理等完整功能。

---

## 设置页签一览

| 序号 | 页签 | 视图文件 | 说明 |
|------|------|---------|------|
| 0 | 服务管理 | `ServiceManagerView.swift` | 后端/Ollama 启停、连接状态 |
| 1 | 服务配置 | `SettingsView.swift` (内联) | LLM Provider/API Key/Model/Tunnel |
| 2 | 通用 | `SettingsView.swift` (内联) | 语言、主题、LangChain 开关 |
| 3 | 邮件 | `SettingsView.swift` (内联) | SMTP 配置 |
| 4 | 模型 | `SettingsView.swift` (内联) | 多模型路由、Tier 配置 |
| 5 | 工具 | `ToolSettingsContent` | 工具启用/禁用、审批队列 |
| 6 | 权限 | `PermissionSettingsContent` | 辅助功能/屏幕录制/自动化 |
| 7 | 关于 | `AboutContent` | 版本信息 |
| **8** | **MCP** | `MCPSettingsView.swift` | MCP 服务器连接管理 |
| **9** | **功能开关** | `FeatureFlagsSettingsView.swift` | FeatureFlag 热切换 |
| **10** | **审计日志** | `AuditLogView.swift` | 全量操作审计查看 |
| **11** | **上下文** | `ContextVisualizationView.swift` | Token/文件/模型路由可视化 |

此外还有嵌入主界面的组件：

| 组件 | 视图文件 | 触发方式 |
|------|---------|---------|
| 快照回滚 | `RollbackPanelView.swift` | 工具面板 / 任务详情 |
| HITL 确认 | `HITLOverlayView.swift` | 后端推送危险动作时弹出 |

---

## 各页签详细说明

### MCP 服务管理（页签 8）

**文件**: `MacAgentApp/Views/MCPSettingsView.swift`

**功能区域**:

1. **内置 MCP 目录**
   - 显示 6 个预配置的 MCP 服务卡片
   - 每个卡片显示：图标、名称、描述、安装提示
   - 操作：点击"+"连接 → 显示加载动画 → 成功显示绿色勾号
   - 已连接：点击勾号断开

2. **已连接服务列表**
   - 显示所有已连接的 MCP 服务器状态
   - 每项显示：连接状态（绿/橙圆点）、传输方式、工具数量
   - 操作：刷新、删除

3. **添加自定义 MCP**
   - 蓝色"添加"按钮打开弹窗
   - 支持 stdio（输入命令）或 http（输入 URL）
   - 输入名称和命令后点击"添加"

4. **MCP 工具列表**
   - 列出所有已连接服务器提供的工具
   - 显示完整名称（`server/tool_name`）和描述

**内置 MCP 目录**:

| 服务 | npm 包 | 图标 | 颜色 |
|------|--------|------|------|
| GitHub MCP | `@modelcontextprotocol/server-github` | `chevron.left.forwardslash.chevron.right` | 紫色 |
| Brave Search MCP | `@modelcontextprotocol/server-brave-search` | `magnifyingglass` | 橙色 |
| Sequential Thinking MCP | `@modelcontextprotocol/server-sequential-thinking` | `brain.head.profile` | 青色 |
| Browser Automation MCP | `@modelcontextprotocol/server-puppeteer` | `safari` | 红色 |
| Filesystem MCP | `@modelcontextprotocol/server-filesystem` | `folder` | 黄色 |
| Memory MCP | `@modelcontextprotocol/server-memory` | `brain` | 薄荷色 |

---

### 功能开关（页签 9）

**文件**: `MacAgentApp/Views/FeatureFlagsSettingsView.swift`

**功能**:
- 列出所有 FeatureFlag 及其当前状态
- Toggle 开关实时切换（通过 `PATCH /feature-flags` API）
- 显示 Flag 来源（默认值 / 环境变量 / 运行时覆盖）
- "重置全部"按钮恢复默认值

**可用 Flag** (v3.3+):

| Flag | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_HITL` | false | 人工审批开关 |
| `ENABLE_AUDIT_LOG` | true | 审计日志开关 |
| `ENABLE_SESSION_RESUME` | false | 会话恢复/Fork |
| `ENABLE_SUBAGENT` | false | SubAgent 并行 |
| `ENABLE_IDEMPOTENT_TASKS` | false | 幂等任务去重 |
| `ENABLE_VECTOR_SEARCH` | false | BGE 向量搜索 |
| `ENABLE_EVOMAP` | false | EvoMap 进化网络 |

---

### 审计日志（页签 10）

**文件**: `MacAgentApp/Views/AuditLogView.swift`

**功能**:
- 全量操作审计记录列表
- 按类型过滤（tool_call / file_write / shell_exec / config_change 等）
- 按日期范围过滤
- 查看单条记录详情（操作参数、结果、时间戳）
- 审计统计摘要

**对应 API**: `GET /audit`, `GET /audit/stats`, `GET /audit/{log_id}`

---

### 上下文可视化（页签 11）

**文件**: `MacAgentApp/Views/ContextVisualizationView.swift`

**功能**:
- Token 用量统计（已用 / 上限 / 百分比）
- 会话创建的文件列表
- 模型路由统计（Fast/Strong/Cheap 调用次数与分布）
- Phase 阶段统计（Gather/Act/Verify 计数）
- MCP 状态概览（已连接服务器、可用工具数）
- 活跃任务状态
- 快照数量

**对应 API**: `GET /context`

---

### 快照回滚面板

**文件**: `MacAgentApp/Views/RollbackPanelView.swift`

**功能**:
- 文件操作快照列表（按时间倒序）
- 每项显示：操作类型（write/delete/move/copy）、文件路径、时间
- 一键回滚：恢复到指定快照点
- 按 task_id / session_id 过滤

**对应 API**: `GET /rollback/snapshots`, `POST /rollback`

---

### HITL 人工审批弹窗

**文件**: `MacAgentApp/Views/HITLOverlayView.swift`

**功能**:
- 后端检测到危险操作时自动弹出确认窗口
- 显示：操作类型、目标路径/命令、风险等级
- 操作按钮：✅ 确认执行 / ❌ 拒绝执行
- 超时自动拒绝（默认 120 秒）

**触发条件**（`ENABLE_HITL=true` 时）:
- 删除文件/目录
- 执行包含 `rm`/`sudo`/`kill` 的 shell 命令
- 修改系统配置
- 其他后端标记为"高风险"的操作

**对应 API**: `GET /hitl/pending`, `POST /hitl/confirm/{id}`, `POST /hitl/reject/{id}`
