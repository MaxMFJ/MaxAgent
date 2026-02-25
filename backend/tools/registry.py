"""
Tool Registry for dynamic tool management
Supports registration, discovery, execution, and dynamic loading of tools
安全：行为白名单、签名校验
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

# 是否跳过签名校验（不推荐）
TRUST_ALL_GENERATED = os.environ.get("MACAGENT_TRUST_ALL_GENERATED", "false").lower() == "true"


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
    
    def load_generated_tools(self, runtime_adapter=None) -> List[str]:
        """
        动态加载 tools/generated/ 目录下的新工具
        加载前：行为白名单校验、签名校验
        runtime_adapter: DI 注入，传给需要 adapter 的动态工具

        Returns:
            新加载的工具名称列表
        """
        try:
            from agent.upgrade_security import (
                check_code_safety,
                verify_tool_signature,
                is_path_allowed,
            )
        except ImportError:
            check_code_safety = lambda c: (True, "")
            verify_tool_signature = lambda fp, tn, ta=False: (True, "")
            is_path_allowed = lambda p: True
        
        loaded: List[str] = []
        if not os.path.exists(GENERATED_TOOLS_DIR):
            os.makedirs(GENERATED_TOOLS_DIR, exist_ok=True)
            return loaded
        
        for filename in sorted(os.listdir(GENERATED_TOOLS_DIR)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            
            module_name = f"tools.generated.{filename[:-3]}"
            filepath = os.path.join(GENERATED_TOOLS_DIR, filename)
            tool_name_from_file = filename[:-3]
            
            # 路径保护：仅加载 generated 目录
            if not is_path_allowed(filepath):
                logger.warning(f"Skipping {filename}: path not in allowed list")
                continue
            
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    code = f.read()
                
                # 行为白名单
                safe, err = check_code_safety(code)
                if not safe:
                    logger.warning(f"Skipping {filename}: {err}")
                    continue
                
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
                            # 优先注入 runtime_adapter（与 get_all_tools 一致）
                            import inspect
                            sig = inspect.signature(obj.__init__)
                            if "runtime_adapter" in sig.parameters:
                                instance = obj(runtime_adapter=runtime_adapter)
                            else:
                                instance = obj()
                            # 再次按工具名校验签名（因工具名可能与文件名不同）
                            verified, _ = verify_tool_signature(
                                filepath, instance.name, TRUST_ALL_GENERATED
                            )
                            if not verified:
                                logger.warning(f"Skipping {instance.name}: signature not verified")
                                continue
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


# === Tool Runtime v2: 结构化 Schema 注册（供 validator/router 使用）===
from .schema_registry import (
    TOOLS,
    get_tool,
    validate_args as validate_tool_args,
    build_from_base_tools,
    register_tool as register_schema,
)
