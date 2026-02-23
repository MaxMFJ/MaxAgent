"""
Tool Registry for dynamic tool management
Supports registration, discovery, execution, and dynamic loading of tools
"""

import os
import sys
import importlib.util
import logging
from typing import Dict, List, Optional, Any

from .base import BaseTool, ToolResult, ToolCategory

logger = logging.getLogger(__name__)

# 动态工具目录（tools/generated/）
GENERATED_TOOLS_DIR = os.path.join(os.path.dirname(__file__), "generated")


class ToolRegistry:
    """
    Central registry for all available tools
    Supports dynamic registration and lookup
    """
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool) -> None:
        """Register a tool instance"""
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, overwriting")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")
    
    def register_many(self, tools: List[BaseTool]) -> None:
        """Register multiple tools at once"""
        for tool in tools:
            self.register(tool)
    
    def unregister(self, name: str) -> bool:
        """Unregister a tool by name"""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"Unregistered tool: {name}")
            return True
        return False
    
    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[BaseTool]:
        """Get all registered tools"""
        return list(self._tools.values())
    
    def list_by_category(self, category: ToolCategory) -> List[BaseTool]:
        """Get tools filtered by category"""
        return [t for t in self._tools.values() if t.category == category]
    
    def get_schemas(self) -> List[Dict[str, Any]]:
        """Get all tool schemas for LLM"""
        return [tool.to_function_schema() for tool in self._tools.values()]
    
    async def execute(self, name: str, **kwargs) -> ToolResult:
        """
        Execute a tool by name
        
        Args:
            name: Tool name
            **kwargs: Tool parameters
            
        Returns:
            ToolResult from tool execution
        """
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"未知工具: {name}",
                data={"tool_not_found": True, "tool_name": name}  # 供升级流程识别
            )
        
        validation_error = tool.validate_params(**kwargs)
        if validation_error:
            return ToolResult(success=False, error=validation_error)
        
        try:
            logger.info(f"Executing tool: {name} with params: {kwargs}")
            result = await tool.execute(**kwargs)
            logger.info(f"Tool {name} completed: success={result.success}")
            return result
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return ToolResult(success=False, error=str(e))
    
    def load_generated_tools(self) -> List[str]:
        """
        动态加载 tools/generated/ 目录下的新工具
        扫描 .py 文件，查找 BaseTool 子类并注册
        
        Returns:
            新加载的工具名称列表
        """
        loaded: List[str] = []
        if not os.path.exists(GENERATED_TOOLS_DIR):
            os.makedirs(GENERATED_TOOLS_DIR, exist_ok=True)
            return loaded
        
        for filename in sorted(os.listdir(GENERATED_TOOLS_DIR)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            
            module_name = f"tools.generated.{filename[:-3]}"
            filepath = os.path.join(GENERATED_TOOLS_DIR, filename)
            
            try:
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                if not spec or not spec.loader:
                    continue
                mod = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = mod
                spec.loader.exec_module(mod)
                
                for attr_name in dir(mod):
                    obj = getattr(mod, attr_name)
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, BaseTool)
                        and obj is not BaseTool
                        and not getattr(obj, "name", "").startswith("_")
                    ):
                        try:
                            instance = obj()
                            self.register(instance)
                            loaded.append(instance.name)
                            logger.info(f"Dynamic loaded tool: {instance.name} from {filename}")
                        except Exception as e:
                            logger.error(f"Failed to instantiate {obj.__name__}: {e}")
            except Exception as e:
                logger.error(f"Failed to load {filename}: {e}")
        
        return loaded
    
    def __len__(self) -> int:
        return len(self._tools)
    
    def __contains__(self, name: str) -> bool:
        return name in self._tools
