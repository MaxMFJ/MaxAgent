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
    description = "完整的隧道监控工具包，提供隧道状态监控、连接管理、日志查看、性能监控等功能。支持 SSH、OpenVPN、WireGuard、IPSec 等常见隧道类型。"
    category = ToolCategory.SYSTEM
    parameters = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": "要执行的操作：status, connections, logs, performance, config",
            "enum": [
                "status",
                "connections",
                "logs",
                "performance",
                "config"
            ]
        },
        "tunnel_name": {
            "type": "string",
            "description": "隧道名称，如不指定则处理所有隧道"
        },
        "lines": {
            "type": "integer",
            "description": "查看日志时显示的行数",
            "default": 50
        },
        "duration": {
            "type": "integer",
            "description": "性能监控持续时间（秒）",
            "default": 10
        }
    },
    "required": [
        "action"
    ]
}

    async def execute(self, **kwargs) -> ToolResult:
        # 实现逻辑
        return ToolResult(success=True, data={...})
```

## 你的具体任务

在 backend/tools/generated/ 目录下创建 tunnel_tools_examples.py 文件。提供完整的工具使用示例和集成指南：

1. 每个工具的完整使用示例
2. 工具链组合使用场景
3. 常见问题解决方案
4. 与现有 Agent 系统的集成方法
5. 配置说明和最佳实践

内容要求：
- 包含导入和使用每个工具的代码示例
- 展示工具链如何协同工作
- 提供错误处理示例
- 说明如何扩展和自定义功能
- 包含性能优化建议
- 添加版本兼容性说明

---

## 完成后
1. 保存所有文件
2. 新工具将自动加载，用户可立即在 Chat 中调用
