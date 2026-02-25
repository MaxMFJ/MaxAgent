# MacAgent 工具自我升级任务

**请在本次对话中完成此任务，创建/修改文件后保存。**

**⚠️ 输出位置**：新工具必须创建在 MacAgent 项目 `tools/generated/` 目录（相对于当前 workspace），禁止创建在 ~/ 或用户主目录。

---


## ⚠️ 强制性要求（必须遵守，违反则升级失败）

1. **输出路径（硬性）**：
   - 必须在 MacAgent 项目内创建：`tools/generated/interactive_mail_tool.py`（相对 workspace 根 backend/）
   - 绝对路径示例：`/Users/lzz/Desktop/未命名文件夹/MacAgent/backend/tools/generated/interactive_mail_tool.py`
   - **严禁**创建在：~/、$HOME、/tmp、/Users/xxx/、桌面 等项目外路径
   - 只有 tools/generated/ 下的工具会被 Agent 动态加载
2. **类结构**：必须继承 `from tools.base import BaseTool, ToolResult, ToolCategory`
3. **必须实现**：`name`、`description`、`parameters`（JSON Schema）、`execute()` 异步方法

## 工具代码模板参考

```python
from tools.base import BaseTool, ToolResult, ToolCategory

class InteractiveMailTool(BaseTool):
    name = "interactive_mail"
    description = "通过Chat交互获取SMTP配置信息后发送邮件。当缺少SMTP服务器、邮箱、授权码等信息时，会提示用户通过Chat提供，然后自动配置并发送邮件。"
    category = ToolCategory.CUSTOM
    parameters = {
    "type": "object",
    "properties": {
        "to_email": {
            "type": "string",
            "description": "收件人邮箱地址"
        },
        "subject": {
            "type": "string",
            "description": "邮件主题"
        },
        "body": {
            "type": "string",
            "description": "邮件正文内容"
        },
        "smtp_server": {
            "type": "string",
            "description": "SMTP服务器地址（如smtp.qq.com），可选，缺失时会提示用户提供"
        },
        "smtp_port": {
            "type": "integer",
            "description": "SMTP端口号（如465或587），可选，缺失时会提示用户提供"
        },
        "sender_email": {
            "type": "string",
            "description": "发件人邮箱地址，可选，缺失时会提示用户提供"
        },
        "sender_password": {
            "type": "string",
            "description": "发件人邮箱授权码/密码，可选，缺失时会提示用户提供"
        }
    },
    "required": [
        "to_email",
        "subject",
        "body"
    ]
}

    async def execute(self, **kwargs) -> ToolResult:
        # 实现逻辑
        return ToolResult(success=True, data={...})
```

## 你的具体任务

在 backend/tools/generated/ 目录下创建 interactive_mail_tool.py，实现以下功能：
1. 工具类 InteractiveMailTool，继承 BaseTool
2. 主要方法 send_mail_with_config：
   - 参数：to_email（收件人），subject（主题），body（正文），smtp_server（可选），smtp_port（可选），sender_email（可选），sender_password（可选）
   - 逻辑：如果缺少SMTP配置参数，抛出 ToolException 提示用户通过Chat提供缺失信息
   - 支持SSL/TLS加密连接
   - 使用email.mime.text构建邮件内容
   - 成功发送后返回确认信息
3. 辅助方法 save_smtp_config（可选）：将用户提供的配置保存到本地文件供后续使用
4. 错误处理：网络错误、认证失败、参数缺失等
5. 工具描述明确说明需要用户通过Chat交互提供SMTP配置信息

---

## 完成后
1. 保存所有文件
2. 新工具将自动加载，用户可立即在 Chat 中调用
