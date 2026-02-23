"""
Event Schema - 统一事件模型
强制所有 publish 使用 Event 实例，支持 trace_id、timestamp、priority
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict

# 优先级常量：越小越优先
PRIORITY_TOOL_FAILED = 1
PRIORITY_TOOL_NOT_FOUND = 2
PRIORITY_PARSE_FAILED = 3
PRIORITY_TRIGGER_UPGRADE = 4
PRIORITY_DEFAULT = 5


@dataclass
class Event:
    """标准事件模型"""

    type: str
    payload: Dict[str, Any]
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    priority: int = PRIORITY_DEFAULT  # 默认中等优先级
