# Chow Duck - macOS AI 智能助手

基于 SwiftUI + Python 后端的 macOS 本地 AI Agent。支持**流式对话（ReAct）**与**自主长任务（Autonomous）**两种模式，具备多模型选择、上下文向量检索、技能 Capsule、工具自我升级与自愈能力，Mac/iOS 多端会话同步。内置**监控仪表板**、**语音输入**、**TTS 朗读**、**权限管理**、**Cloudflare Tunnel**、**MCP 生态集成**等完整能力。

---

## 功能特性

### 对话与执行模式
- **流式对话（Chat）**：ReAct 循环，按需调用工具（文件、终端、应用、截图、邮件等），支持断线重连与输出恢复
- **自主任务（Autonomous）**：长 horizon 多步执行，三阶段主循环（Gather → Act → Verify），可选反思、模型选择（本地/云端）、自适应停止
- **Prompt 与 Token 优化**：简单查询用 LITE system prompt，复杂任务用 FULL；上下文 token 上限 2000，工具 schema 按查询语义裁剪（最多 8 个），减少无效 token
- **LangChain 兼容**：可选启用 LangChain 进行对话（需安装 `requirements-langchain.txt`），与原生引擎并存、可随时切换

### 基础与扩展工具
- **基础**：文件操作、终端命令、应用控制、系统信息、剪贴板、脚本执行、截图、浏览器、邮件、日历、通知
- **扩展**：Docker、网络诊断、数据库查询、开发工具、联网搜索（DuckDuckGo/维基）、动态工具生成、视觉、鼠标键盘模拟
- **Generated 工具**：隧道监控、隧道管理、交互式邮件等（Self-Upgrade 产出 + 手写，动态加载）
- **MCP 生态**：通过 Model Context Protocol 连接外部 MCP 服务器（GitHub、Brave Search、Filesystem 等），即插即用
- **统一工具路由**：内置工具优先，MCP 作为 fallback；同名工具自动遮蔽，LLM 无感知切换
- **Agent 能力**：请求工具升级（Self-Upgrade）、EvoMap 技能（可选）、技能 Capsule（本地 + 开放技能源，v3.2 支持按需拉取）

### Mac 客户端能力
- **监控仪表板**：执行时间线、系统状态、历史分析、实时日志流、用户平台统计（Token/RPM/TPM、模型分布）
- **MCP 管理**：内置 6 个 MCP 服务一键连接（GitHub / Brave Search / Sequential Thinking / Puppeteer / Filesystem / Memory），支持自定义添加
- **上下文可视化**：Token 用量、文件清单、模型路由统计、Phase 阶段统计
- **功能开关**：FeatureFlag 热切换，支持运行时调整无需重启
- **审计日志**：全量操作审计查看器，支持类型 / 日期过滤
- **快照回滚**：文件操作快照列表、一键回滚
- **HITL 人工审批**：危险操作弹窗确认（如删除文件、执行高风险命令），可拒绝
- **语音输入**：实时语音识别（中/英）、静音自动提交、无说话超时提交
- **TTS 朗读**：流式按句朗读、支持中英文，可随时停止
- **权限管理**：辅助功能、屏幕录制、自动化、cliclick、Quartz、osascript 状态检测与引导
- **Workspace 上下文**：上报当前工作目录、打开文件，供 prompt 注入
- **终端会话增强**：记录 cwd/输出，供后续命令和 prompt 复用

### v3.3 人机协同与安全
- **FeatureFlag 体系化**：REST API + 热更新 + 持久化（运行时 > JSON > 环境变量 > 默认值）
- **HITL 人工审批**：关键动作需用户确认，可配超时（默认 120s）
- **统一审计日志**：全量操作记录（`data/audit/`），磁盘自动轮转（默认上限 100MB）
- **会话恢复/分支**：Session Resume / Fork，从检查点恢复或分支新会话
- **SubAgent 并行**：任务拆分给子 Agent 并行执行（最多 3 个，可配）
- **幂等任务**：同一 task hash 不重复执行（24h TTL）

### v3.4 MCP 生态与可回滚
- **MCP 生态集成**：支持 stdio（npx 子进程）和 HTTP 两种传输；配置持久化，启动自动重连
- **统一工具路由器**（Unified Tool Router）：`Agent → ToolRouter → Builtin Tools → MCP Fallback`
  - 内置工具优先级最高，LLM 直接使用
  - MCP 工具：与内置重名的注册为 `mcp/` 前缀（隐藏），仅在内置失败时自动 fallback
  - MCP 独有工具：以 `{server}_{tool}` 格式暴露给 LLM
- **三级模型路由**：Fast（本地/低延迟）/ Strong（旗舰远程）/ Cheap（性价比），按任务复杂度自动选择
- **可回滚操作**：文件操作前自动快照（最多 500 条），支持 write/delete/move/copy 一键 undo
- **三阶段执行**：Gather → Act → Verify，自动验证执行结果并注入 LLM 上下文
- **上下文查询**：`/context` API 提供完整运行时状态快照（Token / 文件 / 路由 / MCP / 快照）

### 架构与运维
- **上下文与记忆**：BGE 向量检索（可关）、会话持久化、情景记忆与策略 DB、任务上下文（目标应用绑定）；v3.2 支持重要性加权 memory
- **EventBus 解耦**：错误收集、自愈建议、升级触发通过事件总线，不侵入主循环
- **工具自我升级**：Planner → Strategy → Executor → Validation → Activation，沙箱执行（resource_dispatcher）
- **自愈**：诊断引擎、修复计划与执行，支持 HTTP 与 WebSocket 调用；v3.2 支持失败分类反思（7 种 FailureType）
- **系统消息与日志**：统一系统通知、启动日志分析（错误模式匹配与用户提示）
- **多客户端**：Mac/iOS 同时连接，按 session 同步；可选 Cloudflared 隧道 + Token 认证
- **Tunnel 生命周期**：Cloudflared 隧道自动启停、局域网信息、自动启动配置

### v3.2 可观测与可评估
- **Trace 完善**：span 级 token 统计、工具调用记录、`get_trace_summary` / `list_traces` / `get_trace_spans` / `delete_trace`
- **Traces REST API**：`GET /traces`、`GET /traces/{task_id}`、`GET /traces/{task_id}/spans`、`DELETE /traces/{task_id}`
- **深度健康检查**：`GET /health/deep` 8 子系统（LLM、磁盘、内存、vector_db、tool_router、task_tracker、traces、evomap）
- **Benchmark 自动化**：`scripts/run_benchmark.py` B1-B7 用例，WebSocket 自动执行并汇总

---

## 系统要求

- **macOS 14.0+**
- **Python 3.10+**
- **Node.js 18+**（MCP 服务器需要，自动发现 Homebrew keg-only 安装如 `node@22`）
- **Xcode 15.0+**（编译 SwiftUI 应用）

---

## 快速开始

### 1. 安装 Python 依赖

```bash
cd MacAgent/backend
pip install -r requirements.txt
```

### 2. 配置 LLM

**方式一：环境变量**
```bash
export DEEPSEEK_API_KEY="your-api-key-here"
# 可选：LLM_BASE_URL、LLM_MODEL
```

**方式二：在 Mac 应用设置中配置**  
启动应用后，在设置中选择 Provider（DeepSeek / New API / Ollama / LM Studio）并填写 API Key、Base URL、模型名。

### 3. 启动后端

```bash
cd MacAgent/backend
python main.py
```

服务地址：`http://127.0.0.1:8765`，WebSocket：`ws://127.0.0.1:8765/ws`。

### 4. 启动 Mac 应用

启动后，工具栏可控制**后端**、**Ollama** 启停，打开**监控仪表板**（执行时间线、系统状态、历史分析、日志流、Token 统计），展开**工具面板**与**系统消息**。点击**齿轮**打开设置，可配置服务、远程隧道、模型、通用（含 LangChain 兼容）、邮件、工具、**权限**（快捷管理辅助功能、屏幕录制、自动化等）等。

**Xcode**
```bash
open MacAgent/MacAgentApp/MacAgentApp.xcworkspace   # 若使用 CocoaPods
# 或
open MacAgent/MacAgentApp/MacAgentApp.xcodeproj
```
在 Xcode 中运行。

**命令行编译**
```bash
cd MacAgent/MacAgentApp
xcodebuild -project MacAgentApp.xcodeproj -scheme MacAgentApp -configuration Debug build
```

---

## 使用 Ollama / LM Studio 本地模型

1. 安装 [Ollama](https://ollama.ai/) 或 LM Studio，并拉取模型（如 `ollama pull qwen2.5-coder:7b`）
2. 在应用设置中选择「Ollama」或「LM Studio」，配置对应地址与模型名
3. 自主任务可勾选「自动选模型」，由后端按任务复杂度选择本地/云端

---

## MCP 服务器管理

通过 MCP（Model Context Protocol）连接外部工具服务器，扩展 Agent 能力。

### Mac App 内置目录（一键连接）

| MCP 服务 | 包名 | 说明 | 前置条件 |
|----------|------|------|---------|
| GitHub | `@modelcontextprotocol/server-github` | 仓库/PR/Issues/代码搜索 | `GITHUB_TOKEN` 环境变量 |
| Brave Search | `@modelcontextprotocol/server-brave-search` | 隐私优先网页搜索 | `BRAVE_API_KEY` 环境变量 |
| Sequential Thinking | `@modelcontextprotocol/server-sequential-thinking` | 增强推理与问题分解 | Node.js 18+ |
| Puppeteer | `@modelcontextprotocol/server-puppeteer` | 浏览器自动化 | Node.js 18+ |
| Filesystem | `@modelcontextprotocol/server-filesystem` | 沙箱文件操作 | Node.js 18+ |
| Memory | `@modelcontextprotocol/server-memory` | 知识图谱/跨会话记忆 | Node.js 18+ |

### 命令行手动添加

```bash
# 添加 MCP 服务器
curl -X POST http://127.0.0.1:8765/mcp/servers \
  -H 'Content-Type: application/json' \
  -d '{"name": "memory", "transport": "stdio", "command": ["npx", "-y", "@modelcontextprotocol/server-memory"]}'

# 查看已连接的服务器
curl http://127.0.0.1:8765/mcp/servers

# 查看所有 MCP 工具
curl http://127.0.0.1:8765/mcp/tools

# 调用 MCP 工具
curl -X POST http://127.0.0.1:8765/mcp/tools/call \
  -H 'Content-Type: application/json' \
  -d '{"server": "memory", "tool": "search_nodes", "arguments": {"query": "test"}}'
```

### 统一工具路由策略

MCP 工具通过 **Unified Tool Router** 与内置工具无缝协作：

1. **内置工具优先**：Agent 执行时始终优先使用 20+ 内置工具（file_tool、terminal_tool 等）
2. **MCP 自动 Fallback**：当内置工具执行失败时，自动尝试同名 MCP 替代
3. **MCP 独有工具直接暴露**：内置没有的 MCP 工具（如 `search_nodes`）直接以 `{server}_{tool}` 格式对 LLM 可见
4. **LLM 无感知**：重名的 MCP 工具注册为 `mcp/` 前缀（隐藏），LLM 不会看到重复工具

---

## Xcode 运行后权限保留

从 Xcode 运行若每次都要重新在「系统设置 → 隐私与安全性」授权（辅助功能、自动化等），是因为默认构建到 DerivedData，路径会变，系统按路径记权限。

**建议**：固定构建路径，一次授权长期有效。

1. 用 Xcode 打开 **MacAgentApp.xcworkspace**（使用 CocoaPods 时务必用 workspace）
2. **File → Workspace Settings…**（或 Project Settings）
3. **Build Location** 选 **Custom**，再选 **Relative to Workspace** 或固定目录（如项目下 `Build`）
4. 重新编译运行，在系统设置中对该路径下的 **MacAgentApp** 授权一次

若出现 **「Framework 'Pods_MacAgentApp' not found」**，请确认已用 `.xcworkspace` 打开并执行过 `pod install`。

---

## 权限管理（Mac App）

权限配置在 **设置 → 权限** 中完成。**快捷入口**：点击工具栏齿轮图标 → 设置 → 权限。

### 权限项与快捷操作

| 权限 | 用途 | 快捷操作 |
|------|------|----------|
| App 辅助功能 | MacAgentApp 自身控制键鼠 | 「请求权限」弹窗 / 「打开系统设置」 |
| Python 辅助功能 | 后端模拟键鼠（Agent 核心） | 「打开辅助功能设置」；路径可复制，⌘⇧G 前往文件夹 |
| 屏幕录制 | 截图、视觉感知 | 「打开屏幕录制设置」 |
| 自动化 (System Events) | AppleScript 控制其他应用 | 「打开自动化设置」 |

### 快捷提示

- **刷新状态**：授权后需重启后端（或重启电脑）才能生效，点击「刷新状态」或「重启后端并重新检测」验证
- **Python 路径在 .app 包内**：系统文件选择器可能无法直接选中，使用 **⌘⇧G** 在「前往文件夹」中粘贴完整路径
- **工具可用性**：页面底部显示 CGEvent、cliclick、osascript 状态；cliclick 未安装时执行 `brew install cliclick`

---

## 打包与后台内置

**后台已内置到 Mac App**：构建时通过 Build Phase 将 `backend/` 复制到 `MacAgentApp.app/Contents/Resources/backend/`，用户无需单独部署后端。

- **体积**：~180MB（仅核心依赖）。RAG/向量搜索（~600MB）在用户首次启用时自动安装到 Application Support，0 操作。

- **启动/关闭**：应用内工具栏或服务管理页的「后端」开关控制启停
- **可写数据**：Bundle 内 `data/` 只读，配置持久化到 `~/Library/Application Support/com.macagent.app/backend_data/`
- **路径**：`ProcessManager.getBackendPath()` 优先使用 Bundle 内 backend，开发时回退到项目 `backend/`

详见 `docs/archive/打包技术路线-后台集成.md`。更多文档见 `docs/`（含后台功能清单、自愈测试指南等）。

---

## 项目结构

```
MacAgent/
├── MacAgentApp/                   # macOS 客户端 (SwiftUI)
│   └── MacAgentApp/
│       ├── MacAgentApp.swift
│       ├── ContentView.swift
│       ├── ViewModels/AgentViewModel.swift, MonitoringViewModel.swift
│       ├── Services/BackendService.swift, ProcessManager.swift, TunnelManager.swift
│       │         VoiceInputService.swift, TTSService.swift, PermissionManager.swift
│       ├── Models/Message.swift
│       └── Views/
│           ├── 聊天/              # ChatView, InputBar, MessageBubble, RichMarkdownView, ImageDisplayView...
│           ├── Monitoring/        # MonitoringWindowView, ExecutionTimelineView, UsageStatisticsView...
│           ├── SettingsView, ToolPanelView, SystemMessageView, TunnelView
│           ├── MCPSettingsView    # MCP 服务管理（6 个内置 + 自定义添加）（v3.4）
│           ├── FeatureFlagsSettingsView  # 功能开关热切换（v3.3）
│           ├── AuditLogView       # 审计日志查看器（v3.3）
│           ├── ContextVisualizationView  # 上下文可视化（v3.4）
│           ├── RollbackPanelView  # 快照回滚面板（v3.4）
│           ├── HITLOverlayView    # 人工审批弹窗（v3.3）
│           └── ServiceManagerView, PermissionSettingsView
│
├── iOSAgentApp/                   # iOS 客户端（可选）
│
├── backend/                       # Python FastAPI 后端
│   ├── main.py                    # 入口、lifespan、路由与 WebSocket 注册
│   ├── app_state.py               # 全局状态、TaskTracker、Feature Flags（含 v3.2）
│   ├── auth.py                    # 隧道认证
│   ├── connection_manager.py      # WebSocket 连接与按 session 广播
│   ├── ws_handler.py              # /ws 消息分发（chat/stop/autonomous/resume/monitor_event...）
│   ├── config/                    # llm_config, smtp_config, github_config, agent_config（合并原根目录）
│   ├── core/                      # v3 框架层（error_model, task_state_machine, trace_logger v3.2）
│   ├── data/                      # llm_config, smtp, github, contexts/, episodes/, traces/
│   │
│   ├── routes/                    # HTTP 路由
│   │   ├── health.py              # /health, /health/deep（v3.2）, /server-status, /connections
│   │   ├── auth_routes.py         # /auth/status, generate-token, disable
│   │   ├── config.py              # /config, /config/smtp, /config/github, /config/install-langchain
│   │   ├── tools.py               # /tools, /tools/pending, approve, reload
│   │   ├── upgrade.py             # /upgrade/self, trigger, restart
│   │   ├── logs.py                # /logs, /system-messages
│   │   ├── memory.py              # /memory/status, /local-llm/status, /model-selector/*
│   │   ├── self_healing.py        # /self-healing/*, /ws/self-healing
│   │   ├── evomap.py              # /evomap/*（ENABLE_EVOMAP=true 时）
│   │   ├── capsules.py           # /capsules, /capsules/find, execute
│   │   ├── chat.py                # POST /chat 非流式
│   │   ├── monitor.py            # /monitor/episodes, /monitor/statistics
│   │   ├── usage_stats.py        # /usage-stats/overview, /usage-stats/model-analysis
│   │   ├── tunnel.py             # /tunnel/status, start, stop, restart, lan-info, auto-start
│   │   ├── workspace.py          # POST /workspace（上报 cwd、open_files）
│   │   ├── permissions.py        # /permissions/status
│   │   ├── traces.py             # /traces（v3.2 新增）
│   │   ├── files.py              # /files/* 文件读写
│   │   ├── mcp.py                # /mcp/servers, /mcp/tools, /mcp/tools/call（v3.4）
│   │   ├── rollback.py           # /rollback/snapshots, /rollback（v3.4）
│   │   ├── context.py            # /context, /context/tokens, /context/files（v3.4）
│   │   ├── feature_flags.py      # /feature-flags CRUD + reset（v3.3）
│   │   ├── audit.py              # /audit, /audit/stats（v3.3）
│   │   ├── hitl.py               # /hitl/pending, confirm, reject（v3.3）
│   │   ├── sessions.py           # /sessions, resume, fork（v3.3）
│   │   └── subagents.py          # /subagents 状态查询（v3.3）
│   │
│   ├── agent/                     # Agent 核心与周边
│   │   ├── core.py                # AgentCore ReAct 循环
│   │   ├── autonomous_agent.py    # 自主任务、反思、模型选择
│   │   ├── exec_phases.py        # Gather→Act→Verify 三阶段（v3.4）
│   │   ├── snapshot_manager.py   # 文件快照与回滚管理（v3.4）
│   │   ├── mcp_client.py         # MCP 连接器（stdio/http 双传输）（v3.4）
│   │   ├── model_selector.py     # 三级路由 Fast/Strong/Cheap（v3.4）
│   │   ├── llm_client.py         # 统一 LLM 客户端（v3.2：extra_body/Extended Thinking）
│   │   ├── local_llm_manager.py   # 本地模型检测
│   │   ├── model_selector.py     # 任务→模型选择
│   │   ├── prompt_loader.py      # LITE/FULL system prompt、进化规则
│   │   ├── context_manager.py    # 对话上下文、向量检索
│   │   ├── vector_store.py       # BGE 嵌入与语义检索
│   │   ├── task_context_manager.py# 目标应用解析与绑定
│   │   ├── episodic_memory.py    # 情景记忆（v3.2：重要性加权）
│   │   ├── reflect_engine.py     # 反思（v3.2：失败分类 + 专用 prompt）
│   │   ├── web_augmented_thinking.py  # 联网增强
│   │   ├── local_tool_parser.py   # 本地模型 tool_calls 解析
│   │   ├── capsule_on_demand.py  # v3.2 按需拉取 Skill
│   │   ├── event_bus.py, error_service.py, self_healing_worker.py, upgrade_service.py
│   │   ├── system_message_service.py, log_analyzer.py
│   │   ├── self_upgrade/         # 工具自我升级
│   │   ├── self_healing/         # 自愈
│   │   ├── capsule_*.py         # Capsule 加载、执行、校验、开放技能源
│   │   ├── evomap_*.py          # EvoMap 服务与升级钩子（可选）
│   │   ├── stop_policy.py       # 自主任务自适应停止
│   │   ├── resource_dispatcher.py # 升级任务沙箱执行
│   │   ├── usage_tracker.py     # Token/RPM/TPM 统计
│   │   ├── workspace_context.py # 工作区 cwd、open_files
│   │   ├── terminal_session.py  # 终端 cwd 与输出记录
│   │   └── ...
│   │
│   ├── tools/                    # 工具实现
│   │   ├── base.py, registry.py, router.py, schema_registry.py, validator.py, middleware.py
│   │   ├── mcp_adapter.py        # MCP→BaseTool 适配器、统一工具路由 fallback（v3.4）
│   │   ├── file_tool, terminal_tool, app_tool, system_tool, clipboard_tool
│   │   ├── script_tool, screenshot_tool, browser_tool, mail_tool, calendar_tool
│   │   ├── notification_tool, docker_tool, network_tool, database_tool
│   │   ├── developer_tool, web_search_tool, dynamic_tool_generator, vision_tool
│   │   ├── input_control_tool, request_tool_upgrade_tool, evomap_tool, capsule_tool
│   │   └── generated/             # 动态加载（tunnel_monitor, tunnel_manager, interactive_mail 等）
│   │
│   ├── services/                  # 业务服务层
│   │   ├── tunnel_lifecycle.py    # Cloudflared 隧道生命周期
│   │   ├── feature_flag_service.py # FeatureFlag 管理与持久化（v3.3）
│   │   ├── audit_service.py      # 审计日志记录与查询（v3.3）
│   │   ├── hitl_service.py       # HITL 确认管理与超时（v3.3）
│   │   ├── session_service.py    # 会话恢复与 Fork（v3.3）
│   │   ├── subagent_service.py   # SubAgent 调度（v3.3）
│   │   └── idempotent_service.py # 幂等任务去重（v3.3）
│   ├── llm/                       # tool_parser_v2, json_repair
│   ├── runtime/                   # RuntimeAdapter, mac_adapter, permission_checker, cg_event
│   └── scripts/                   # run_benchmark.py（v3.2）, check_ollama.py 等
│
└── docs/
    ├── README.md                  # 文档总览与主线目标点
    ├── backend-structure.md       # 后端目录与模块说明
    ├── 主线目标与路线图.md
    ├── 痛点分析与解决方案.md
    ├── v3.2_PLAN.md               # v3.2 功能清单（可观测、Benchmark）
    ├── v3.3_PLAN.md               # v3.3 功能清单（人机协同、安全增强）
    ├── v3.4_PLAN.md               # v3.4 功能清单（MCP、回滚、模型路由）
    ├── Mac-App-UI-Guide.md        # Mac App 全部设置页说明
    ├── API-Endpoints.md           # REST API 完整端点参考
    ├── V3.1_PLAN.md
    ├── 测试与验收.md
    └── archive/                   # 历史与专项文档
```

---

## 扩展工具

1. **在 `backend/tools/` 下新建工具类**（继承 `BaseTool`，接收 `runtime_adapter` 注入）：

```python
# backend/tools/my_tool.py
from .base import BaseTool, ToolResult, ToolCategory

class MyTool(BaseTool):
    name = "my_tool"
    description = "我的自定义工具"
    parameters = {
        "type": "object",
        "properties": {"param1": {"type": "string", "description": "参数1"}},
        "required": ["param1"]
    }
    category = ToolCategory.CUSTOM

    async def execute(self, **kwargs) -> ToolResult:
        param1 = kwargs.get("param1")
        # 实现逻辑（可访问 self.runtime_adapter）
        return ToolResult(success=True, data={"result": "done"})
```

2. **在 `tools/__init__.py` 的 `get_all_tools(runtime_adapter)` 中注册**：

```python
from .my_tool import MyTool

def get_all_tools(runtime_adapter=None):
    return [
        # ... 现有工具
        MyTool(runtime_adapter),
    ]
```

3. **重启后端**。若希望由 Self-Upgrade 自动生成，可将工具放在 `tools/generated/` 并在通过审批后调用 `POST /tools/reload`。

---

## 主要 API

| 类别 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 健康 | GET | /health, /server-status, /connections | 健康与连接数 |
| 健康 | GET | /health/deep | v3.2 深度健康检查（8 子系统）|
| 配置 | GET/POST | /config, /config/smtp, /config/github | LLM / 邮件 / GitHub；GET 含 langchain_compat，POST 可传 langchain_compat |
| 配置 | POST | /config/install-langchain | 安装 LangChain 可选依赖 |
| 工具 | GET | /tools | 工具列表 |
| 工具 | GET/POST | /tools/pending, /tools/approve, /tools/reload | 待审批、审批、重载 |
| 对话 | POST | /chat | 非流式对话 |
| 对话 | WebSocket | /ws | 流式 chat、autonomous、resume、stop、monitor_event 等 |
| 升级 | POST | /upgrade/self, /upgrade/trigger, /upgrade/restart | 自升级、触发升级、重启 |
| 日志 | GET/DELETE | /logs | 日志 |
| 系统消息 | GET/POST/DELETE | /system-messages, .../read, .../read-all | 列表、已读、删除 |
| 记忆 | GET | /memory/status, /local-llm/status, /model-selector/status | 状态 |
| 自愈 | GET/POST | /self-healing/status, /diagnose, /plan | 状态、诊断、计划 |
| 自愈 | WebSocket | /ws/self-healing | 自愈对话与执行 |
| 监控 | GET | /monitor/episodes, /monitor/statistics | 执行历史、统计摘要 |
| 统计 | GET | /usage-stats/overview, /usage-stats/model-analysis | Token/RPM/TPM、模型分布 |
| traces | GET | /traces | v3.2 列出 trace 列表 |
| traces | GET | /traces/{task_id} | v3.2 获取 trace 摘要 |
| traces | GET | /traces/{task_id}/spans | v3.2 分页获取 spans |
| traces | DELETE | /traces/{task_id} | v3.2 删除 trace |
| 隧道 | GET/POST | /tunnel/status, /tunnel/start, /tunnel/stop, /tunnel/restart, /tunnel/lan-info, /tunnel/auto-start | Cloudflare Tunnel 管理 |
| 工作区 | POST/GET | /workspace, /workspace/{session_id} | 上报 cwd、open_files |
| 权限 | GET | /permissions/status | 辅助功能、屏幕录制、自动化等状态 |
| EvoMap | GET/POST | /evomap/status, register, search, resolve, publish, events, audit | 需 ENABLE_EVOMAP=true |
| Capsule | GET/POST | /capsules, /capsules/find, /capsules/{id}, /capsules/{id}/execute | 技能胶囊 |

---

## 环境变量（可选）

| 变量 | 默认 | 说明 |
|------|------|------|
| ENABLE_VECTOR_SEARCH | true | 是否启用 BGE 向量检索 |
| EMBEDDING_MODEL | BAAI/bge-small-zh-v1.5 | 嵌入模型 |
| ENABLE_EVOMAP | false | 是否启用 EvoMap |
| MACAGENT_AUTO_TOOL_UPGRADE | true | 是否自动触发工具升级 |
| AUTH_ENABLED, AUTH_TOKEN | - | 隧道/iOS 认证（见 auth.py）|
| HF_ENDPOINT | - | 国内可设 https://hf-mirror.com 加速 BGE 下载 |

### v3.2 Feature Flags（`MACAGENT_` 前缀）

| 变量 | 默认 | 说明 |
|------|------|------|
| MACAGENT_TRACE_TOKEN_STATS | true | span 级 token 统计 |
| MACAGENT_TRACE_TOOL_CALLS | true | 工具调用写入 trace |
| MACAGENT_ENABLE_IMPORTANCE_WEIGHTED_MEMORY | true | 重要性加权 memory |
| MACAGENT_ENABLE_FAILURE_TYPE_REFLECTION | true | 失败分类反思 |
| MACAGENT_ENABLE_ON_DEMAND_SKILL_FETCH | true | 按需拉取 Skill（启动不全量同步）|
| MACAGENT_ENABLE_EXTENDED_THINKING | false | Extended Thinking / CoT |
| MACAGENT_ENABLE_IDEMPOTENT_TASKS | false | 幂等任务（实验性）|
| MACAGENT_ENABLE_SUBAGENT | false | 子 Agent（规划中）|
| MACAGENT_HEALTH_DEEP_LLM_TIMEOUT | 5.0 | /health/deep LLM 超时（秒）|

---

## Benchmark 自动化（v3.2）

```bash
cd backend
pip install websockets

# 运行所有用例（默认端口 8765）
python scripts/run_benchmark.py --url http://localhost:8765

# 运行指定用例
python scripts/run_benchmark.py --url http://localhost:8765 --cases B1,B3,B7

# 保存结果
python scripts/run_benchmark.py --url http://localhost:8765 --out ./data/benchmark_results
```

---

## CocoaPods（可选）

```bash
# Mac 客户端
cd MacAgent/MacAgentApp && pod install

# iOS 客户端
cd MacAgent/iOSAgentApp && pod install
```

安装后使用 `.xcworkspace` 打开项目。

---

## 常见日志说明

- **`LangChain compat: disabled — Chat uses native runner`**  
  表示当前未开启 LangChain 兼容（配置或环境变量为关闭），对话使用原生 Runner，**不是报错**。若需启用，在设置中打开「使用 LangChain 进行对话」或设置 `ENABLE_LANGCHAIN_COMPAT=true`。

- **`ConnectionClosedError ... keepalive ping timeout`**  
  表示客户端在约定时间内未响应 WebSocket ping，服务端主动断开连接，**属正常断线**（如应用退到后台、休眠）。重连后即可继续使用。

- **安装 LangChain 依赖后服务自动重载**  
  若在设置中点击安装 LangChain 后出现大量 `WatchFiles detected changes in 'venv/...'` 并触发重启，已通过 `reload_excludes` 排除 `venv` 目录；若仍发生，可手动重启一次后端即可。

---

## 安全说明

- 危险终端命令会被拒绝（如 `rm -rf /`）；Self-Upgrade 执行在沙箱内（`resource_dispatcher`：cwd 限制、命令黑名单、超时）
- API Key 与配置存于本地（`backend/data/`），不会上传
- 建议在沙盒或测试环境中验证新工具与升级流程

---

## Mac App 与 v3.2 兼容性

**v3.2 不破坏 v3.1 任何接口或行为**，现有 Mac App 无需修改即可与 v3.2 后端兼容。

| 项目 | 说明 |
|------|------|
| **必须改动** | 无。Mac App 使用的 `/health`、`/ws`、`/permissions/status`、`/logs` 等接口保持不变 |
| **可选增强** | 1）用 `GET /health/deep` 替代或补充 `/health`，获取 8 子系统详细状态；2）在监控仪表板中集成 `GET /traces`、`GET /traces/{task_id}/spans` 展示执行轨迹与 token 消耗 |
| **端口** | 后端仍为 `127.0.0.1:8765`，Mac App 无需调整 |

---

## 相关文档

- 文档总览与主线目标点：[docs/README.md](docs/README.md)
- 后端结构：[docs/backend-structure.md](docs/backend-structure.md)
- 主线目标与路线图：[docs/主线目标与路线图.md](docs/主线目标与路线图.md)
- v3.2 功能清单：[docs/v3.2_PLAN.md](docs/v3.2_PLAN.md)
- 痛点与方案：[docs/痛点分析与解决方案.md](docs/痛点分析与解决方案.md)
- 测试与验收：[docs/测试与验收.md](docs/测试与验收.md)

---

## 许可证

MIT License
