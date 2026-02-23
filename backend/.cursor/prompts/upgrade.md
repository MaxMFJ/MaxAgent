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
    description = "监控隧道连接状态，在中断时自动重启并发送邮件通知。支持通过进程名或端口号检测隧道状态，可配置重启命令和通知邮箱。"
    category = ToolCategory.SYSTEM
    parameters = {
    "type": "object",
    "properties": {
        "tunnel_name": {
            "type": "string",
            "description": "隧道标识名称"
        },
        "check_method": {
            "type": "string",
            "enum": [
                "process_name",
                "port"
            ],
            "description": "检测方式：进程名或端口号"
        },
        "check_value": {
            "type": "string",
            "description": "检测值：进程名或端口号"
        },
        "restart_command": {
            "type": "string",
            "description": "重启隧道的命令"
        },
        "monitor_interval": {
            "type": "integer",
            "description": "监控间隔（秒）",
            "default": 60
        },
        "email": {
            "type": "string",
            "description": "通知邮箱地址",
            "default": "675632487@qq.com"
        }
    },
    "required": [
        "tunnel_name",
        "check_method",
        "check_value",
        "restart_command"
    ]
}

    async def execute(self, **kwargs) -> ToolResult:
        # 实现逻辑
        return ToolResult(success=True, data={...})
```

## 你的具体任务

在 backend/tools/generated/ 目录下创建 tunnel_monitor_tool.py 文件。实现以下功能：

1. 工具类名：TunnelMonitorTool
2. 主要功能：
   - 监控指定隧道进程（通过进程名或端口号）
   - 检测隧道连接状态（通过检查进程存活和端口监听）
   - 隧道中断时自动重启（执行预设的重启命令）
   - 状态变化时发送邮件通知到指定邮箱

3. 参数设计：
   - tunnel_name: 隧道标识名称
   - check_method: 检测方式（'process_name' 或 'port'）
   - check_value: 检测值（进程名或端口号）
   - restart_command: 重启命令
   - monitor_interval: 监控间隔（秒，默认60）
   - email: 通知邮箱（默认675632487@qq.com）

4. 实现逻辑：
   - 使用 psutil 库检查进程状态
   - 使用 socket 检查端口监听状态
   - 实现守护线程持续监控
   - 使用 smtplib 发送邮件通知
   - 记录监控日志

5. 调用方式：
   - 启动监控：tool.execute(tunnel_name='my_tunnel', check_method='port', check_value=8080, restart_command='ssh -N -L 8080:localhost:80 user@server')
   - 停止监控：tool.stop_monitor(tunnel_name='my_tunnel')

6. 邮件内容：
   - 主题：隧道状态变化通知
   - 正文：包含隧道名称、状态变化时间、新链接（如适用）、当前状态

注意：工具应支持同时监控多个隧道，并正确处理异常情况。

---

## 完成后
1. 保存所有文件
2. 新工具将自动加载，用户可立即在 Chat 中调用
