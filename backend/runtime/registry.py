"""
Runtime Registry - 注册式适配器管理
支持插件化、远程扩展，不依赖 if-else 平台判断
"""

import platform
import logging
from typing import Callable, Dict, List, Optional, Type

from .base import RuntimeAdapter

logger = logging.getLogger(__name__)

# 适配器工厂：system_name -> (adapter_class | factory_callable)
# 允许 register(system, AdapterClass) 或 register(system, lambda: get_remote_adapter())
_REGISTRY: Dict[str, Type[RuntimeAdapter] | Callable[[], RuntimeAdapter]] = {}

# 平台名映射
_SYSTEM_MAP = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}


def current_platform() -> str:
    """当前系统: darwin | linux | windows"""
    return _SYSTEM_MAP.get(platform.system(), platform.system().lower())


def register(system: str, adapter_cls_or_factory: Type[RuntimeAdapter] | Callable[[], RuntimeAdapter]) -> None:
    """
    注册适配器
    - adapter_cls_or_factory: 类（无参实例化）或工厂函数
    """
    _REGISTRY[system] = adapter_cls_or_factory
    logger.debug(f"Registered runtime adapter for {system}")


def unregister(system: str) -> None:
    """取消注册"""
    if system in _REGISTRY:
        del _REGISTRY[system]


def list_registered() -> List[str]:
    """已注册的系统列表"""
    return list(_REGISTRY.keys())


def _resolve_adapter(system: str) -> Optional[RuntimeAdapter]:
    factory = _REGISTRY.get(system)
    if factory is None:
        return None
    if callable(factory) and not isinstance(factory, type):
        return factory()
    return factory()


def get_runtime_adapter(system: Optional[str] = None) -> Optional[RuntimeAdapter]:
    """
    获取运行时适配器
    - system: 指定系统（Darwin/Linux/Windows），None 则用当前平台
    """
    target = system or platform.system()
    adapter = _resolve_adapter(target)
    if adapter is None:
        logger.warning(f"平台 {target} 暂无 RuntimeAdapter")
        return None
    if not adapter.is_available:
        logger.warning("RuntimeAdapter.is_available 为 False")
    return adapter


def get_runtime_adapter_for_test(mock: bool = True) -> Optional[RuntimeAdapter]:
    """
    测试用：返回 Mock 适配器
    用于 CI 无 GUI 环境
    """
    if mock:
        from .mock_adapter import MockRuntimeAdapter
        return MockRuntimeAdapter()
    return get_runtime_adapter()


# 兼容旧 API
def register_adapter(system: str, adapter_cls: type) -> None:
    """兼容：注册新平台适配器"""
    register(system, adapter_cls)


# 默认注册内置适配器
def _init_defaults():
    try:
        from .mac_adapter import MacRuntimeAdapter
        register("Darwin", MacRuntimeAdapter)
    except ImportError:
        pass
    try:
        from .linux_adapter import LinuxRuntimeAdapter
        register("Linux", LinuxRuntimeAdapter)
    except ImportError:
        pass
    try:
        from .windows_adapter import WindowsRuntimeAdapter
        register("Windows", WindowsRuntimeAdapter)
    except ImportError:
        pass


_init_defaults()
