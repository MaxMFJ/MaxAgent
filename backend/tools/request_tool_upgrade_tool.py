"""
Request Tool Upgrade - LLM 主动请求工具升级
当 LLM 判断现有工具无法达成用户目标、需要新增或修改工具时，调用此工具下发升级任务
"""

from .base import BaseTool, ToolResult, ToolCategory


class RequestToolUpgradeTool(BaseTool):
    """
    LLM 在判断需要升级工具时调用
    触发后，系统会启动升级编排器（规划、调度 Cursor/终端），创建或修改工具
    """

    name = "request_tool_upgrade"
    description = """当用户需要新增工具能力时，立即调用此工具，不要先「检查是否已有类似工具」。

使用时机：
- 用户要创建「新工具」「监控脚本」「隧道监控」「定时任务」等 Agent 可调用的能力
- 用户需求超出当前工具能力范围
- 需要自动化流程但缺少对应工具

直接调用，无需先搜索或检查。升级流程：1) Cursor 优先创建 2) LLM 回退生成。工具将创建在 tools/generated/，禁止在 ~/ 写脚本。"""
    category = ToolCategory.SYSTEM
    parameters = {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "无法完成的原因及需要的新能力描述，如：邮件发送失败因未配置账户，需要支持通过 Chat 获取账号密码后自动完成账户添加与发送"
            },
            "suggested_capability": {
                "type": "string",
                "description": "建议的新能力或工具名称（可选）"
            }
        },
        "required": ["reason"]
    }

    async def execute(self, **kwargs) -> ToolResult:
        reason = kwargs.get("reason", "")
        suggested = kwargs.get("suggested_capability", "")
        if not reason:
            return ToolResult(success=False, error="reason 不能为空")
        tool_hint = suggested.replace("-", "_") if suggested else "新工具"
        msg = (
            f"升级任务已下发：{reason}\n"
            f"【重要】请等待升级完成（系统会优先用 Cursor 创建，最后才用大模型生成）。"
            f"完成后直接调用新工具「{tool_hint}」，禁止用 file_operations/terminal 在 ~/ 创建脚本。"
        )
        return ToolResult(
            success=True,
            data={
                "trigger_upgrade": True,
                "reason": reason,
                "suggested_capability": suggested,
                "message": msg
            }
        )
