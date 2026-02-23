"""
示例：动态加载工具的格式
用于测试动态加载功能 - 可删除或重命名
"""
from tools.base import BaseTool, ToolResult, ToolCategory


class ExampleGeneratedTool(BaseTool):
    """示例动态工具 - 用于测试动态加载"""
    
    name = "example_generated"
    description = "示例动态工具，用于验证动态加载功能"
    category = ToolCategory.CUSTOM
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "要回显的消息"}
        },
        "required": []
    }
    
    async def execute(self, **kwargs) -> ToolResult:
        msg = kwargs.get("message", "dynamic load ok")
        return ToolResult(success=True, data={"echo": msg, "source": "generated"})
