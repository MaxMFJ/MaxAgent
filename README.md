# MacAgent - macOS AI 智能助手

一个强大的 macOS 本地 AI Agent 助手，使用 SwiftUI 构建原生界面，通过 Python 后端与 DeepSeek/Ollama 模型交互，支持文件操作、终端命令、应用控制等系统功能。

## 功能特性

- **文件操作**: 读取、创建、删除、移动、复制文件和目录
- **终端命令**: 执行 shell 命令和脚本
- **应用控制**: 打开、关闭、切换 macOS 应用程序
- **系统信息**: 查看 CPU、内存、磁盘、网络状态
- **剪贴板**: 读取和写入剪贴板内容
- **可扩展**: 插件式架构，轻松添加新工具

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
├── iOSAgentApp/                 # iOS 客户端 (Objective-C)
│   ├── iOSAgentApp/
│   ├── Podfile
│   └── iOSAgentApp.xcworkspace
│
├── MacAgentApp/                 # Xcode 项目 (SwiftUI)
│   ├── MacAgentApp/
│   │   ├── MacAgentApp.swift    # App 入口
│   │   ├── ContentView.swift    # 主视图
│   │   ├── Views/               # 视图组件
│   │   ├── ViewModels/          # 视图模型
│   │   ├── Services/            # 服务层
│   │   └── Models/              # 数据模型
│   └── MacAgentApp.xcodeproj
│
├── backend/                      # Python 后端
│   ├── main.py                   # FastAPI 入口
│   ├── requirements.txt
│   ├── agent/
│   │   ├── core.py              # Agent 核心逻辑
│   │   └── llm_client.py        # LLM 客户端
│   └── tools/
│       ├── base.py              # 工具基类
│       ├── registry.py          # 工具注册中心
│       ├── file_tool.py         # 文件操作
│       ├── terminal_tool.py     # 终端命令
│       ├── app_tool.py          # 应用控制
│       ├── system_tool.py       # 系统信息
│       └── clipboard_tool.py    # 剪贴板
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

## API 接口

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/config` | GET/POST | 获取/更新配置 |
| `/tools` | GET | 列出可用工具 |
| `/chat` | POST | 发送消息 (非流式) |
| `/ws` | WebSocket | 流式对话 |

## 安全说明

- 危险的终端命令会被自动拒绝 (如 `rm -rf /`)
- 建议在沙盒环境中测试新功能
- API Key 存储在本地，不会上传到云端

## 许可证

MIT License
