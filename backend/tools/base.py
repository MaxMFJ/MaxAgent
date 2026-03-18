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
    
    # 发送给 LLM 的工具结果最大字符数
    MAX_RESULT_CHARS = 3000
    # 含 content 的 read 类结果：降低上限防止上下文爆炸（从 15000 降至 8000）
    MAX_RESULT_CHARS_READ = 8000

    def to_string(self) -> str:
        """Convert result to string for LLM consumption (excludes large/binary data)"""
        if self.success:
            if isinstance(self.data, dict):
                import json
                filtered_data = self._filter_large_data(self.data)
                text = json.dumps(filtered_data, ensure_ascii=False, indent=2)
            elif isinstance(self.data, list):
                import json
                filtered_list = [
                    self._filter_large_data(item) if isinstance(item, dict) else item
                    for item in self.data
                ]
                text = json.dumps(filtered_list, ensure_ascii=False, indent=2)
            else:
                text = str(self.data) if self.data else "操作成功"

            # 含 content 的 read 结果使用更高上限
            max_chars = (
                self.MAX_RESULT_CHARS_READ
                if isinstance(self.data, dict) and "content" in self.data
                else self.MAX_RESULT_CHARS
            )
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n...[结果已截断，原始长度 {len(text)} 字符]"
            return text
        return f"错误: {self.error}"

    # 已知的二进制/大体积字段名（精确匹配）
    _BINARY_FIELD_NAMES = {
        "image_base64", "base64", "screenshot_data", "binary",
        "raw_data", "encoded", "audio_base64",
    }
    # 高价值文本字段（如 file read 的 content、design_spec）：保留更多字符供 LLM 使用
    _TEXT_CONTENT_KEYS = {"content"}

    def _filter_large_data(self, data: Dict) -> Dict:
        """Filter out binary blobs and oversized string values from tool results"""
        if not isinstance(data, dict):
            return data

        filtered = {}
        for key, value in data.items():
            if isinstance(value, str):
                # 已知二进制字段或任何超长字符串
                is_known_binary = key in self._BINARY_FIELD_NAMES
                is_text_content = key in self._TEXT_CONTENT_KEYS
                # content 字段（如 read_file 结果）保留 6000 字符（从 12000 降低，避免上下文爆炸）
                max_str = 6000 if is_text_content else 1500
                is_oversized = len(value) > max_str
                if is_known_binary and len(value) > 200:
                    filtered[key] = f"[二进制数据，{len(value)} 字符，已省略]"
                elif is_oversized:
                    filtered[key] = value[:max_str] + f"...[截断，共 {len(value)} 字符]"
                else:
                    filtered[key] = value
            elif isinstance(value, dict):
                filtered[key] = self._filter_large_data(value)
            elif isinstance(value, list):
                filtered[key] = [
                    self._filter_large_data(item) if isinstance(item, dict) else item
                    for item in value[:50]  # 最多保留 50 个元素
                ]
                if len(value) > 50:
                    filtered[key].append(f"...[共 {len(value)} 项，已截断]")
            elif isinstance(value, bytes):
                filtered[key] = f"[二进制数据，{len(value)} 字节]"
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
            "parameters": self.parameters,
            "category": self.category.value if hasattr(self.category, 'value') else str(self.category),
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
