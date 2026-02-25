# MacAgent - macOS AI 智能助手

一个强大的 macOS 本地 AI Agent 助手，使用 SwiftUI 构建原生界面，通过 Python 后端与 DeepSeek/Ollama 模型交互。支持文件操作、终端命令、应用控制、浏览器自动化、邮件日历、截图 OCR、联网搜索等系统功能，具备自我修复与工具自我升级能力。

## 功能特性

### 基础能力
- **文件操作**: 读取、创建、删除、移动、复制文件和目录
- **终端命令**: 执行 shell 命令和脚本
- **应用控制**: 打开、关闭、切换 macOS 应用程序
- **系统信息**: 查看 CPU、内存、磁盘、网络状态
- **剪贴板**: 读取和写入剪贴板内容

### 扩展能力
- **截图与 OCR**: 全屏/窗口/区域截图，文字识别
- **浏览器**: Safari/Chrome 自动化，网页内容抓取
- **邮件与日历**: 发送/读取邮件，管理日历事件
- **Docker/网络/数据库**: 容器管理、网络检测、SQL 查询
- **开发工具**: 创建 Web/iOS 应用、API 服务、React/Vue 项目
- **联网搜索**: DuckDuckGo 搜索、维基百科、天气、翻译
- **技能 Capsule**: 本地技能库（`backend/capsules/`），可执行多步骤、条件、重试、并行等；无需 EvoMap 官方库，可选从任意符合格式的 GitHub 仓库同步。详见 [docs/CAPSULE_SOURCES.md](docs/CAPSULE_SOURCES.md)

### 架构特性
- **Runtime 抽象层**: 平台无关，支持 Mac/Linux/Windows 移植
- **EventBus 解耦**: 自愈、升级、错误收集通过事件总线解耦
- **工具自我升级**: Planner → Strategy → Executor → Validation → Activation
- **多客户端**: Mac/iOS 端同时连接，会话级同步

## 系统要求

- macOS 14.0+
- Python 3.10+
- Xcode 15.0+ (用于编译 SwiftUI 应用)

## 快速开始

### 1. 安装 Python 依赖

```bash
cd MacAgent/backend
pip install -r requirements.txt
```

### 2. 配置 API Key

**方式一: 环境变量**
```bash
export DEEPSEEK_API_KEY="your-api-key-here"
```

**方式二: 在应用设置中配置**
启动应用后，在设置界面中输入 API Key。

### 3. 启动后端服务

```bash
cd MacAgent/backend
python main.py
```

后端服务将在 `http://127.0.0.1:8765` 启动。

### 4. 启动 macOS 应用

**方式一: 使用 Xcode**
```bash
# 若已执行 pod install，请打开 .xcworkspace
open MacAgent/MacAgentApp/MacAgentApp.xcworkspace
# 或
open MacAgent/MacAgentApp/MacAgentApp.xcodeproj
```
在 Xcode 中点击运行按钮。

**方式二: 命令行编译**
```bash
cd MacAgent/MacAgentApp
xcodebuild -project MacAgentApp.xcodeproj -scheme MacAgentApp -configuration Debug build
```

## 使用 Ollama 本地模型

如果你想使用本地模型而不是 DeepSeek API:

1. 安装 Ollama: https://ollama.ai/
2. 下载模型:
   ```bash
   ollama pull deepseek-r1:8b
   ```
3. 在应用设置中选择 "Ollama (本地)" 并配置模型名称

## CocoaPods (可选)

iOS 和 Mac 客户端均已配置 CocoaPods，便于添加第三方依赖:

```bash
# iOS 客户端
cd MacAgent/iOSAgentApp && pod install

# Mac 客户端
cd MacAgent/MacAgentApp && pod install
```

安装后请使用 `.xcworkspace` 打开项目。在 Podfile 中可添加如 Masonry、AFNetworking、Alamofire 等依赖。

## 项目结构

```
MacAgent/
├── iOSAgentApp/                   # iOS 客户端 (Objective-C)
│   ├── iOSAgentApp/
│   ├── Podfile
│   └── iOSAgentApp.xcworkspace
│
├── MacAgentApp/                   # Xcode 项目 (SwiftUI)
│   ├── MacAgentApp/
│   │   ├── MacAgentApp.swift      # App 入口
│   │   ├── ContentView.swift      # 主视图
│   │   ├── Views/                 # 视图组件
│   │   ├── ViewModels/            # 视图模型 (AgentViewModel)
│   │   ├── Services/              # BackendService, ProcessManager
│   │   └── Models/                # 数据模型
│   └── MacAgentApp.xcodeproj
│
├── backend/                       # Python 后端
│   ├── main.py                    # FastAPI + WebSocket 入口
│   ├── requirements.txt
│   │
│   ├── agent/                     # Agent 层
│   │   ├── core.py                # AgentCore 最小调度核心 (ReAct)
│   │   ├── runtime_v2.py          # AgentRuntimeV2 本地模型专用
│   │   ├── llm_client.py          # LLM 客户端
│   │   ├── autonomous_agent.py    # 自主执行模式
│   │   ├── event_bus.py           # EventBus 发布订阅
│   │   ├── event_schema.py        # Event 事件模型
│   │   ├── error_service.py       # 错误收集服务
│   │   ├── self_healing_worker.py # 自愈 Worker
│   │   ├── upgrade_service.py     # 升级触发服务
│   │   ├── self_upgrade/          # Self-Upgrade 框架
│   │   │   ├── orchestrator.py    # Planner→Strategy→Executor→Activation
│   │   │   ├── planner.py
│   │   │   └── executors.py
│   │   ├── context_manager.py     # 对话上下文
│   │   ├── task_context_manager.py
│   │   └── ...
│   │
│   ├── runtime/                   # Runtime 抽象层
│   │   ├── base.py                # RuntimeAdapter 基类
│   │   ├── registry.py            # get_runtime_adapter()
│   │   ├── mac_adapter.py         # macOS 实现
│   │   ├── linux_adapter.py
│   │   └── windows_adapter.py
│   │
│   ├── tools/                     # 工具层
│   │   ├── base.py                # BaseTool
│   │   ├── registry.py            # ToolRegistry
│   │   ├── router.py              # 统一执行入口 validate→execute
│   │   ├── validator.py           # 参数校验
│   │   ├── schema_registry.py     # 工具 schema
│   │   ├── generated/             # 动态生成的工具 (Self-Upgrade)
│   │   ├── file_tool.py
│   │   ├── terminal_tool.py
│   │   └── ...
│   │
│   └── llm/                       # LLM 层
│       ├── tool_parser_v2.py      # parse_tool_call 结构化解析
│       └── json_repair.py
│
└── README.md
```

## 扩展工具

添加新工具只需三步:

1. 创建工具类 (继承 `BaseTool`):

```python
# tools/my_tool.py
from .base import BaseTool, ToolResult, ToolCategory

class MyTool(BaseTool):
    name = "my_tool"
    description = "我的自定义工具"
    parameters = {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "参数1"}
        },
        "required": ["param1"]
    }
    category = ToolCategory.CUSTOM
    
    async def execute(self, **kwargs) -> ToolResult:
        param1 = kwargs.get("param1")
        # 实现你的逻辑
        return ToolResult(success=True, data={"result": "done"})
```

2. 在 `tools/__init__.py` 中注册:

```python
from .my_tool import MyTool

def get_all_tools():
    return [
        # ... 其他工具
        MyTool(),
    ]
```

3. 重启后端服务

## 架构概览

- **Agent 层**: `AgentCore` (ReAct 循环) + `AgentRuntimeV2` (本地模型 parse→validate→execute)
- **EventBus 解耦**: `ErrorService` / `SelfHealingWorker` / `UpgradeService` 通过事件总线解耦，不侵入主循环
- **Runtime 抽象层**: `RuntimeAdapter` 定义平台能力 (APP_CONTROL, CLIPBOARD, SCREENSHOT 等)，`MacRuntimeAdapter` 实现 macOS 调用
- **Tools 层**: `router.execute` → `validator.validate` → 执行，支持 `tools/generated/` 动态加载
- **Self-Upgrade**: 工具缺失时自动触发 Planner→Strategy→Executor→Validation→Activation 流程

## API 接口

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 (含 server_status) |
| `/config` | GET/POST | 获取/更新 LLM 配置 |
| `/config/smtp` | GET/POST | SMTP 配置 |
| `/tools` | GET | 列出可用工具 |
| `/tools/reload` | POST | 动态加载 generated 工具 |
| `/tools/approve` | POST | 人工审批新工具 |
| `/chat` | POST | 发送消息 (非流式) |
| `/ws` | WebSocket | 流式对话 (多客户端 ConnectionManager) |
| `/upgrade/trigger` | POST | 手动触发工具升级 |
| `/upgrade/restart` | POST | 触发重启流程 |
| `/connections` | GET | 连接统计 |

## 安全说明

- 危险的终端命令会被自动拒绝 (如 `rm -rf /`)
- 建议在沙盒环境中测试新功能
- API Key 存储在本地，不会上传到云端

## 许可证

MIT License
