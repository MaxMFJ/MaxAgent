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
    description = "监控隧道连接状态，在中断时自动重启并发送新链接到指定邮箱"
    category = ToolCategory.SYSTEM
    parameters = {
    "type": "object",
    "properties": {
        "tunnel_command": {
            "type": "string",
            "description": "启动隧道的完整命令"
        },
        "check_interval": {
            "type": "integer",
            "description": "检查间隔（秒）",
            "default": 60
        },
        "recipient_email": {
            "type": "string",
            "description": "收件人邮箱地址",
            "default": "675632487@qq.com"
        },
        "process_name": {
            "type": "string",
            "description": "隧道进程名关键词"
        }
    },
    "required": [
        "tunnel_command",
        "process_name"
    ]
}

    async def execute(self, **kwargs) -> ToolResult:
        # 实现逻辑
        return ToolResult(success=True, data={...})
```

## 你的具体任务

在MacAgent项目的backend/tools/generated/目录下创建tunnel_monitor_tool.py文件。

实现逻辑：
1. 工具需要监控指定的隧道进程（如SSH隧道、frp等）
2. 定期检查隧道进程是否运行，如果中断则自动重启
3. 重启成功后获取新的隧道链接
4. 通过邮件将新链接发送到指定邮箱

参数设计：
- tunnel_command: 启动隧道的命令（如'ssh -L 8080:localhost:8080 user@server'）
- check_interval: 检查间隔（秒，默认60）
- recipient_email: 收件人邮箱（默认675632487@qq.com）
- process_name: 进程名关键词（用于识别隧道进程）

调用方式：
1. 初始化监控：tunnel_monitor.start_monitoring()
2. 停止监控：tunnel_monitor.stop_monitoring()
3. 检查状态：tunnel_monitor.check_status()

实现要点：
- 使用psutil库监控进程
- 使用subprocess启动隧道进程
- 使用smtplib发送邮件（Mac系统自带邮件功能）
- 实现后台线程持续监控
- 记录日志便于调试

---

## 完成后
1. 保存所有文件
2. 新工具将自动加载，用户可立即在 Chat 中调用
