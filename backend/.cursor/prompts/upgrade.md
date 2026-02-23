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
    description = "监控隧道连接状态，中断后自动重启并发送新链接到指定邮箱"
    category = ToolCategory.SYSTEM
    parameters = {
    "type": "object",
    "properties": {
        "tunnel_type": {
            "type": "string",
            "description": "隧道类型：ngrok, frp, 或 custom",
            "enum": [
                "ngrok",
                "frp",
                "custom"
            ]
        },
        "process_name": {
            "type": "string",
            "description": "隧道进程名称"
        },
        "check_port": {
            "type": "integer",
            "description": "监控的端口号（可选）"
        },
        "check_interval": {
            "type": "integer",
            "description": "监控间隔秒数，默认60",
            "default": 60
        },
        "max_retries": {
            "type": "integer",
            "description": "最大重试次数，默认3",
            "default": 3
        },
        "email": {
            "type": "string",
            "description": "接收新链接的邮箱地址",
            "default": "675632487@qq.com"
        },
        "tunnel_command": {
            "type": "string",
            "description": "重启隧道的命令（custom类型时必须）"
        }
    },
    "required": [
        "tunnel_type",
        "process_name"
    ]
}

    async def execute(self, **kwargs) -> ToolResult:
        # 实现逻辑
        return ToolResult(success=True, data={...})
```

## 你的具体任务

在MacAgent项目的backend/tools/generated/目录下创建tunnel_monitor_tool.py文件。

实现要求：
1. 工具类名：TunnelMonitorTool
2. 主要功能：
   - 监控指定隧道进程（通过进程名或端口检测）
   - 检测到中断后自动重启隧道服务
   - 获取新的隧道链接（可通过解析日志或API获取）
   - 将新链接通过SMTP发送到指定邮箱（675632487@qq.com）
   - 支持配置监控间隔和重试次数

3. 参数设计：
   - tunnel_type: 隧道类型（ngrok/frp/custom）
   - process_name: 进程名（如'ngrok'）
   - check_port: 监控端口（可选）
   - check_interval: 监控间隔秒数（默认60）
   - max_retries: 最大重试次数（默认3）
   - email: 接收邮箱（默认675632487@qq.com）
   - tunnel_command: 启动命令（用于重启）

4. 实现逻辑：
   - 使用psutil检查进程状态
   - 使用schedule或threading实现定时监控
   - 邮件发送使用smtplib，配置发件邮箱（需用户自行配置SMTP信息）
   - 提供start_monitoring()方法启动监控
   - 提供stop_monitoring()方法停止监控

5. 调用方式：
   - LLM可调用tunnel_monitor方法启动监控
   - 返回监控状态信息

---

## 完成后
1. 保存所有文件
2. 新工具将自动加载，用户可立即在 Chat 中调用
