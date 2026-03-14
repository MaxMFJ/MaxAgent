"""
DuckHandlersMixin — Action handlers for Duck delegation, DAG orchestration and call_tool.
Extracted from autonomous_agent.py.
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict

from .action_schema import AgentAction, ActionResult, ActionType, TaskContext
from tools.router import execute_tool

logger = logging.getLogger(__name__)


class DuckHandlersMixin:
    """Mixin providing Duck delegation, DAG orchestration and tool-call handlers."""

    async def _handle_call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """调用已注册工具（screenshot、capsule、terminal 等），优先使用而非 run_shell 猜测命令。"""
        tool_name = params.get("tool_name", "").strip()
        args = params.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        if not tool_name:
            return {"success": False, "error": "call_tool 缺少 tool_name"}

        # 拦截 delegate_duck / delegate_dag（Duck 模式下不允许递归委派）
        if tool_name in ("delegate_duck", "delegate_dag"):
            try:
                from app_state import IS_DUCK_MODE
                if IS_DUCK_MODE:
                    return {"success": False, "error": "Duck 模式下不允许委派任务给其他 Duck"}
            except ImportError:
                pass
            if tool_name == "delegate_duck":
                return await self._handle_delegate_duck(args)
            return await self._handle_delegate_dag(args)

        try:
            result = await execute_tool(tool_name, args)
            out = result.data
            # 保留原始结构化输出；仅在不可序列化时回退为字符串
            if out is not None and not isinstance(out, (str, int, float, bool, dict, list, type(None))):
                out = str(out)
            return {"success": result.success, "output": out, "error": result.error}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}

    async def _handle_delegate_duck(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步委派子任务给 Duck 分身 Agent。
        采用 fire-and-forget 模式：提交任务后立即返回，不阻塞主 Agent。
        Duck 结果通过 _collect_duck_results() 在后续迭代中收集。
        """
        from app_state import IS_DUCK_MODE
        if IS_DUCK_MODE:
            return {"success": False, "error": "Duck 模式下不允许再次委派子任务给其他 Duck"}

        description = params.get("description", "").strip()
        if not description:
            return {"success": False, "error": "delegate_duck 缺少 description"}

        duck_type = params.get("duck_type")
        target_duck_id = params.get("duck_id")
        strategy = params.get("strategy", "single")
        timeout = params.get("timeout", 300)
        task_params = params.get("params", {})

        try:
            from services.duck_task_scheduler import get_task_scheduler, ScheduleStrategy
            from services.duck_protocol import DuckType, TaskStatus

            scheduler = get_task_scheduler()
            await scheduler.initialize()

            dt = None
            if duck_type:
                try:
                    dt = DuckType(duck_type)
                except ValueError:
                    pass

            loop = asyncio.get_event_loop()
            future: asyncio.Future = loop.create_future()

            async def on_result(task):
                if not future.done():
                    future.set_result(task)

            task = await scheduler.submit(
                description=description,
                task_type=params.get("task_type", "general"),
                params=task_params,
                priority=params.get("priority", 0),
                timeout=timeout,
                strategy=strategy,
                target_duck_id=target_duck_id,
                target_duck_type=dt,
                callback=on_result,
            )

            if task.status == TaskStatus.PENDING:
                return {
                    "success": False,
                    "output": None,
                    "error": "No available duck to handle this task. Task queued as PENDING.",
                    "task_id": task.task_id,
                }

            self._pending_duck_futures[task.task_id] = future
            self._pending_duck_descriptions[task.task_id] = description[:100]
            logger.info(f"Duck task {task.task_id} dispatched asynchronously (pending: {len(self._pending_duck_futures)})")

            return {
                "success": True,
                "output": f"子任务已异步委派给 Duck（task_id: {task.task_id}）。Duck 正在后台执行，你可以继续执行其他操作。完成后系统会自动通知结果。",
                "task_id": task.task_id,
                "duck_id": task.assigned_duck_id,
                "async_dispatched": True,
            }

        except ImportError:
            return {"success": False, "error": "Duck task scheduler not available"}
        except Exception as e:
            return {"success": False, "error": f"delegate_duck error: {e}"}

    async def _handle_delegate_dag(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建多Agent协作DAG：自动分解为多个子任务节点，按依赖顺序执行，
        自动创建群聊供所有Agent实时汇报进度。
        """
        from app_state import IS_DUCK_MODE
        if IS_DUCK_MODE:
            return {"success": False, "error": "Duck 模式下不允许创建 DAG 协作任务"}

        description = params.get("description", "").strip()
        nodes_raw = params.get("nodes", [])
        if not description or not nodes_raw:
            return {"success": False, "error": "delegate_dag 需要 description 和 nodes 参数"}

        try:
            from services.duck_task_dag import DAGTaskOrchestrator, DAGNode
            from services.duck_protocol import DuckType

            dag_nodes = []
            for raw in nodes_raw:
                node_id = raw.get("node_id", "").strip()
                node_desc = raw.get("description", "").strip()
                if not node_id or not node_desc:
                    return {"success": False, "error": "每个 node 必须包含 node_id 和 description"}

                duck_type = None
                if raw.get("task_type"):
                    try:
                        duck_type = DuckType(raw["task_type"])
                    except ValueError:
                        pass

                dag_nodes.append(DAGNode(
                    node_id=node_id,
                    description=node_desc,
                    task_type=raw.get("task_type", "general"),
                    params=raw.get("params", {}),
                    duck_type=duck_type,
                    duck_id=raw.get("duck_id"),
                    timeout=raw.get("timeout", 600),
                    depends_on=raw.get("depends_on", []),
                    input_mapping=raw.get("input_mapping", {}),
                ))

            orchestrator = DAGTaskOrchestrator.get_instance()

            loop = asyncio.get_event_loop()
            future: asyncio.Future = loop.create_future()

            async def _dag_callback(execution):
                if not future.done():
                    future.set_result(execution)

            session_id = getattr(self, '_current_session_id', '') or ''
            execution = orchestrator.create_dag(
                description=description,
                nodes=dag_nodes,
                callback=_dag_callback,
                session_id=session_id,
            )

            self._pending_dag_futures[execution.dag_id] = future
            self._pending_dag_descriptions[execution.dag_id] = description[:100]

            asyncio.create_task(orchestrator.execute(execution.dag_id))
            logger.info(f"DAG {execution.dag_id} created with {len(dag_nodes)} nodes, executing asynchronously")

            return {
                "success": True,
                "output": (
                    f"多Agent协作 DAG 已创建并开始执行（dag_id: {execution.dag_id}，共 {len(dag_nodes)} 个子任务）。"
                    f"群聊已自动创建，各Agent将在群聊中实时汇报进度。DAG 完成后系统会自动通知结果。"
                ),
                "dag_id": execution.dag_id,
                "node_count": len(dag_nodes),
                "group_id": execution.group_id,
                "async_dispatched": True,
            }

        except ValueError as e:
            return {"success": False, "error": str(e)}
        except ImportError:
            return {"success": False, "error": "DAG task orchestrator not available"}
        except Exception as e:
            return {"success": False, "error": f"delegate_dag error: {e}"}

    async def _collect_duck_results(self, context: TaskContext) -> AsyncGenerator[Dict[str, Any], None]:
        """
        非阻塞地收集已完成的并行 Duck 任务结果。
        在每次迭代开始时调用，将已完成的 Duck 结果注入主 Agent 上下文。
        """
        if not self._pending_duck_futures:
            return

        from services.duck_protocol import TaskStatus

        completed_ids = []
        for task_id, future in self._pending_duck_futures.items():
            if future.done():
                completed_ids.append(task_id)

        for task_id in completed_ids:
            future = self._pending_duck_futures.pop(task_id)
            desc = self._pending_duck_descriptions.pop(task_id, "")
            try:
                completed_task = future.result()
                success = completed_task.status == TaskStatus.COMPLETED
                output = completed_task.output
                error = completed_task.error
                duck_id = completed_task.assigned_duck_id

                duck_action = AgentAction(
                    action_type=ActionType.DELEGATE_DUCK,
                    params={"description": desc, "task_id": task_id},
                    reasoning=f"异步 Duck 任务完成（{'成功' if success else '失败'}）",
                )
                duck_result = ActionResult(
                    action_id=duck_action.action_id,
                    success=success,
                    output=output,
                    error=error,
                )
                context.add_action_log(duck_action, duck_result)

                status_text = "✅ 成功" if success else "❌ 失败"
                hint = f"【Duck 异步任务完成】{status_text}：{desc}"
                if output:
                    hint += f"\n结果：{str(output)[:300]}"
                if error:
                    hint += f"\n错误：{error[:200]}"
                existing_hint = self._mid_reflection_hint or ""
                self._mid_reflection_hint = f"{existing_hint}\n{hint}".strip()

                yield {
                    "type": "duck_result_collected",
                    "task_id": task_id,
                    "duck_id": duck_id,
                    "success": success,
                    "description": desc,
                    "output": str(output)[:500] if output else None,
                    "error": error,
                    "pending_count": len(self._pending_duck_futures),
                }
                logger.info(f"Duck async result collected: task={task_id} success={success} pending={len(self._pending_duck_futures)}")
            except Exception as e:
                logger.warning(f"Failed to collect duck result for {task_id}: {e}")
                self._pending_duck_descriptions.pop(task_id, None)

    async def _collect_dag_results(self, context: TaskContext) -> AsyncGenerator[Dict[str, Any], None]:
        """
        非阻塞地收集已完成的 DAG 执行结果。
        在每次迭代开始时调用，将已完成的 DAG 结果注入主 Agent 上下文。
        """
        if not self._pending_dag_futures:
            return

        completed_ids = []
        for dag_id, future in self._pending_dag_futures.items():
            if future.done():
                completed_ids.append(dag_id)

        for dag_id in completed_ids:
            future = self._pending_dag_futures.pop(dag_id)
            desc = self._pending_dag_descriptions.pop(dag_id, "")
            try:
                execution = future.result()
                success = execution.status == "completed"

                dag_action = AgentAction(
                    action_type=ActionType.DELEGATE_DAG,
                    params={"description": desc, "dag_id": dag_id},
                    reasoning=f"DAG 多Agent协作完成（{'成功' if success else '失败'}）",
                )
                dag_result = ActionResult(
                    action_id=dag_action.action_id,
                    success=success,
                    output=execution.output,
                    error=execution.error,
                )
                context.add_action_log(dag_action, dag_result)

                status_text = "✅ 成功" if success else "❌ 失败"
                node_summary = ", ".join(
                    f"{n.node_id}({'✅' if n.status.value == 'completed' else '❌'})"
                    for n in execution.nodes.values()
                )
                hint = f"【DAG 多Agent协作完成】{status_text}：{desc}\n节点状态：{node_summary}"
                if execution.output:
                    hint += f"\n最终结果：{str(execution.output)[:500]}"
                if execution.error:
                    hint += f"\n错误：{execution.error[:200]}"
                existing_hint = self._mid_reflection_hint or ""
                self._mid_reflection_hint = f"{existing_hint}\n{hint}".strip()

                yield {
                    "type": "dag_result_collected",
                    "dag_id": dag_id,
                    "success": success,
                    "description": desc,
                    "status": execution.status,
                    "output": str(execution.output)[:500] if execution.output else None,
                    "error": execution.error,
                    "group_id": execution.group_id,
                    "pending_count": len(self._pending_dag_futures),
                }
                logger.info(f"DAG result collected: dag={dag_id} status={execution.status} pending={len(self._pending_dag_futures)}")
            except Exception as e:
                logger.warning(f"Failed to collect DAG result for {dag_id}: {e}")
                self._pending_dag_descriptions.pop(dag_id, None)
