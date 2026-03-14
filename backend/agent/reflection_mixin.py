"""
ReflectionMixin — Post-task reflection using local LLM.
Extracted from autonomous_agent.py.
"""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict

from .action_schema import TaskContext
from .local_llm_manager import get_local_llm_manager, LocalLLMProvider
from .llm_utils import extract_text_from_content

logger = logging.getLogger(__name__)


class ReflectionMixin:
    """Mixin providing post-task reflection capabilities for AutonomousAgent."""

    async def _run_reflection(
        self, context: TaskContext
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run reflection on completed task using local LLM (Ollama or LM Studio)"""
        local_llm_manager = get_local_llm_manager()
        client, config = await local_llm_manager.get_client()

        if client is None or config.provider == LocalLLMProvider.NONE:
            logger.warning("No local LLM service available for reflection")
            yield {
                "type": "reflect_result",
                "error": "反思跳过: 本地模型服务未运行 (Ollama/LM Studio)",
            }
            return

        logger.info(f"Using {config.provider.value} ({config.model}) for reflection")

        reflection_prompt = f"""分析以下任务执行过程，提取经验和改进建议：

任务: {context.task_description}

执行日志:
{json.dumps([log.to_dict() for log in context.action_logs[-20:]], ensure_ascii=False, indent=2)}

请分析：
1. 执行是否高效？有哪些可以优化的地方？
2. 是否有失败的步骤？原因是什么？
3. 提取可复用的策略或模式
4. 给出改进建议

以 JSON 格式输出：
{{
  "efficiency_score": 1-10,
  "successes": ["成功点1", "成功点2"],
  "failures": ["失败点1"],
  "strategies": ["策略1", "策略2"],
  "improvements": ["改进建议1", "改进建议2"]
}}"""

        try:
            from core.timeout_policy import get_timeout_policy
        except ImportError:
            get_timeout_policy = None

        try:
            reflect_coro = client.chat.completions.create(
                model=config.model,
                messages=[{"role": "user", "content": reflection_prompt}],
                temperature=0.3,
            )
            if get_timeout_policy is not None:
                response = await get_timeout_policy().with_llm_timeout(reflect_coro, timeout=60.0)
            else:
                response = await asyncio.wait_for(reflect_coro, timeout=60.0)

            raw = getattr(response.choices[0].message, "content", None)
            content = extract_text_from_content(raw)
            yield {
                "type": "reflect_result",
                "reflection": content,
                "provider": config.provider.value,
                "model": config.model,
            }

        except asyncio.TimeoutError:
            logger.warning(f"Reflection timed out ({config.provider.value})")
            yield {
                "type": "reflect_result",
                "error": f"反思超时: {config.provider.value} 响应过慢",
            }
        except Exception as e:
            logger.error(f"Reflection error: {e}")
            yield {"type": "reflect_result", "error": str(e)}
