"""
UI Grounding Layer — 将 LLM 的 UI 意图映射到真实 UI 元素
桥接高层语义（"点击发送按钮"）与底层 AX/坐标系统。

功能：
1. AX 元素查询：通过 Swift AX Bridge 获取实时 UI 树
2. 元素匹配：根据角色/标题/文本等属性匹配目标元素
3. 坐标校验：验证 LLM 给出的坐标是否合理
4. UI 快照：生成结构化的 UI 状态描述给 LLM
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class UIElement:
    """单个 UI 元素"""
    role: str = ""               # AXButton, AXTextField, ...
    title: str = ""
    value: str = ""
    pos_x: float = 0.0
    pos_y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    enabled: bool = True
    focused: bool = False
    children_count: int = 0

    @property
    def center(self) -> Tuple[float, float]:
        return (self.pos_x + self.width / 2, self.pos_y + self.height / 2)

    @property
    def label(self) -> str:
        """可显示的标签"""
        parts = []
        if self.role:
            parts.append(self.role.replace("AX", ""))
        if self.title:
            parts.append(f'"{self.title}"')
        elif self.value:
            parts.append(f'val="{self.value[:30]}"')
        return " ".join(parts) if parts else "Unknown"

    def contains_point(self, x: float, y: float) -> bool:
        return (self.pos_x <= x <= self.pos_x + self.width and
                self.pos_y <= y <= self.pos_y + self.height)

    @staticmethod
    def from_ax_dict(d: Dict[str, Any]) -> "UIElement":
        """从 AX Bridge 返回的 dict 构建"""
        frame = d.get("frame", {})
        return UIElement(
            role=d.get("role", ""),
            title=d.get("title", ""),
            value=str(d.get("value", ""))[:100] if d.get("value") else "",
            pos_x=frame.get("x", 0),
            pos_y=frame.get("y", 0),
            width=frame.get("width", 0),
            height=frame.get("height", 0),
            enabled=d.get("enabled", True),
            focused=d.get("focused", False),
            children_count=d.get("children_count", 0),
        )


@dataclass
class UISnapshot:
    """UI 状态快照"""
    app_name: str = ""
    window_title: str = ""
    elements: List[UIElement] = field(default_factory=list)
    total_elements: int = 0
    focused_element: Optional[UIElement] = None
    timestamp: float = field(default_factory=time.time)

    def find_by_role(self, role: str) -> List[UIElement]:
        role_lower = role.lower()
        return [e for e in self.elements
                if e.role.lower() == role_lower or e.role.lower() == f"ax{role_lower}"]

    def find_by_title(self, title: str, fuzzy: bool = True) -> List[UIElement]:
        title_lower = title.lower()
        if fuzzy:
            return [e for e in self.elements if title_lower in e.title.lower()]
        return [e for e in self.elements if e.title.lower() == title_lower]

    def find_by_role_and_title(self, role: str, title: str) -> List[UIElement]:
        role_lower = role.lower()
        title_lower = title.lower()
        return [
            e for e in self.elements
            if (e.role.lower() == role_lower or e.role.lower() == f"ax{role_lower}")
            and title_lower in e.title.lower()
        ]

    def element_at(self, x: float, y: float) -> Optional[UIElement]:
        """找到包含指定坐标的最小元素"""
        matches = [e for e in self.elements if e.contains_point(x, y)]
        if not matches:
            return None
        # 返回面积最小的（最精确的）
        return min(matches, key=lambda e: e.width * e.height)

    def interactive_elements(self) -> List[UIElement]:
        """返回可交互元素"""
        interactive_roles = {
            "axbutton", "axtextfield", "axtextarea", "axcheckbox",
            "axradiobutton", "axpopupbutton", "axcombobox", "axslider",
            "axlink", "axmenuitem", "axtab", "axtabgroup",
            "axincrementor", "axcolorwell", "axmenubutton",
        }
        return [e for e in self.elements
                if e.role.lower() in interactive_roles and e.enabled]

    def for_llm(self, max_elements: int = 30) -> str:
        """生成给 LLM 的 UI 快照描述"""
        parts = []
        if self.app_name:
            header = f"[{self.app_name}]"
            if self.window_title:
                header += f" {self.window_title}"
            parts.append(header)

        # 优先展示可交互元素
        interactive = self.interactive_elements()
        if interactive:
            parts.append(f"可交互元素 ({len(interactive)}):")
            for i, e in enumerate(interactive[:max_elements]):
                cx, cy = e.center
                line = f"  [{i}] {e.label} @({cx:.0f},{cy:.0f})"
                if e.focused:
                    line += " [焦点]"
                parts.append(line)
            if len(interactive) > max_elements:
                parts.append(f"  ... 还有 {len(interactive) - max_elements} 个")

        if self.focused_element:
            parts.append(f"焦点: {self.focused_element.label}")

        return "\n".join(parts)


class UIGrounding:
    """
    UI Grounding 层 — 将语义意图映射到 UI 元素。

    使用 Swift AX Bridge（accessibility_bridge_client）获取实时 AX 树，
    结合 screenshot OCR 进行 UI 状态感知。
    """

    def __init__(self):
        self._last_snapshot: Optional[UISnapshot] = None
        self._bridge_available: Optional[bool] = None

    async def _ensure_bridge(self) -> bool:
        """检查 AX Bridge 是否可用（带缓存）"""
        if self._bridge_available is not None:
            return self._bridge_available
        try:
            from backend.runtime.accessibility_bridge_client import is_bridge_available
            self._bridge_available = await is_bridge_available()
        except ImportError:
            logger.warning("accessibility_bridge_client 不可用")
            self._bridge_available = False
        return self._bridge_available

    def reset_bridge_cache(self) -> None:
        """重置 bridge 可用性缓存（连接状态可能变化）"""
        self._bridge_available = None

    async def capture_snapshot(self, app_name: str = "", max_depth: int = 5,
                               max_count: int = 200) -> UISnapshot:
        """
        捕获当前 UI 快照。
        如果不指定 app_name，则获取当前焦点应用。
        """
        snap = UISnapshot()

        if not await self._ensure_bridge():
            logger.debug("AX Bridge 不可用，返回空快照")
            return snap

        from backend.runtime import accessibility_bridge_client as ax

        # 确定目标应用
        if not app_name:
            focused = await ax.get_focused_element()
            if focused:
                app_name = focused.get("app", "")
                snap.focused_element = UIElement.from_ax_dict(focused)

        if not app_name:
            return snap

        snap.app_name = app_name

        # 获取窗口信息
        windows = await ax.get_windows(app_name)
        if windows:
            snap.window_title = windows[0].get("title", "")

        # 获取扁平元素列表
        elements, total = await ax.get_flat_elements(
            app_name=app_name,
            max_depth=max_depth,
            max_count=max_count,
        )
        snap.total_elements = total
        snap.elements = [UIElement.from_ax_dict(e) for e in elements]

        self._last_snapshot = snap
        return snap

    async def find_element(self, app_name: str, role: str = "",
                           title: str = "") -> Optional[UIElement]:
        """通过 AX Bridge 直接搜索元素"""
        if not await self._ensure_bridge():
            return None

        from backend.runtime import accessibility_bridge_client as ax

        results = await ax.find_elements(
            app_name=app_name,
            role=role or None,
            title=title or None,
        )
        if results:
            return UIElement.from_ax_dict(results[0])
        return None

    async def validate_click_target(self, x: float, y: float,
                                    expected_role: str = "",
                                    expected_title: str = "") -> Dict[str, Any]:
        """
        验证点击坐标是否指向预期的 UI 元素。
        返回验证结果，包含实际元素信息和是否匹配。
        """
        result: Dict[str, Any] = {"valid": False, "x": x, "y": y}

        if not await self._ensure_bridge():
            result["reason"] = "AX Bridge 不可用"
            return result

        from backend.runtime import accessibility_bridge_client as ax

        actual = await ax.get_element_at(x, y)
        if not actual:
            result["reason"] = f"坐标 ({x},{y}) 处没有可识别的 UI 元素"
            return result

        elem = UIElement.from_ax_dict(actual)
        result["actual_element"] = elem.label
        result["actual_role"] = elem.role
        result["actual_title"] = elem.title

        # 检查匹配
        role_ok = not expected_role or elem.role.lower().replace("ax", "") == expected_role.lower().replace("ax", "")
        title_ok = not expected_title or expected_title.lower() in elem.title.lower()

        if role_ok and title_ok:
            result["valid"] = True
        else:
            result["valid"] = False
            reasons = []
            if expected_role and not role_ok:
                reasons.append(f"期望角色 {expected_role}，实际是 {elem.role}")
            if expected_title and not title_ok:
                reasons.append(f"期望标题含 '{expected_title}'，实际是 '{elem.title}'")
            result["reason"] = "; ".join(reasons)

            # 尝试建议正确坐标
            if expected_title and self._last_snapshot:
                matches = self._last_snapshot.find_by_title(expected_title)
                if matches:
                    best = matches[0]
                    cx, cy = best.center
                    result["suggestion"] = {
                        "x": cx, "y": cy,
                        "element": best.label,
                    }

        return result

    async def get_focused_info(self) -> Dict[str, str]:
        """获取当前焦点应用和元素信息"""
        info: Dict[str, str] = {"app": "", "window": "", "element": ""}
        if not await self._ensure_bridge():
            return info

        from backend.runtime import accessibility_bridge_client as ax

        focused = await ax.get_focused_element()
        if focused:
            elem = UIElement.from_ax_dict(focused)
            info["element"] = elem.label
            info["app"] = focused.get("app", "")
        return info

    async def generate_ui_observation(self, app_name: str = "") -> str:
        """
        生成 UI 观察文本给 LLM。
        用于 Observation Loop。
        """
        snap = await self.capture_snapshot(app_name=app_name)
        if not snap.elements:
            return "无法获取 UI 状态（AX Bridge 可能不可用）"
        return snap.for_llm()

    @property
    def last_snapshot(self) -> Optional[UISnapshot]:
        return self._last_snapshot


# 单例
_ui_grounding: Optional[UIGrounding] = None


def get_ui_grounding() -> UIGrounding:
    global _ui_grounding
    if _ui_grounding is None:
        _ui_grounding = UIGrounding()
    return _ui_grounding
