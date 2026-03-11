"""
Demo Learner — LLM 意图分析与 Capsule 生成
将人工演示的语义化步骤发送给 LLM，学习人类操作意图并生成可重用的 SkillCapsule。

流程：
  1. 收集演示步骤 + 截图 + 用户目标描述
  2. 构建多模态 prompt（文本 + 视觉）
  3. LLM 分析：推断目标、泛化步骤、参数化变量
  4. 生成 SkillCapsule JSON
  5. 可选：注册到 CapsuleRegistry
"""

import json
import logging
import os
import base64
import time
from typing import Any, Dict, List, Optional

from .human_demo_models import DemoStep, HumanDemoSession, LearningResult
from .capsule_models import SkillCapsule

logger = logging.getLogger(__name__)

# ── 系统 Prompt ──────────────────────────────────────────

DEMO_LEARNER_SYSTEM_PROMPT = """你是 macOS GUI 自动化语义分析专家。

# 核心原则（最高优先级）

**绝对禁止学习或依赖固定 XY 坐标。**

坐标仅供你理解空间上下文（如"屏幕右上角"），但生成的 Capsule 中
不得出现任何 raw_x / raw_y / 坐标数值。所有 UI 定位必须基于
Accessibility (AX) 语义属性：role、title、label、identifier、element_path。

核心理念：XY 坐标 ≠ 语义。坐标会因窗口位置、分辨率而改变；
AX 属性才是稳定的 UI 语义标识。

# 你的任务

给定一段人工 GUI 操作的语义化录制数据（每步包含 AX 元素信息），你需要：

## 第一步：推断真实目标
- 根据操作上下文推断用户想完成的任务
- 用一句话描述 inferred_goal

## 第二步：重建语义步骤
将原始录制步骤提升为"意图级动作"。例如：
  - 原始：点击 AXButton('发送') → 语义：click_button(label="发送")
  - 原始：在 AXTextField 中输入 "hello" → 语义：type_in_field(role="AXTextField", text="hello")
  - 原始：打开微信 → 语义：open_app(name="微信")
每个语义步骤需包含：
  - intent_action：意图级动作名
  - semantic_target：{app, role, title, label, identifier, path_hint}（至少2个有效属性）
  - args：该步骤的参数
  - reasoning：为什么选择这个定位方式

## 第三步：识别可变参数
- 用户输入的文本内容 → {{input.参数名}}
- 收件人/联系人/搜索词等动态值 → {{input.参数名}}
- 固定的 UI 按钮/菜单操作 → 保持不变

## 第四步：生成可重用 Capsule

### Capsule procedure 中可用的 tool 和 action：

**gui_automation**（首选，语义定位）:
  - click_element: {"action": "click_element", "app_name": "应用名", "element_name": "按AX title/label定位的元素名"}
  - type_text: {"action": "type_text", "app_name": "应用名", "text": "内容"}
  - find_elements: {"action": "find_elements", "app_name": "应用名", "element_name": "元素名"}
  - get_gui_state: {"action": "get_gui_state", "app_name": "应用名"}

**app_control**（应用生命周期）:
  - open: {"action": "open", "app_name": "应用名"}
  - close: {"action": "close", "app_name": "应用名"}
  - activate: {"action": "activate", "app_name": "应用名"}

**input_control**（仅用于语义定位不可用时的回退）:
  - keyboard_type: {"action": "keyboard_type", "text": "内容"}
  - keyboard_key: {"action": "keyboard_key", "key": "return"}
  - keyboard_shortcut: {"action": "keyboard_shortcut", "keys": ["cmd", "v"]}
  - ⚠️ mouse_click 仅在绝对无法语义定位时使用，且必须加注释说明原因

**screenshot**（验证用）:
  - capture: {"action": "capture", "app_name": "应用名"}

### Capsule 优先级规则：
1. 优先用 gui_automation.click_element (按 title/label 定位)
2. 文本输入优先用 gui_automation.type_text
3. 只有当 AX 信息不足时才回退到 input_control
4. 绝不在 Capsule 中硬编码坐标

# 输出格式

请严格返回以下 JSON（不要添加其他内容）：
```json
{
  "inferred_goal": "一句话描述推断的任务目标",
  "summary": "操作摘要",
  "confidence": 0.85,
  "semantic_steps": [
    {
      "intent_action": "open_app",
      "semantic_target": {"app": "微信"},
      "args": {},
      "reasoning": "用户需要先打开目标应用"
    },
    {
      "intent_action": "click_button",
      "semantic_target": {"app": "微信", "role": "AXStaticText", "title": "联系人名"},
      "args": {"element_name": "{{input.recipient}}"},
      "reasoning": "通过 AX title 定位联系人，title 是可变参数"
    }
  ],
  "suggestions": ["优化建议"],
  "capsule": {
    "id": "demo_generated_<简短英文标识>",
    "description": "技能的中文描述",
    "inputs": {
      "参数名": {"type": "string", "description": "参数描述"}
    },
    "outputs": {
      "result": {"type": "object", "description": "执行结果"}
    },
    "procedure": [
      {
        "id": "step_0",
        "type": "tool",
        "tool": "gui_automation 或 app_control 或 input_control",
        "args": {"action": "...", "其他参数": "..."},
        "description": "该步骤的语义描述"
      }
    ],
    "task_type": "gui_task",
    "tags": ["标签1"],
    "capability": ["能力关键词"]
  }
}
```

# 硬性规则（违反任何一条即为失败）
1. procedure 中禁止出现 x、y、raw_x、raw_y 等坐标参数
2. click_element 必须用 element_name 语义定位，不得用坐标
3. 可变内容必须参数化为 {{input.xxx}}
4. element_name 应使用录制数据中的 AX title / label / identifier，不可自行编造
5. 每个 procedure step 的 tool 必须是 gui_automation / app_control / input_control / screenshot 之一
6. 每个 step 必须有 description 说明意图
7. 聊天应用发送消息用 keyboard_key(key="return")，不要用 keyboard_shortcut(cmd+return)"""


class DemoLearner:
    """
    使用 LLM 分析人工演示，生成可重用的 SkillCapsule。
    """

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: LLMClient 实例（可选，不传则在调用时自动获取）
        """
        self._llm_client = llm_client

    def _get_llm_client(self):
        if self._llm_client:
            return self._llm_client
        from .llm_client import LLMClient, LLMConfig
        from config.llm_config import load_llm_config
        cfg = load_llm_config()
        config = LLMConfig(
            provider=cfg.get("provider", "deepseek"),
            api_key=cfg.get("api_key"),
            base_url=cfg.get("base_url", ""),
            model=cfg.get("model", "deepseek-chat"),
        )
        self._llm_client = LLMClient(config)
        return self._llm_client

    async def analyze(self, session: HumanDemoSession) -> LearningResult:
        """
        分析演示会话，生成 LearningResult（含 Capsule JSON）。
        """
        if not session.steps:
            return LearningResult(
                inferred_goal="",
                summary="无有效步骤",
                confidence=0,
            )

        messages = self._build_messages(session)
        client = self._get_llm_client()

        try:
            response = await client.chat(messages=messages, max_tokens=4096)
            content = response.get("content", "")
            result = self._parse_response(content, session)
            return result
        except Exception as e:
            logger.error(f"DemoLearner analyze failed: {e}")
            return LearningResult(
                inferred_goal="",
                summary=f"LLM 分析失败: {e}",
                confidence=0,
            )

    def _build_messages(self, session: HumanDemoSession) -> List[Dict[str, Any]]:
        """构建发送给 LLM 的消息序列，重点输出 AX 语义信息"""
        messages = [{"role": "system", "content": DEMO_LEARNER_SYSTEM_PROMPT}]

        user_parts = []

        if session.task_description:
            user_parts.append(f"用户目标描述: \"{session.task_description}\"\n")

        user_parts.append(f"演示包含 {len(session.steps)} 个语义化步骤:\n")

        for i, step in enumerate(session.steps):
            # 基本信息
            step_desc = f"[步骤{i+1}] action_type={step.action_type}: {step.description}"
            if step.value:
                step_desc += f"\n  输入值: \"{step.value[:200]}\""

            # AX 语义定位信息（核心数据）
            if step.target_selector:
                sel = step.target_selector
                ax_parts = []
                for key in ("app", "role", "title", "label", "subrole", "identifier", "element_path"):
                    val = sel.get(key)
                    if val:
                        ax_parts.append(f"{key}={val}")
                if ax_parts:
                    step_desc += f"\n  AX语义: {', '.join(ax_parts)}"
                # 坐标仅作参考上下文
                raw_x = sel.get("raw_x")
                raw_y = sel.get("raw_y")
                if raw_x or raw_y:
                    step_desc += f"\n  (坐标参考，仅用于理解空间位置: x={raw_x}, y={raw_y})"

            user_parts.append(step_desc)

        user_content = "\n".join(user_parts)

        # 尝试附带截图（视觉能力）
        content_blocks = [{"type": "text", "text": user_content}]
        screenshot_count = 0
        max_screenshots = 5  # 限制截图数量避免 token 超标

        for step in session.steps:
            if screenshot_count >= max_screenshots:
                break
            screenshot_path = step.screenshot_before or step.screenshot_after
            if screenshot_path and os.path.isfile(screenshot_path):
                try:
                    with open(screenshot_path, "rb") as f:
                        img_b64 = base64.b64encode(f.read()).decode("utf-8")
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    })
                    screenshot_count += 1
                except Exception as e:
                    logger.debug(f"Failed to encode screenshot: {e}")

        # 如果有截图，使用多模态格式；否则纯文本
        if screenshot_count > 0:
            messages.append({"role": "user", "content": content_blocks})
        else:
            messages.append({"role": "user", "content": user_content})

        return messages

    def _parse_response(self, content: str, session: HumanDemoSession) -> LearningResult:
        """解析 LLM 返回的 JSON 结果"""
        # 尝试从 markdown code block 中提取 JSON
        json_str = content
        if "```json" in content:
            start = content.index("```json") + 7
            end = content.index("```", start)
            json_str = content[start:end].strip()
        elif "```" in content:
            start = content.index("```") + 3
            end = content.index("```", start)
            json_str = content[start:end].strip()

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # 尝试 JSON repair
            try:
                from llm.json_repair import repair_json
                repaired = repair_json(json_str)
                data = json.loads(repaired)
            except Exception:
                logger.warning("Failed to parse LLM response as JSON")
                return LearningResult(
                    inferred_goal="",
                    summary=content[:500],
                    confidence=0,
                )

        capsule_data = data.get("capsule", {})
        capsule_id = capsule_data.get("id", f"demo_gen_{session.id}")

        # 验证 capsule 中无坐标泄露
        if capsule_data:
            self._strip_coordinates_from_capsule(capsule_data)

        return LearningResult(
            inferred_goal=data.get("inferred_goal", ""),
            summary=data.get("summary", ""),
            capsule_json=capsule_data if capsule_data else None,
            capsule_id=capsule_id,
            confidence=float(data.get("confidence", 0)),
            suggestions=data.get("suggestions", []),
        )

    def _strip_coordinates_from_capsule(self, capsule_data: Dict[str, Any]):
        """安全检查：移除 capsule procedure 中意外残留的坐标参数"""
        procedure = capsule_data.get("procedure", [])
        coord_keys = {"x", "y", "raw_x", "raw_y"}
        for step in procedure:
            args = step.get("args", {})
            removed = [k for k in coord_keys if k in args]
            for k in removed:
                del args[k]
            if removed:
                logger.warning(f"Stripped coordinates {removed} from capsule step {step.get('id')}")

    def capsule_from_result(self, result: LearningResult) -> Optional[SkillCapsule]:
        """从学习结果创建 SkillCapsule 对象"""
        if not result.capsule_json:
            return None
        try:
            capsule_data = dict(result.capsule_json)
            capsule_data.setdefault("source", "human_demo")
            capsule_data.setdefault("author", "demo_learner")
            return SkillCapsule.from_dict(capsule_data)
        except Exception as e:
            logger.error(f"Failed to create capsule from result: {e}")
            return None

    async def learn_and_register(
        self,
        session: HumanDemoSession,
        auto_approve: bool = False,
    ) -> LearningResult:
        """
        分析演示 + 可选自动注册 Capsule。

        Args:
            session: 演示会话
            auto_approve: True 时自动注册到 CapsuleRegistry

        Returns:
            LearningResult
        """
        result = await self.analyze(session)
        session.learning_result = result
        session.status = "analyzed"

        if auto_approve and result.capsule_json and result.confidence >= 0.7:
            capsule = self.capsule_from_result(result)
            if capsule:
                try:
                    from .capsule_registry import get_capsule_registry
                    registry = get_capsule_registry()
                    registry.register(capsule)
                    session.generated_capsule_id = capsule.id
                    session.status = "approved"
                    logger.info(f"Auto-approved capsule: {capsule.id}")
                except Exception as e:
                    logger.error(f"Failed to auto-register capsule: {e}")

        return result

    def approve_capsule(self, session: HumanDemoSession) -> Optional[SkillCapsule]:
        """
        人工审批：将学习结果中的 Capsule 注册到 Registry。

        Returns:
            注册的 SkillCapsule，失败则 None
        """
        if not session.learning_result or not session.learning_result.capsule_json:
            return None

        capsule = self.capsule_from_result(session.learning_result)
        if not capsule:
            return None

        try:
            from .capsule_registry import get_capsule_registry
            registry = get_capsule_registry()
            registry.register(capsule)
            session.generated_capsule_id = capsule.id
            session.status = "approved"

            # 持久化 capsule 到磁盘
            from paths import DATA_DIR
            capsule_dir = os.path.join(DATA_DIR, "capsules")
            os.makedirs(capsule_dir, exist_ok=True)
            capsule_path = os.path.join(capsule_dir, f"{capsule.id}.json")
            with open(capsule_path, "w", encoding="utf-8") as f:
                json.dump(capsule.to_dict(), f, ensure_ascii=False, indent=2)

            logger.info(f"Capsule approved and saved: {capsule.id}")
            return capsule
        except Exception as e:
            logger.error(f"Failed to approve capsule: {e}")
            return None


# ── 单例 ──────────────────────────────────────────────────────
_learner: Optional[DemoLearner] = None


def get_demo_learner() -> DemoLearner:
    global _learner
    if _learner is None:
        _learner = DemoLearner()
    return _learner
