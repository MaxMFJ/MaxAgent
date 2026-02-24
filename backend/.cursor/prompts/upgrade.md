# MacAgent 工具自我升级任务

**请在本次对话中完成此任务，创建/修改文件后保存。**

**⚠️ 输出位置**：新工具必须创建在 MacAgent 项目 `tools/generated/` 目录（相对于当前 workspace），禁止创建在 ~/ 或用户主目录。

---


## ⚠️ 强制性要求（必须遵守，违反则升级失败）

1. **输出路径（硬性）**：
   - 必须在 MacAgent 项目内创建：`tools/generated/chat_session_recovery_tool.py`（相对 workspace 根 backend/）
   - 绝对路径示例：`/Users/lzz/Desktop/未命名文件夹/MacAgent/backend/tools/generated/chat_session_recovery_tool.py`
   - **严禁**创建在：~/、$HOME、/tmp、/Users/xxx/、桌面 等项目外路径
   - 只有 tools/generated/ 下的工具会被 Agent 动态加载
2. **类结构**：必须继承 `from tools.base import BaseTool, ToolResult, ToolCategory`
3. **必须实现**：`name`、`description`、`parameters`（JSON Schema）、`execute()` 异步方法

## 工具代码模板参考

```python
from tools.base import BaseTool, ToolResult, ToolCategory

class ChatSessionRecoveryTool(BaseTool):
    name = "chat_session_recovery"
    description = "检查当前聊天会话状态，检测中断的会话并提供恢复方案。当手机端中断链接再恢复后，之前的聊天会话中断时，可以使用此工具诊断和恢复。"
    category = ToolCategory.SYSTEM
    parameters = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": "操作类型：check_status（检查状态）、list_interrupted（列出中断会话）、recover_last（恢复最近中断的会话）",
            "enum": [
                "check_status",
                "list_interrupted",
                "recover_last"
            ]
        },
        "session_id": {
            "type": "string",
            "description": "指定要恢复的会话ID（当action为recover_last时可选）"
        }
    },
    "required": []
}

    async def execute(self, **kwargs) -> ToolResult:
        # 实现逻辑
        return ToolResult(success=True, data={...})
```

## 你的具体任务

请创建一个名为 chat_session_recovery_tool.py 的工具文件，放置在 backend/tools/generated/ 目录下。

实现逻辑：
1. 工具需要检查当前聊天会话的状态，特别是当手机端中断链接再恢复后，之前的聊天会话是否中断
2. 工具应该能够检测到中断的会话并提供恢复方案
3. 实现以下核心功能：
   - 检查当前活跃的聊天会话状态
   - 识别最近中断的会话
   - 提供恢复中断会话的方法
   - 返回会话状态信息和恢复建议

参数设计：
- action (string, 可选): 指定操作类型，如 'check_status', 'list_interrupted', 'recover_last'
- session_id (string, 可选): 指定要恢复的会话ID

调用方式：
- 当用户报告聊天中断问题时，Agent可以调用此工具检查状态
- 工具返回当前会话状态、中断会话列表和恢复建议

实现要点：
1. 需要与现有的聊天系统集成
2. 提供清晰的返回信息，包括状态码、消息和建议
3. 考虑异常处理和边缘情况
4. 工具应该返回JSON格式的结果，便于Agent解析

---

## 完成后
1. 保存所有文件
2. 新工具将自动加载，用户可立即在 Chat 中调用
