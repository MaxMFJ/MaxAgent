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
    description = "监控隧道连接状态，检测中断后自动重启并发送新的隧道链接到指定邮箱"
    category = ToolCategory.SYSTEM
    parameters = {
    "type": "object",
    "properties": {
        "email_recipient": {
            "type": "string",
            "description": "收件人邮箱地址"
        },
        "check_interval": {
            "type": "integer",
            "description": "检查间隔时间（秒）"
        },
        "max_retries": {
            "type": "integer",
            "description": "最大重试次数"
        }
    },
    "required": []
}

    async def execute(self, **kwargs) -> ToolResult:
        # 实现逻辑
        return ToolResult(success=True, data={...})
```

## 你的具体任务

在 backend/tools/generated/ 目录下创建 tunnel_monitor_tool.py 文件。

实现逻辑：
1. 工具类名为 TunnelMonitorTool，继承自 BaseTool
2. 主要功能：
   - 监控隧道连接状态（通过检查特定进程或端口）
   - 检测到中断后自动重启隧道（调用系统命令重启隧道服务）
   - 获取新的隧道链接（从配置文件或命令输出中提取）
   - 发送邮件通知到指定邮箱（675632487@qq.com），包含新的隧道链接
3. 参数设计：
   - email_recipient: 收件人邮箱，默认 '675632487@qq.com'
   - check_interval: 检查间隔（秒），默认 30
   - max_retries: 最大重试次数，默认 3
4. 邮件发送功能：
   - 使用 smtplib 和 email 标准库
   - 支持 SSL/TLS 加密连接
   - 邮件主题：'隧道链接更新通知'
   - 邮件内容包含：新的隧道链接、更新时间、状态信息
5. 错误处理：
   - 网络异常重试机制
   - 邮件发送失败记录日志
   - 隧道重启失败告警
6. 调用方式：Agent 可调用该工具进行隧道监控，工具会持续运行直到检测到中断并完成重启和通知

---

## 完成后
1. 保存所有文件
2. 新工具将自动加载，用户可立即在 Chat 中调用
