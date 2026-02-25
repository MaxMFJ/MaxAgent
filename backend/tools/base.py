"""
Base Tool class for all agent tools
Defines the standard interface for tool implementation
支持依赖注入：runtime_adapter 由 Agent 在初始化时传入，Tool 禁止自行获取全局 adapter
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    from runtime import RuntimeAdapter


class ToolException(Exception):
    """Exception raised when a tool execution fails (invalid input, runtime error, etc.)."""
    pass


class ToolCategory(Enum):
    """Tool categories for organization"""
    FILE = "file"
    TERMINAL = "terminal"
    APPLICATION = "application"
    SYSTEM = "system"
    CLIPBOARD = "clipboard"
    BROWSER = "browser"
    CUSTOM = "custom"


@dataclass
class ToolResult:
    """Standardized tool execution result"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"success": self.success}
        if self.data is not None:
            result["data"] = self.data
        if self.error:
            result["error"] = self.error
        return result
    
    def to_string(self) -> str:
        """Convert result to string for LLM consumption (excludes large data like base64)"""
        if self.success:
            if isinstance(self.data, dict):
                import json
                # 过滤掉大型数据字段，避免 token 超限
                filtered_data = self._filter_large_data(self.data)
                return json.dumps(filtered_data, ensure_ascii=False, indent=2)
            elif isinstance(self.data, list):
                import json
                return json.dumps(self.data, ensure_ascii=False, indent=2)
            return str(self.data) if self.data else "操作成功"
        return f"错误: {self.error}"
    
    def _filter_large_data(self, data: Dict) -> Dict:
        """Filter out large data fields like base64 images"""
        if not isinstance(data, dict):
            return data
        
        filtered = {}
        large_fields = {"image_base64", "base64", "data", "content"}
        
        for key, value in data.items():
            if key in large_fields and isinstance(value, str) and len(value) > 1000:
                # 替换大型数据为简短描述
                filtered[key] = f"[{len(value)} 字符的数据，已省略]"
            elif isinstance(value, dict):
                filtered[key] = self._filter_large_data(value)
            else:
                filtered[key] = value
        
        return filtered


class BaseTool(ABC):
    """
    Abstract base class for all tools
    
    依赖注入：runtime_adapter 由 Agent 传入，Tool 禁止调用 get_runtime_adapter()
    
    Each tool must define:
    - name: Unique identifier for the tool
    - description: Human-readable description for LLM
    - parameters: JSON Schema defining tool parameters
    - category: Tool category for organization
    
    And implement:
    - execute(): Async method to perform the tool action
    """
    
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any]
    category: ToolCategory = ToolCategory.CUSTOM
    requires_confirmation: bool = False  # Set True for dangerous operations
    
    def __init__(self, runtime_adapter: Optional["RuntimeAdapter"] = None):
        self.runtime_adapter = runtime_adapter  # DI: 由 Agent 注入
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with given parameters
        
        Args:
            **kwargs: Tool-specific parameters
            
        Returns:
            ToolResult with success status and data/error
        """
        pass
    
    def to_function_schema(self) -> Dict[str, Any]:
        """
        Convert tool to OpenAI Function Calling format
        
        Returns:
            Dict compatible with OpenAI tools parameter
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }
    
    def validate_params(self, **kwargs) -> Optional[str]:
        """
        Validate parameters against schema
        
        Returns:
            Error message if validation fails, None otherwise
        """
        required = self.parameters.get("required", [])
        for param in required:
            if param not in kwargs:
                return f"缺少必需参数: {param}"
        return None
    
    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"
