"""
Demo Step Compressor — 语义化压缩与步骤切割
将原始鼠标/键盘事件序列压缩为有意义的语义化操作步骤。

压缩规则：
  - 连续 key_press (带 text) → 合并为一个 type 步骤
  - mouse_click + AX 信息 → click 步骤(语义描述)
  - scroll → 合并连续滚动为一个步骤
  - app_switch → navigate 步骤
  - key_press (特殊键) → shortcut 步骤
"""

import logging
import os
from typing import List, Optional

from .human_demo_models import DemoStep, HumanDemoSession, HumanEvent

logger = logging.getLogger(__name__)


class DemoStepCompressor:
    """将原始 HumanEvent 列表压缩为 DemoStep 列表"""

    # 连续滚动合并的最大时间间隔（秒）
    SCROLL_MERGE_THRESHOLD = 1.0
    # 截图关联距离（事件索引范围）
    SCREENSHOT_LOOK_RANGE = 3

    def compress(self, session: HumanDemoSession) -> List[DemoStep]:
        """
        对 session.events 执行压缩，生成 session.steps 并返回。
        """
        events = session.events
        if not events:
            return []

        steps: List[DemoStep] = []
        i = 0
        step_counter = 0

        while i < len(events):
            event = events[i]

            if event.type == "mouse_click":
                step = self._compress_click(event, i, events, step_counter)
                steps.append(step)
                step_counter += 1
                i += 1

            elif event.type == "key_press":
                modifiers = event.data.get("modifiers", [])
                text = event.data.get("text", "")
                has_modifier = bool(modifiers)
                if text and not has_modifier:
                    # 普通文本输入 — 合并连续字符
                    merged_text, end_i = self._merge_consecutive_typing(events, i)
                    step = DemoStep(
                        id=f"step_{step_counter}",
                        action_type="type",
                        description=f"输入文本 \"{merged_text[:50]}{'...' if len(merged_text) > 50 else ''}\"",
                        value=merged_text,
                        timestamp=event.timestamp,
                        raw_event_indices=list(range(i, end_i + 1)),
                    )
                    steps.append(step)
                    step_counter += 1
                    i = end_i + 1
                else:
                    # 快捷键或特殊键
                    step = self._compress_shortcut(event, i, step_counter)
                    steps.append(step)
                    step_counter += 1
                    i += 1

            elif event.type == "text_input":
                # 从 AX 值变化推断的文本输入
                typed = event.data.get("typed_text", "")
                app = event.data.get("app_name", "")
                role = event.data.get("ui_role", "")
                if typed:
                    display_text = typed[:50] + ("..." if len(typed) > 50 else "")
                    desc = f"在 {app} 的 {role} 中输入 \"{display_text}\"" if app else f"输入文本 \"{display_text}\""
                    step = DemoStep(
                        id=f"step_{step_counter}",
                        action_type="type",
                        description=desc,
                        value=typed,
                        target_selector={"app": app, "role": role},
                        timestamp=event.timestamp,
                        raw_event_indices=[i],
                    )
                    steps.append(step)
                    step_counter += 1
                i += 1

            elif event.type == "scroll":
                # 合并连续滚动
                end_i = self._find_scroll_end(events, i)
                step = self._compress_scroll(events, i, end_i, step_counter)
                steps.append(step)
                step_counter += 1
                i = end_i + 1

            elif event.type == "app_switch":
                step = self._compress_app_switch(event, i, step_counter)
                steps.append(step)
                step_counter += 1
                i += 1

            else:
                # screenshot 等辅助事件跳过（已关联到其他步骤)
                i += 1

        session.steps = steps
        return steps

    # ── 各类型压缩 ──────────────────────────────────────

    def _compress_click(
        self, event: HumanEvent, idx: int, events: List[HumanEvent], step_id: int
    ) -> DemoStep:
        data = event.data
        app = data.get("app_name", "")
        # 支持新旧两种字段名
        role = data.get("ui_role", data.get("element_role", ""))
        title = data.get("ui_title", data.get("element_title", ""))
        label = data.get("ui_label", "")
        value = data.get("ui_value", "")
        description_text = data.get("ui_description", "")
        identifier = data.get("ui_identifier", data.get("element_identifier", ""))
        subrole = data.get("ui_subrole", data.get("element_subrole", ""))
        role_desc = data.get("ui_role_description", "")
        element_path = data.get("element_path", "")
        x = data.get("raw_x", data.get("x", 0))
        y = data.get("raw_y", data.get("y", 0))

        # 构建人类可读描述（优先使用语义信息）
        display_name = title or label or description_text or role_desc
        if display_name and role:
            desc = f"点击 {role}('{display_name}')"
        elif display_name:
            desc = f"点击 '{display_name}'"
        elif role:
            desc = f"点击 {role}"
        else:
            desc = f"点击坐标 ({x}, {y})"
        if app:
            desc = f"在 {app} 中 " + desc

        # 查找关联截图
        screenshot = data.get("screenshot_path", "")

        return DemoStep(
            id=f"step_{step_id}",
            action_type="click",
            description=desc,
            target_selector={
                "app": app,
                "role": role,
                "title": title,
                "label": label,
                "subrole": subrole,
                "identifier": identifier,
                "element_path": element_path,
                "raw_x": x,
                "raw_y": y,
            },
            screenshot_before=screenshot,
            timestamp=event.timestamp,
            raw_event_indices=[idx],
        )

    def _compress_type(self, event: HumanEvent, idx: int, step_id: int) -> DemoStep:
        text = event.data.get("text", "")
        # 截断过长文本用于描述
        display_text = text[:50] + ("..." if len(text) > 50 else "")
        return DemoStep(
            id=f"step_{step_id}",
            action_type="type",
            description=f"输入文本 \"{display_text}\"",
            value=text,
            timestamp=event.timestamp,
            raw_event_indices=[idx],
        )

    def _compress_shortcut(self, event: HumanEvent, idx: int, step_id: int) -> DemoStep:
        key = event.data.get("key", "") or str(event.data.get("key_code", ""))
        modifiers = event.data.get("modifiers", [])
        if modifiers:
            combo = "+".join(modifiers + [key])
        else:
            combo = key

        return DemoStep(
            id=f"step_{step_id}",
            action_type="shortcut",
            description=f"按键 {combo}",
            value=combo,
            timestamp=event.timestamp,
            raw_event_indices=[idx],
        )

    def _compress_scroll(
        self, events: List[HumanEvent], start: int, end: int, step_id: int
    ) -> DemoStep:
        total_dx, total_dy = 0, 0
        indices = []
        for i in range(start, end + 1):
            e = events[i]
            total_dx += e.data.get("delta_x", 0)
            total_dy += e.data.get("delta_y", 0)
            indices.append(i)

        direction = "下" if total_dy < 0 else "上" if total_dy > 0 else "横向"
        return DemoStep(
            id=f"step_{step_id}",
            action_type="scroll",
            description=f"滚动{direction} ({abs(total_dy)} 单位)",
            target_selector={
                "x": events[start].data.get("x", 0),
                "y": events[start].data.get("y", 0),
                "total_dx": total_dx,
                "total_dy": total_dy,
            },
            timestamp=events[start].timestamp,
            duration_ms=int((events[end].timestamp - events[start].timestamp) * 1000),
            raw_event_indices=indices,
        )

    def _compress_app_switch(self, event: HumanEvent, idx: int, step_id: int) -> DemoStep:
        from_app = event.data.get("from_app", "")
        to_app = event.data.get("to_app", "")
        return DemoStep(
            id=f"step_{step_id}",
            action_type="navigate",
            description=f"切换应用: {from_app} → {to_app}",
            target_selector={"from_app": from_app, "to_app": to_app},
            timestamp=event.timestamp,
            raw_event_indices=[idx],
        )

    def _find_scroll_end(self, events: List[HumanEvent], start: int) -> int:
        """找到连续滚动事件的末尾索引"""
        i = start + 1
        while i < len(events):
            if events[i].type != "scroll":
                break
            if events[i].timestamp - events[i - 1].timestamp > self.SCROLL_MERGE_THRESHOLD:
                break
            i += 1
        return i - 1

    def _merge_consecutive_typing(self, events: List[HumanEvent], start: int) -> tuple:
        """合并连续的普通文本 key_press 事件，返回 (merged_text, end_index)"""
        merged = []
        i = start
        # 连续打字的最大时间间隔（秒）
        MAX_GAP = 5.0
        while i < len(events):
            e = events[i]
            if e.type != "key_press":
                break
            modifiers = e.data.get("modifiers", [])
            text = e.data.get("text", "")
            if not text or modifiers:
                break
            if i > start and (e.timestamp - events[i - 1].timestamp) > MAX_GAP:
                break
            merged.append(text)
            i += 1
        return "".join(merged), i - 1


# ── 便捷函数 ──────────────────────────────────────────

def compress_demo_steps(session: HumanDemoSession) -> List[DemoStep]:
    """对单个演示会话执行步骤压缩"""
    compressor = DemoStepCompressor()
    return compressor.compress(session)
