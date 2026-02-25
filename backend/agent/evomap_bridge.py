"""
EvoMap Bridge - lightweight adapter between AgentCore and EvoMap service.
增强版：优先使用本地 Capsule 库（加权搜索），自动推荐可执行 Capsule，
然后回退到 EvoMap 网络策略。
当 ENABLE_EVOMAP=false 时仅使用本地能力，不访问 EvoMap 网络。
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

ENABLE_EVOMAP = os.environ.get("ENABLE_EVOMAP", "false").lower() == "true"


async def evomap_enhance_context(task_description: str) -> str:
    """
    Query local Capsule registry first (with weighted search),
    then EvoMap network for strategy hints.
    Returns a formatted system prompt fragment.
    No EvoMap account required for local capsules.
    """
    parts = []

    # 1) 本地 Capsule 库（加权模糊搜索，无需 EvoMap 网络）
    try:
        from .capsule_registry import get_capsule_registry
        registry = get_capsule_registry()
        local_caps = registry.find_capsule_by_task(task_description, limit=5, min_score=1.0)
        if local_caps:
            parts.append("## 可用技能 Capsule")
            parts.append("以下技能与当前任务匹配。**请立即调用 capsule 工具执行最合适的技能。**")
            parts.append("")
            for i, cap in enumerate(local_caps, 1):
                step_count = len(cap.get_steps())
                step_types = set()
                for s in cap.get_steps():
                    st = s.get("type", "tool")
                    step_types.add(st)
                is_instruction = all(
                    s.get("type", "tool") == "subtask" for s in cap.get_steps()
                )

                parts.append(f"{i}. **{cap.id}** — {cap.description}")
                if cap.task_type:
                    parts.append(f"   类型: {cap.task_type}")
                if cap.tags:
                    parts.append(f"   标签: {', '.join(cap.tags[:5])}")
                src = cap.source or "local"
                mode = "指令型（按步骤指导你操作）" if is_instruction else f"可执行（{step_count}步 {', '.join(step_types)}）"
                parts.append(f"   来源: {src} | 模式: {mode}")
                parts.append(
                    f"   **调用**: capsule(action=\"execute\", capsule_id=\"{cap.id}\", inputs={{\"task\": \"<用户任务>\"}})"
                )
                parts.append("")

            stats = registry.get_stats()
            if stats["total_capsules"] > len(local_caps):
                parts.append(f"(共 {stats['total_capsules']} 个技能可用，capsule(action=\"list\") 查看全部)")
    except Exception as e:
        logger.debug(f"Local capsule registry failed: {e}")

    # 2) EvoMap 进化网络（仅当 ENABLE_EVOMAP=true 且已初始化）
    if not ENABLE_EVOMAP:
        return "\n".join(parts) if parts else ""
    try:
        from .evomap_service import get_evomap_service
        service = get_evomap_service()
        if not service._initialized:
            if parts:
                return "\n".join(parts)
            return ""

        result = await service.resolve_capability(task_description)
        if not result.get("found"):
            if parts:
                return "\n".join(parts)
            return ""

        capsules = result.get("capsules", [])
        genes = result.get("genes", [])

        if capsules:
            parts.append("\n## EvoMap 策略参考 (来自进化网络已验证的策略)")
            for i, cap in enumerate(capsules[:3], 1):
                summary = cap.get("summary", "")
                confidence = cap.get("confidence", 0)
                triggers = ", ".join(cap.get("trigger", [])[:5])
                parts.append(f"{i}. [{confidence:.0%} 置信度] {summary}")
                if triggers:
                    parts.append(f"   触发信号: {triggers}")

        if genes:
            parts.append("\n## EvoMap 基因策略")
            for g in genes[:2]:
                gene_id = g.get("id", "")
                strategy = g.get("strategy", [])
                if strategy:
                    parts.append(f"- {gene_id}: {' -> '.join(strategy[:3])}")

        if parts:
            parts.append("\n(以上策略仅供参考，请根据实际情况选择合适的工具执行)")

        return "\n".join(parts) if parts else ""

    except Exception as e:
        logger.debug(f"EvoMap enhance context failed: {e}")
        return "\n".join(parts) if parts else ""


async def evomap_record_success(
    tool_name: str,
    task_description: str,
    strategy_steps: Optional[list] = None,
):
    if not ENABLE_EVOMAP:
        return
    """
    Record a successful tool execution as a potential Capsule candidate.
    Also records execution stats in the local Capsule registry.
    """
    # 记录本地 Capsule 执行统计
    try:
        from .capsule_registry import get_capsule_registry
        registry = get_capsule_registry()
        caps = registry.find_capsule_by_task(task_description, limit=1)
        if caps:
            registry.record_execution(caps[0].id, success=True)
    except Exception:
        pass

    try:
        from .evomap_service import get_evomap_service, _extract_signals
        service = get_evomap_service()
        if not service._initialized:
            return

        signals = _extract_signals(task_description)
        if not signals:
            return

        await service.publish_capability(
            tool_name=tool_name,
            strategy=strategy_steps or [f"Execute {tool_name} for task"],
            signals=signals,
            summary=f"Auto-captured: {tool_name} successfully handled '{task_description[:60]}'",
            confidence=0.7,
        )
    except Exception as e:
        logger.debug(f"EvoMap record success skipped: {e}")


async def evomap_record_failure(
    tool_name: str,
    task_description: str,
    error: str = "",
):
    """Record a failed execution in local Capsule registry stats."""
    try:
        from .capsule_registry import get_capsule_registry
        registry = get_capsule_registry()
        caps = registry.find_capsule_by_task(task_description, limit=1)
        if caps:
            registry.record_execution(caps[0].id, success=False)
    except Exception:
        pass
