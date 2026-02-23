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
    description = "监控隧道连接状态，检测到中断时自动重启隧道，并将新的连接信息发送到指定邮箱。支持进程名或端口号检测，可配置检测间隔和重启命令。"
    category = ToolCategory.SYSTEM
    parameters = {
    "type": "object",
    "properties": {
        "process_name": {
            "type": "string",
            "description": "隧道进程名称（如 'frpc', 'ngrok'）"
        },
        "port": {
            "type": "integer",
            "description": "隧道监听的端口号"
        },
        "check_interval": {
            "type": "integer",
            "description": "检测间隔秒数，默认60秒"
        },
        "restart_command": {
            "type": "string",
            "description": "重启隧道的shell命令"
        },
        "email": {
            "type": "string",
            "description": "接收通知的邮箱地址，默认675632487@qq.com"
        },
        "max_retries": {
            "type": "integer",
            "description": "最大重试次数，默认3次"
        }
    },
    "required": [
        "restart_command"
    ]
}

    async def execute(self, **kwargs) -> ToolResult:
        # 实现逻辑
        return ToolResult(success=True, data={...})
```

## 你的具体任务

创建隧道监控工具 tunnel_monitor_tool.py，实现以下功能：

1. **核心功能**：
   - 监控指定隧道进程（通过进程名或端口号检测）
   - 检测连接中断（通过心跳检测或进程状态）
   - 自动重启隧道（执行重启命令）
   - 将新的连接信息发送到指定邮箱（675632487@qq.com）

2. **实现逻辑**：
   - 使用 psutil 库检测进程状态
   - 实现网络连接检测（可配置检测间隔）
   - 支持自定义重启命令
   - 使用 requests 发送邮件通知（通过邮件服务API或SMTP）
   - 提供配置参数：进程名/端口、检测间隔、重启命令、邮箱地址

3. **参数设计**：
   - process_name: 隧道进程名（可选）
   - port: 隧道端口（可选）
   - check_interval: 检测间隔秒数（默认60）
   - restart_command: 重启命令
   - email: 通知邮箱（默认675632487@qq.com）
   - max_retries: 最大重试次数（默认3）

4. **调用方式**：
   - 作为独立工具运行：python tunnel_monitor_tool.py --start
   - 被Agent调用：tunnel_monitor.start_monitoring()
   - 支持后台守护进程模式

5. **文件位置**：必须保存在 MacAgent 项目的 backend/tools/generated/ 目录下

---

## 完成后
1. 保存所有文件
2. 新工具将自动加载，用户可立即在 Chat 中调用
