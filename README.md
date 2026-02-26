# MacAgent - macOS AI 智能助手

基于 SwiftUI + Python 后端的 macOS 本地 AI Agent。支持**流式对话（ReAct）**与**自主长任务（Autonomous）**两种模式，具备多模型选择、上下文向量检索、技能 Capsule、工具自我升级与自愈能力，Mac/iOS 多端会话同步。

---

## 功能特性

### 对话与执行模式
- **流式对话（Chat）**：ReAct 循环，按需调用工具（文件、终端、应用、截图、邮件等），支持断线重连与输出恢复
- **自主任务（Autonomous）**：长 horizon 多步执行，可选反思、模型选择（本地/云端）、自适应停止（任务完成/无进展/循环检测等）
- **Prompt 与 Token 优化**：简单查询用 LITE system prompt，复杂任务用 FULL；上下文 token 上限 2000，工具 schema 按查询语义裁剪（最多 8 个），减少无效 token

### 基础与扩展工具
- **基础**：文件操作、终端命令、应用控制、系统信息、剪贴板、脚本执行、截图、浏览器、邮件、日历、通知
- **扩展**：Docker、网络诊断、数据库查询、开发工具、联网搜索（DuckDuckGo/维基）、动态工具生成、视觉、鼠标键盘模拟
- **Agent 能力**：请求工具升级（Self-Upgrade）、EvoMap 技能（可选）、技能 Capsule（本地 + 开放技能源）

### 架构与运维
- **上下文与记忆**：BGE 向量检索（可关）、会话持久化、情景记忆与策略 DB、任务上下文（目标应用绑定）
- **EventBus 解耦**：错误收集、自愈建议、升级触发通过事件总线，不侵入主循环
- **工具自我升级**：Planner → Strategy → Executor → Validation → Activation，沙箱执行（resource_dispatcher）
- **自愈**：诊断引擎、修复计划与执行，支持 HTTP 与 WebSocket 调用
- **系统消息与日志**：统一系统通知、启动日志分析（错误模式匹配与用户提示）
- **多客户端**：Mac/iOS 同时连接，按 session 同步；可选 Cloudflared 隧道 + Token 认证

---

## 系统要求

- **macOS 14.0+**
- **Python 3.10+**
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

## Xcode 运行后权限保留

从 Xcode 运行若每次都要重新在「系统设置 → 隐私与安全性」授权（辅助功能、自动化等），是因为默认构建到 DerivedData，路径会变，系统按路径记权限。

**建议**：固定构建路径，一次授权长期有效。

1. 用 Xcode 打开 **MacAgentApp.xcworkspace**（使用 CocoaPods 时务必用 workspace）
2. **File → Workspace Settings…**（或 Project Settings）
3. **Build Location** 选 **Custom**，再选 **Relative to Workspace** 或固定目录（如项目下 `Build`）
4. 重新编译运行，在系统设置中对该路径下的 **MacAgentApp** 授权一次

若出现 **「Framework 'Pods_MacAgentApp' not found」**，请确认已用 `.xcworkspace` 打开并执行过 `pod install`。

---

## 项目结构

```
MacAgent/
├── MacAgentApp/                   # macOS 客户端 (SwiftUI)
│   └── MacAgentApp/
│       ├── MacAgentApp.swift
│       ├── ContentView.swift
│       ├── ViewModels/AgentViewModel.swift
│       ├── Services/BackendService.swift, ProcessManager.swift, TunnelManager.swift
│       ├── Models/Message.swift
│       └── Views/                 # ChatView, SettingsView, ToolPanelView, TunnelView...
│
├── iOSAgentApp/                   # iOS 客户端（可选）
│
├── backend/                       # Python FastAPI 后端
│   ├── main.py                    # 入口、lifespan、路由与 WebSocket 注册
│   ├── app_state.py               # 全局状态、TaskTracker、Feature Flags
│   ├── auth.py                    # 隧道认证
│   ├── connection_manager.py      # WebSocket 连接与按 session 广播
│   ├── ws_handler.py              # /ws 消息分发（chat/stop/autonomous/resume/...）
│   ├── llm_config.py              # LLM 配置持久化 (data/llm_config.json)
│   ├── smtp_config.py, github_config.py
│   ├── data/                      # llm_config, smtp, github, contexts/
│   │
│   ├── routes/                    # HTTP 路由
│   │   ├── health.py              # /health, /server-status, /connections
│   │   ├── auth_routes.py         # /auth/status, generate-token, disable
│   │   ├── config.py              # /config, /config/smtp, /config/github
│   │   ├── tools.py               # /tools, /tools/pending, approve, reload
│   │   ├── upgrade.py             # /upgrade/self, trigger, restart
│   │   ├── logs.py                # /logs, /system-messages
│   │   ├── memory.py              # /memory/status, /local-llm/status, /model-selector/*
│   │   ├── self_healing.py        # /self-healing/*, /ws/self-healing
│   │   ├── evomap.py              # /evomap/*（ENABLE_EVOMAP=true 时）
│   │   ├── capsules.py            # /capsules, /capsules/find, execute
│   │   └── chat.py                # POST /chat 非流式
│   │
│   ├── agent/                     # Agent 核心与周边
│   │   ├── core.py                # AgentCore ReAct 循环
│   │   ├── autonomous_agent.py    # 自主任务、反思、模型选择
│   │   ├── llm_client.py          # 统一 LLM 客户端（DeepSeek/Ollama/LM Studio/New API）
│   │   ├── local_llm_manager.py    # 本地模型检测
│   │   ├── model_selector.py      # 任务→模型选择
│   │   ├── prompt_loader.py       # LITE/FULL system prompt、进化规则
│   │   ├── context_manager.py     # 对话上下文、向量检索
│   │   ├── vector_store.py        # BGE 嵌入与语义检索
│   │   ├── task_context_manager.py# 目标应用解析与绑定
│   │   ├── web_augmented_thinking.py  # 联网增强（天气/百科/事实核查等）
│   │   ├── local_tool_parser.py   # 本地模型 tool_calls 解析
│   │   ├── event_bus.py, error_service.py, self_healing_worker.py, upgrade_service.py
│   │   ├── system_message_service.py, log_analyzer.py
│   │   ├── self_upgrade/          # 工具自我升级（orchestrator, planner, executors, ...）
│   │   ├── self_healing/          # 自愈（diagnostic, repair_planner/validator/executor）
│   │   ├── capsule_*.py           # Capsule 加载、执行、校验、开放技能源
│   │   ├── evomap_*.py            # EvoMap 服务与升级钩子（可选）
│   │   ├── stop_policy.py         # 自主任务自适应停止
│   │   ├── resource_dispatcher.py # 升级任务沙箱执行
│   │   └── ...
│   │
│   ├── tools/                     # 工具实现
│   │   ├── base.py, registry.py, router.py, schema_registry.py, validator.py
│   │   ├── file_tool, terminal_tool, app_tool, system_tool, clipboard_tool
│   │   ├── script_tool, screenshot_tool, browser_tool, mail_tool, calendar_tool
│   │   ├── notification_tool, docker_tool, network_tool, database_tool
│   │   ├── developer_tool, web_search_tool, dynamic_tool_generator, vision_tool
│   │   ├── input_control_tool, request_tool_upgrade_tool, evomap_tool, capsule_tool
│   │   └── generated/             # 动态加载（Self-Upgrade 产出 + 手写）
│   │
│   ├── llm/                       # tool_parser_v2, json_repair
│   └── runtime/                   # RuntimeAdapter, mac_adapter, linux/windows_adapter
│
└── docs/
    ├── 后台功能清单-人工测试审核.md   # 功能清单与测试要点
    └── ...
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
| 配置 | GET/POST | /config, /config/smtp, /config/github | LLM / 邮件 / GitHub |
| 工具 | GET | /tools | 工具列表 |
| 工具 | GET/POST | /tools/pending, /tools/approve, /tools/reload | 待审批、审批、重载 |
| 对话 | POST | /chat | 非流式对话 |
| 对话 | WebSocket | /ws | 流式 chat、autonomous、resume、stop 等 |
| 升级 | POST | /upgrade/self, /upgrade/trigger, /upgrade/restart | 自升级、触发升级、重启 |
| 日志 | GET/DELETE | /logs | 日志 |
| 系统消息 | GET/POST/DELETE | /system-messages, .../read, .../read-all | 列表、已读、删除 |
| 记忆 | GET | /memory/status, /local-llm/status, /model-selector/status | 状态 |
| 自愈 | GET/POST | /self-healing/status, /diagnose, /plan | 状态、诊断、计划 |
| 自愈 | WebSocket | /ws/self-healing | 自愈对话与执行 |
| EvoMap | GET/POST | /evomap/status, register, search, resolve, publish, events, audit | 需 ENABLE_EVOMAP=true |
| Capsule | GET/POST | /capsules, /capsules/find, /capsules/{id}, /capsules/{id}/execute | 技能胶囊 |

完整列表与测试要点见 [docs/后台功能清单-人工测试审核.md](docs/后台功能清单-人工测试审核.md)。

---

## 环境变量（可选）

| 变量 | 默认 | 说明 |
|------|------|------|
| ENABLE_VECTOR_SEARCH | true | 是否启用 BGE 向量检索 |
| EMBEDDING_MODEL | BAAI/bge-small-zh-v1.5 | 嵌入模型 |
| ENABLE_EVOMAP | false | 是否启用 EvoMap |
| MACAGENT_AUTO_TOOL_UPGRADE | true | 是否自动触发工具升级 |
| AUTH_ENABLED, AUTH_TOKEN | - | 隧道/iOS 认证（见 auth.py） |
| HF_ENDPOINT | - | 国内可设 https://hf-mirror.com 加速 BGE 下载 |

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

## 安全说明

- 危险终端命令会被拒绝（如 `rm -rf /`）；Self-Upgrade 执行在沙箱内（`resource_dispatcher`：cwd 限制、命令黑名单、超时）
- API Key 与配置存于本地（`backend/data/`），不会上传
- 建议在沙盒或测试环境中验证新工具与升级流程

---

## 许可证

MIT License
