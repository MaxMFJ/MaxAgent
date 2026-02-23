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
    description = """当现有工具无法达成用户目标、需要新增或修改工具能力时调用此工具。

使用时机：
- 用户需求超出当前工具能力范围
- 工具执行失败且判断需要新工具或修改现有工具才能完成
- 需要自动化流程但缺少对应工具（如某类账户配置、特定应用的操作流程）

调用后系统会下发升级任务，创建/修改工具，完成后用户可重试。"""
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
        msg = f"升级任务已下发：{reason}"
        if suggested:
            msg += f"（建议能力：{suggested}）"
        return ToolResult(
            success=True,
            data={
                "trigger_upgrade": True,
                "reason": reason,
                "suggested_capability": suggested,
                "message": msg
            }
        )
