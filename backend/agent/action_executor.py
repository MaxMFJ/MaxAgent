"""
Action Executor — 结构化动作执行引擎
包装原有的 action handler，添加：
1. 前置条件验证
2. 环境快照（pre/post）
3. 结构化结果（ActionResult）
4. 错误分类
5. 观察注入
"""

import logging
import time
from typing import Any, Callable, Coroutine, Dict, Optional

from .action_result_schema import (
    ActionOutcome,
    ActionResult as StructuredActionResult,
    UIObservation,
)
from .error_taxonomy import ClassifiedError, ErrorSeverity, classify_error
from .observation_loop import ObservationLoop, get_observation_loop

logger = logging.getLogger(__name__)

# 动作执行超时默认值（秒）
DEFAULT_TIMEOUT = 120
GUI_TIMEOUT = 30


class ActionExecutor:
    """
    结构化动作执行器。
    不替代 AutonomousAgent 的 handler 分发，而是包装执行流程。

    用法:
        executor = ActionExecutor(observation_loop=...)
        result = await executor.execute(
            action_type="write_file",
            params={"path": "/tmp/test.txt", "content": "hello"},
            handler=self._handle_write_file,
            iteration=5,
        )
        # result 是 StructuredActionResult，包含验证、变更追踪
    """

    def __init__(
        self,
        observation_loop: Optional[ObservationLoop] = None,
    ):
        self._obs_loop = observation_loop or get_observation_loop()
        self._execution_count = 0
        self._total_time_ms = 0

    async def execute(
        self,
        action_type: str,
        params: Dict[str, Any],
        handler: Callable[..., Coroutine[Any, Any, Dict[str, Any]]],
        iteration: int = 0,
        action_id: str = "",
        capture_ui: bool = False,
        observe: bool = True,
    ) -> StructuredActionResult:
        """
        执行单个 action 并返回结构化结果。

        Args:
            action_type: 如 "write_file", "run_shell"
            params:      action 参数
            handler:     原始 handler 函数 (async def handler(params) -> dict)
            iteration:   当前迭代轮次
            action_id:   动作ID
            capture_ui:  是否强制捕获 UI 快照
        """
        start_time = time.time()
        self._execution_count += 1

        # 1. Pre-observe: 环境快照（可选）
        pre_snap = None
        if observe:
            pre_snap = await self._obs_loop.pre_observe(
                iteration=iteration,
                action_type=action_type,
                params=params,
            )

        # 2. 前置条件检查
        precondition_error = self._check_preconditions(action_type, params)
        if precondition_error:
            duration_ms = int((time.time() - start_time) * 1000)
            return StructuredActionResult(
                outcome=ActionOutcome.SKIPPED,
                error=precondition_error,
                tool_name=action_type,
                action_type=action_type,
                duration_ms=duration_ms,
                iteration=iteration,
            )

        # 3. 执行 handler
        raw_result: Optional[Dict[str, Any]] = None
        exec_error: Optional[str] = None
        try:
            raw_result = await handler(params)
        except Exception as e:
            exec_error = str(e)
            logger.warning("Action %s failed with exception: %s", action_type, e)

        duration_ms = int((time.time() - start_time) * 1000)
        self._total_time_ms += duration_ms

        # 4. 构建 StructuredActionResult
        structured = self._build_result(
            action_type=action_type,
            action_id=action_id,
            raw_result=raw_result,
            exec_error=exec_error,
            duration_ms=duration_ms,
            iteration=iteration,
        )

        # 5. Post-observe: 对比环境变化（可选）
        if observe and pre_snap is not None:
            try:
                obs = await self._obs_loop.post_observe(
                    iteration=iteration,
                    action_type=action_type,
                    params=params,
                    result=raw_result or {"success": False, "error": exec_error},
                    pre_snapshot=pre_snap,
                    capture_ui=capture_ui,
                )
                self._obs_loop.enrich_action_result(obs, structured)
            except Exception as e:
                logger.debug("Post-observation failed: %s", e)

        return structured

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_executions": self._execution_count,
            "total_time_ms": self._total_time_ms,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check_preconditions(
        self, action_type: str, params: Dict[str, Any]
    ) -> Optional[ClassifiedError]:
        """检查动作前置条件，返回 ClassifiedError 或 None"""
        import os

        at = action_type.lower()

        # read_file: 文件必须存在
        if at == "read_file":
            path = params.get("path", "")
            if path:
                path = os.path.expanduser(path)
                if not os.path.exists(path):
                    return classify_error(
                        f"文件不存在: {path}",
                        tool_name=action_type,
                        action_type=at,
                    )

        # write_file: 目录必须存在或可创建
        if at == "write_file":
            path = params.get("path", "")
            if path:
                path = os.path.expanduser(path)
                parent = os.path.dirname(path)
                if parent and not os.path.exists(parent):
                    # 尝试创建目录
                    try:
                        os.makedirs(parent, exist_ok=True)
                    except OSError as e:
                        return classify_error(
                            f"无法创建目录 {parent}: {e}",
                            tool_name=action_type,
                            action_type=at,
                        )

        return None

    def _build_result(
        self,
        action_type: str,
        action_id: str,
        raw_result: Optional[Dict[str, Any]],
        exec_error: Optional[str],
        duration_ms: int,
        iteration: int,
    ) -> StructuredActionResult:
        """从原始 handler 结果构建 StructuredActionResult"""
        if exec_error:
            classified = classify_error(
                exec_error,
                tool_name=action_type,
                action_type=action_type,
            )
            return StructuredActionResult(
                outcome=ActionOutcome.FAILED,
                error=classified,
                tool_name=action_type,
                action_type=action_type,
                duration_ms=duration_ms,
                iteration=iteration,
            )

        if raw_result is None:
            return StructuredActionResult(
                outcome=ActionOutcome.FAILED,
                error=classify_error("Handler 返回 None", tool_name=action_type, action_type=action_type),
                tool_name=action_type,
                action_type=action_type,
                duration_ms=duration_ms,
                iteration=iteration,
            )

        success = raw_result.get("success", True)
        error_text = raw_result.get("error")

        if success:
            outcome = ActionOutcome.SUCCESS
            classified_err = None
        else:
            outcome = ActionOutcome.FAILED
            classified_err = classify_error(
                error_text or "Unknown error",
                tool_name=action_type,
                action_type=action_type,
            ) if error_text else None

        return StructuredActionResult(
            outcome=outcome,
            data=raw_result.get("output") or raw_result.get("data"),
            error=classified_err,
            tool_name=action_type,
            action_type=action_type,
            duration_ms=duration_ms,
            iteration=iteration,
        )


# 单例
_executor: Optional[ActionExecutor] = None


def get_action_executor() -> ActionExecutor:
    global _executor
    if _executor is None:
        _executor = ActionExecutor()
    return _executor
