# MacAgent 工具自我升级任务

**请在本次对话中完成此任务，创建/修改文件后保存。**

**⚠️ 输出位置**：新工具必须创建在 MacAgent 项目 `tools/generated/` 目录（相对于当前 workspace），禁止创建在 ~/ 或用户主目录。

---


## ⚠️ 强制性要求（必须遵守，违反则升级失败）

1. **输出路径（硬性）**：
   - 必须在 MacAgent 项目内创建：`tools/generated/tunnel_monitor_mail_tool.py`（相对 workspace 根 backend/）
   - 绝对路径示例：`/Users/lzz/Desktop/未命名文件夹/MacAgent/backend/tools/generated/tunnel_monitor_mail_tool.py`
   - **严禁**创建在：~/、$HOME、/tmp、/Users/xxx/、桌面 等项目外路径
   - 只有 tools/generated/ 下的工具会被 Agent 动态加载
2. **类结构**：必须继承 `from tools.base import BaseTool, ToolResult, ToolCategory`
3. **必须实现**：`name`、`description`、`parameters`（JSON Schema）、`execute()` 异步方法

## 工具代码模板参考

```python
from tools.base import BaseTool, ToolResult, ToolCategory

class TunnelMonitorMailTool(BaseTool):
    name = "tunnel_monitor_mail"
    description = "监控隧道状态，在检测到中断时自动重启隧道服务，获取新的隧道链接并发送邮件通知到指定邮箱（默认675632487@qq.com），确保手机端能及时获取最新链接。"
    category = ToolCategory.SYSTEM
    parameters = {
    "type": "object",
    "properties": {
        "to_email": {
            "type": "string",
            "description": "收件人邮箱地址，默认为675632487@qq.com"
        },
        "monitor_interval": {
            "type": "integer",
            "description": "监控检查间隔（秒），默认60秒"
        },
        "only_send_mail": {
            "type": "boolean",
            "description": "是否仅发送邮件而不执行监控，默认false"
        }
    },
    "required": []
}

    async def execute(self, **kwargs) -> ToolResult:
        # 实现逻辑
        return ToolResult(success=True, data={...})
```

## 你的具体任务

在 backend/tools/generated/ 目录下创建 tunnel_monitor_mail_tool.py 文件，实现以下功能：

1. 工具类名：TunnelMonitorMailTool
2. 功能描述：监控隧道状态，中断时自动重启，获取新链接并发送邮件通知
3. 主要方法：
   - check_tunnel_status(): 检查当前隧道状态（可调用现有隧道工具或系统命令）
   - restart_tunnel(): 重启隧道服务并获取新链接
   - send_mail(to_email, tunnel_link): 发送邮件到指定邮箱，包含新隧道链接和说明
4. 参数配置：
   - 邮件服务器配置（SMTP）：支持QQ邮箱（smtp.qq.com:587）
   - 发件人邮箱和授权码（可从环境变量或配置文件中读取）
   - 收件人邮箱：675632487@qq.com（作为默认参数）
5. 邮件内容格式：
   - 主题：隧道链接更新通知
   - 正文：包含新隧道链接、更新时间、使用说明
6. 调用方式：
   - 可单独调用邮件发送功能
   - 可执行完整监控-重启-通知流程
7. 错误处理：
   - 邮件发送失败时记录日志并重试
   - 隧道状态检测异常处理

---

## 完成后
1. 保存所有文件
2. 新工具将自动加载，用户可立即在 Chat 中调用
