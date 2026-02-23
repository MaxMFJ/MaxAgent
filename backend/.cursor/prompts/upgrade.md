# MacAgent 工具自我升级任务

**请在本次对话中完成此任务，创建/修改文件后保存。**

**⚠️ 输出位置**：新工具必须创建在 MacAgent 项目 `tools/generated/` 目录（相对于当前 workspace），禁止创建在 ~/ 或用户主目录。

---


## ⚠️ 强制性要求（必须遵守，违反则升级失败）

1. **输出路径（硬性）**：
   - 必须在 MacAgent 项目内创建：`tools/generated/tunnel_monitor_tool.py`（相对 workspace 根 backend/）
   - 绝对路径示例：`/Users/lzz/Desktop/未命名文件夹/MacAgent/backend/tools/generated/tunnel_monitor_tool.py`
   - **严禁**创建在：~/、$HOME、/tmp、/Users/xxx/、桌面 等项目外路径
   - 只有 tools/generated/ 下的工具会被 Agent 动态加载
2. **类结构**：必须继承 `from tools.base import BaseTool, ToolResult, ToolCategory`
3. **必须实现**：`name`、`description`、`parameters`（JSON Schema）、`execute()` 异步方法

## 工具代码模板参考

```python
from tools.base import BaseTool, ToolResult, ToolCategory

class TunnelMonitorTool(BaseTool):
    name = "tunnel_monitor"
    description = "隧道监控工具，用于启动、停止、检查隧道监控状态，支持SSH、VPN、WireGuard等多种隧道类型。可以设置检查间隔、重试次数等参数，并提供实时状态查询和日志查看功能。"
    category = ToolCategory.SYSTEM
    parameters = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": "操作类型：start(启动监控)、stop(停止监控)、status(检查状态)、logs(查看日志)",
            "enum": [
                "start",
                "stop",
                "status",
                "logs"
            ]
        },
        "tunnel_type": {
            "type": "string",
            "description": "隧道类型：ssh(SSH隧道)、vpn(VPN连接)、wireguard(WireGuard隧道)、custom(自定义隧道)",
            "enum": [
                "ssh",
                "vpn",
                "wireguard",
                "custom"
            ],
            "default": "ssh"
        },
        "check_interval": {
            "type": "integer",
            "description": "检查间隔时间（秒）",
            "minimum": 5,
            "maximum": 3600,
            "default": 30
        },
        "max_retries": {
            "type": "integer",
            "description": "最大重试次数",
            "minimum": 1,
            "maximum": 10,
            "default": 3
        },
        "log_file": {
            "type": "string",
            "description": "日志文件路径",
            "default": "/tmp/tunnel_monitor.log"
        }
    },
    "required": [
        "action"
    ]
}

    async def execute(self, **kwargs) -> ToolResult:
        # 实现逻辑
        return ToolResult(success=True, data={...})
```

## 你的具体任务

在 ~/Desktop/MacAgent/backend/tools/generated/ 目录下创建 tunnel_monitor_tool.py 文件，实现完整的隧道监控工具包装器。

实现要求：
1. 继承 BaseTool 类，实现完整的工具框架
2. 提供以下核心功能：
   - 启动隧道监控
   - 停止隧道监控
   - 检查隧道状态
   - 查看监控日志
3. 支持多种隧道类型：ssh, vpn, wireguard, custom
4. 实现参数验证和错误处理
5. 提供清晰的用户反馈

具体实现逻辑：
1. 工具类名：TunnelMonitorTool
2. 使用 subprocess 模块管理监控脚本进程
3. 监控脚本路径：同目录下的 tunnel_monitor_v3.sh
4. 实现进程管理，确保只有一个监控实例运行
5. 提供状态查询和日志查看功能

参数设计：
- action: 操作类型 (start|stop|status|logs)
- tunnel_type: 隧道类型 (ssh|vpn|wireguard|custom)
- check_interval: 检查间隔(秒)
- max_retries: 最大重试次数
- log_file: 日志文件路径

调用方式示例：
- 启动监控：tunnel_monitor(action='start', tunnel_type='ssh', check_interval=30)
- 检查状态：tunnel_monitor(action='status')
- 查看日志：tunnel_monitor(action='logs')
- 停止监控：tunnel_monitor(action='stop')

确保工具能够被Agent正确调用，并提供详细的执行结果反馈。

---

## 完成后
1. 保存所有文件
2. 新工具将自动加载，用户可立即在 Chat 中调用
