"""
Human Demo Learning — 数据模型
定义人工 GUI 演示的事件、步骤和会话数据结构。
"""

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class HumanEvent:
    """单条原始系统事件（鼠标/键盘/截图）"""

    type: str  # mouse_click | key_press | scroll | screenshot | app_switch
    timestamp: float = 0.0
    data: Dict[str, Any] = field(default_factory=dict)
    # mouse_click data: {x, y, button, click_count, app_name, element_title, element_role, element_path}
    # key_press   data: {key, modifiers, text}
    # scroll      data: {x, y, delta_x, delta_y}
    # screenshot  data: {path, trigger_reason}
    # app_switch  data: {from_app, to_app}


@dataclass
class DemoStep:
    """语义化压缩后的单步操作"""

    id: str = ""
    action_type: str = ""  # click | type | scroll | shortcut | navigate | drag | select
    description: str = ""  # 人类可读描述, e.g. "点击 TextEdit 的 '保存' 按钮"
    target_selector: Dict[str, Any] = field(default_factory=dict)
    # {app, role, title, subrole, identifier, path}  ← AX 语义定位
    value: Optional[str] = None  # type 时的输入文本, shortcut 时的组合键
    screenshot_before: str = ""  # 截图文件路径
    screenshot_after: str = ""  # 截图文件路径
    timestamp: float = 0.0
    duration_ms: int = 0  # 该步骤持续时长
    raw_event_indices: List[int] = field(default_factory=list)  # 对应原始事件索引


@dataclass
class LearningResult:
    """LLM 学习分析结果"""

    inferred_goal: str = ""  # 推断的任务目标
    summary: str = ""  # 操作摘要
    capsule_json: Optional[Dict[str, Any]] = None  # 生成的 Capsule JSON
    capsule_id: str = ""  # 生成的 Capsule ID
    confidence: float = 0.0  # LLM 对此分析的置信度 0-1
    suggestions: List[str] = field(default_factory=list)  # 优化建议


@dataclass
class HumanDemoSession:
    """一次完整的人工演示会话"""

    id: str = ""
    task_description: str = ""  # 用户描述的目标
    events: List[HumanEvent] = field(default_factory=list)
    steps: List[DemoStep] = field(default_factory=list)  # 压缩后的语义步骤
    created_at: float = 0.0
    finished_at: float = 0.0
    duration_seconds: float = 0.0
    status: str = "recording"  # recording | finished | analyzed | approved

    # 第三层填充
    learning_result: Optional[LearningResult] = None
    generated_capsule_id: str = ""
    tags: List[str] = field(default_factory=list)

    @staticmethod
    def new(task_description: str = "", tags: Optional[List[str]] = None) -> "HumanDemoSession":
        now = time.time()
        return HumanDemoSession(
            id=f"demo_{uuid.uuid4().hex[:12]}",
            task_description=task_description,
            created_at=now,
            status="recording",
            tags=tags or [],
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    def to_summary(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task_description": self.task_description,
            "status": self.status,
            "event_count": len(self.events),
            "step_count": len(self.steps),
            "created_at": self.created_at,
            "duration_seconds": self.duration_seconds,
            "tags": self.tags,
            "generated_capsule_id": self.generated_capsule_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HumanDemoSession":
        events = [HumanEvent(**e) for e in data.get("events", [])]
        steps = [DemoStep(**s) for s in data.get("steps", [])]
        lr_data = data.get("learning_result")
        lr = LearningResult(**lr_data) if lr_data else None
        return cls(
            id=data.get("id", ""),
            task_description=data.get("task_description", ""),
            events=events,
            steps=steps,
            created_at=data.get("created_at", 0),
            finished_at=data.get("finished_at", 0),
            duration_seconds=data.get("duration_seconds", 0),
            status=data.get("status", "finished"),
            learning_result=lr,
            generated_capsule_id=data.get("generated_capsule_id", ""),
            tags=data.get("tags", []),
        )
