"""
Local Duck Worker — 本地 Duck 运行时

在同一进程中以 asyncio 任务运行的 Duck Agent。
每个 Local Duck 有独立的任务队列，通过内存直接与调度器通信，
无需 WebSocket。
"""
from __future__ import annotations
import asyncio
import logging
import os
import platform
import socket
import time
import uuid
from typing import Any, Dict, Optional

from services.duck_protocol import (
    DuckInfo,
    DuckResultPayload,
    DuckStatus,
    DuckTask,
    DuckTaskPayload,
    DuckType,
    TaskStatus,
)
from services.duck_registry import DuckRegistry

logger = logging.getLogger(__name__)


class LocalDuckWorker:
    """单个本地 Duck 工作线程（asyncio 协程）"""

    def __init__(
        self,
        duck_id: str,
        name: str,
        duck_type: DuckType = DuckType.GENERAL,
        skills: list[str] | None = None,
        llm_api_key: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_provider_ref: Optional[str] = None,
    ):
        self.duck_id = duck_id
        self.name = name
        self.duck_type = duck_type
        self.skills = skills or []
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model
        self.llm_provider_ref = llm_provider_ref

        self._task_queue: asyncio.Queue[DuckTaskPayload] = asyncio.Queue()
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._agent = None  # 独立的 AutonomousAgent 实例（不再共享全局）

    # ─── 生命周期 ────────────────────────────────────

    async def start(self):
        """启动工作协程并注册到 Registry"""
        if self._running:
            return

        registry = DuckRegistry.get_instance()
        await registry.initialize()

        info = DuckInfo(
            duck_id=self.duck_id,
            name=self.name,
            duck_type=self.duck_type,
            status=DuckStatus.ONLINE,
            skills=self.skills,
            hostname=socket.gethostname(),
            platform=platform.system().lower(),
            is_local=True,
            llm_api_key=self.llm_api_key,
            llm_base_url=self.llm_base_url,
            llm_model=self.llm_model,
            llm_provider_ref=self.llm_provider_ref,
        )
        await registry.register(info)

        self._running = True
        self._worker_task = asyncio.create_task(self._run_loop())
        logger.info(f"Local Duck started: {self.duck_id} ({self.name})")

    async def stop(self):
        """停止工作协程并从 Registry 注销"""
        if not self._running:
            return

        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        registry = DuckRegistry.get_instance()
        await registry.set_status(self.duck_id, DuckStatus.OFFLINE)
        logger.info(f"Local Duck stopped: {self.duck_id}")

    # ─── 任务接收（由调度器直接调用） ────────────────

    async def enqueue_task(self, payload: DuckTaskPayload):
        """调度器直接向本地 Duck 投递任务"""
        await self._task_queue.put(payload)

    # ─── 主循环 ──────────────────────────────────────

    async def _run_loop(self):
        """持续从队列取任务并执行"""
        while self._running:
            try:
                payload = await asyncio.wait_for(
                    self._task_queue.get(), timeout=5.0
                )
            except asyncio.TimeoutError:
                # 定期更新心跳
                registry = DuckRegistry.get_instance()
                await registry.heartbeat(self.duck_id)
                continue
            except asyncio.CancelledError:
                break

            await self._execute_task(payload)

    async def _execute_task(self, payload: DuckTaskPayload):
        """执行单个任务，向监控面板广播实时步骤，并回传结果"""
        from services.duck_task_scheduler import get_task_scheduler
        from ws_handler import broadcast_monitor_event

        registry = DuckRegistry.get_instance()
        await registry.set_current_task(self.duck_id, payload.task_id)

        desc_preview = (payload.description or "")[:80]
        logger.info(f"[Local Duck] {self.duck_id} executing task {payload.task_id}: {desc_preview}...")

        # 获取委派来源 session（用于广播到正确的监控客户端）
        scheduler = get_task_scheduler()
        source_session = scheduler._task_sessions.get(
            payload.task_id, f"duck_{self.duck_id}"
        )

        start_time = time.time()
        success = False
        output: Any = None
        error: Optional[str] = None

        # 广播任务开始事件（带 Duck 身份）
        await broadcast_monitor_event(
            session_id=source_session,
            task_id=payload.task_id,
            event={
                "type": "task_start",
                "task": payload.description,
                "task_id": payload.task_id,
                "duck_name": self.name,
                "duck_type": self.duck_type.value,
            },
            task_type="duck",
            worker_type="local_duck",
            worker_id=self.duck_id,
        )

        # 在 DAG 群聊中发送「Duck 已接受并开始执行」通知
        try:
            from services.duck_task_dag import notify_duck_task_started
            await notify_duck_task_started(payload.task_id, self.duck_id, self.name)
        except Exception:
            pass  # 非 DAG 任务或群聊不存在时静默跳过

        try:
            output = await self._do_work_with_monitoring(payload, source_session)
            success = True
        except Exception as e:
            error = str(e)
            logger.error(f"Local Duck {self.duck_id} task failed: {e}")
            # 广播任务失败事件
            await broadcast_monitor_event(
                session_id=source_session,
                task_id=payload.task_id,
                event={
                    "type": "task_complete",
                    "task_id": payload.task_id,
                    "success": False,
                    "summary": f"执行失败: {error[:200]}",
                },
                task_type="duck",
                worker_type="local_duck",
                worker_id=self.duck_id,
            )

        duration = time.time() - start_time

        result = DuckResultPayload(
            task_id=payload.task_id,
            success=success,
            output=output,
            error=error,
            duration=duration,
        )

        await scheduler.handle_result(self.duck_id, result)

    def _create_duck_llm_client(self) -> Optional[Any]:
        """若分身配置了独立 LLM，创建 LLMClient。优先使用 provider_ref 动态解析，否则回退到静态字段。"""
        api_key = self.llm_api_key
        base_url = self.llm_base_url
        model = self.llm_model

        # 方案B: 优先通过 provider_ref 动态解析（跟随主配置变更）
        if getattr(self, 'llm_provider_ref', None):
            try:
                from config.llm_config import resolve_provider_config
                resolved = resolve_provider_config(self.llm_provider_ref)
                if resolved:
                    api_key = resolved["api_key"]
                    base_url = resolved["base_url"]
                    model = resolved["model"]
                    logger.info("Duck %s LLM resolved via provider_ref=%s -> model=%s",
                                self.duck_id, self.llm_provider_ref, model)
                else:
                    logger.warning("Duck %s provider_ref=%s 解析失败，回退到静态字段",
                                   self.duck_id, self.llm_provider_ref)
            except Exception as e:
                logger.warning("Duck %s provider_ref resolve error: %s", self.duck_id, e)

        if not all([api_key, base_url, model]):
            return None
        try:
            from agent.llm_client import LLMClient, LLMConfig
            config = LLMConfig(
                provider="openai",
                api_key=api_key,
                base_url=base_url,
                model=model,
            )
            return LLMClient(config)
        except Exception as e:
            logger.warning("Duck LLM client creation failed: %s", e)
            return None

    def _create_independent_agent(self, duck_llm=None):
        """为 Duck 创建独立的 AutonomousAgent 实例，不共享全局 agent 状态。
        v3.8: 优先通过 AgentRegistry + AgentFactory 创建，保留后向兼容。
        v3.8.1: isolated_context=True — 隔离主 Agent 会话上下文，Duck 只看到任务描述。
        """
        from app_state import get_autonomous_agent

        main_agent = get_autonomous_agent()
        if main_agent is None:
            raise RuntimeError("Main AutonomousAgent not initialized")

        llm_client = duck_llm if duck_llm is not None else main_agent.remote_llm

        # v3.8: 尝试通过 AgentRegistry 获取该 Duck 类型的 AgentSpec
        try:
            from agent.agent_registry import AgentFactory, get_agent_registry
            registry = get_agent_registry()
            spec = registry.get(self.duck_type.value if hasattr(self.duck_type, 'value') else str(self.duck_type))
            if spec:
                agent = AgentFactory.create(
                    spec=spec,
                    llm_client=llm_client,
                    reflect_llm=main_agent.reflect_llm,
                    local_llm=main_agent.local_llm,
                    runtime_adapter=main_agent.runtime_adapter,
                    isolated_context=True,
                )
                logger.info("Duck %s: created via AgentFactory (type=%s, isolated=True, llm=%s)",
                            self.duck_id, spec.agent_type,
                            llm_client.config.model if hasattr(llm_client, 'config') else 'main')
                return agent
        except Exception as e:
            logger.debug("AgentFactory fallback: %s", e)

        # 后向兼容：直接创建
        from agent.autonomous_agent import AutonomousAgent
        agent = AutonomousAgent(
            llm_client=llm_client,
            local_llm_client=main_agent.local_llm,
            reflect_llm=main_agent.reflect_llm,
            runtime_adapter=main_agent.runtime_adapter,
            max_iterations=main_agent.max_iterations,
            enable_reflection=main_agent.enable_reflection,
            enable_model_selection=main_agent.enable_model_selection,
            enable_adaptive_stop=main_agent.enable_adaptive_stop,
            isolated_context=True,
        )
        logger.info("Duck %s: created independent AutonomousAgent (isolated=True, llm=%s)",
                     self.duck_id, llm_client.config.model if hasattr(llm_client, 'config') else 'main')
        return agent

    @staticmethod
    def _desc_has_explicit_output_path(description: str) -> bool:
        """检测任务描述中是否包含明确的输出路径（如 ~/Desktop/xxx.md, /Users/xxx/xxx.html）。"""
        import re
        # 匹配 "输出到/保存到/写入到 + 路径" 或描述中直接包含绝对路径的输出指示
        explicit_patterns = [
            r'(?:输出|保存|写入|生成|创建)\s*(?:到|至|为)\s*[`"\']*(/[^\s`"\'，,]+|~/[^\s`"\'，,]+)',
            r'(?:output|save|write)\s+(?:to|at|as)\s+[`"\']*(/[^\s`"\'，,]+|~/[^\s`"\'，,]+)',
        ]
        for pat in explicit_patterns:
            if re.search(pat, description, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def _desc_has_modify_existing_intent(description: str) -> bool:
        """检测任务是否意在修改现有文件（而非创建新文件）。"""
        import re
        modify_patterns = [
            r'(?:修改|改造|重新设计|重构|优化|更新|替换)\s*(?:现有|已有|桌面上的|原始)',
            r'(?:modify|update|refactor|redesign)\s+(?:existing|the|current)',
            r'(?:修改|改造)\s+[^\s]+\.(?:html|css|js|py)',
        ]
        for pat in modify_patterns:
            if re.search(pat, description, re.IGNORECASE):
                return True
        return False

    def _build_isolated_description(self, payload: DuckTaskPayload, sandbox=None) -> str:
        """
        v3.8.2: 构建隔离的任务描述 — 只包含任务本身 + 必要文件引用 + 工作目录提示。

        智能路径策略:
        1. 若任务描述包含明确输出路径（如 "输出到 ~/Desktop/xxx.md"），优先使用该路径
        2. 若任务是修改现有文件，允许读取和写回原始路径
        3. 仅当任务没有明确输出路径时，才建议使用沙箱工作目录
        """
        import re

        # 过滤主 Agent 系统提示中注入的桌面路径提示，不应传递给 Duck Agent
        raw_desc = payload.description or ""
        clean_desc = re.sub(
            r'[\n\s]*【重要】保存文件时必须使用实际路径[：:][^\n。]*[。\n]?',
            '',
            raw_desc,
        ).strip()

        parts = [clean_desc]

        # 附加任务参数中的文件引用（方案 A+D：大文件用智能摘要+缓存，小文件直接给路径）
        file_refs = []
        if payload.params:
            # 先扫描特定键
            for key in ("file_path", "file_paths", "input_file", "output_file", "source_file", "target_path"):
                val = payload.params.get(key)
                if val:
                    if isinstance(val, list):
                        file_refs.extend(str(v) for v in val)
                    else:
                        file_refs.append(str(val))
            # 再扫描所有字符串/列表参数值，提取其中的绝对路径（用于 input_mapping 传递的上游输出）
            if not file_refs:
                for key, val in payload.params.items():
                    if key in ("description", "task_type"):
                        continue
                    text = val if isinstance(val, str) else (
                        "\n".join(str(v) for v in val) if isinstance(val, list) else ""
                    )
                    if not text:
                        continue
                    for m in re.finditer(
                        r'(/(?:Users|home|tmp|var|opt)/[^\s"\'\\,，；；、\]\)>\n]+\.(?:md|html?|txt|json|pdf|py|js|ts|css|yaml|yml|csv))',
                        text, re.IGNORECASE,
                    ):
                        p = m.group(1).rstrip("。.）)")
                        if os.path.exists(p) and p not in file_refs:
                            file_refs.append(p)
        # 从描述中解析文件路径（多种格式）
        if not file_refs and payload.description:
            # 格式1: 【用户附带文件】列表格式 "- /path" 或 "• ~/path"
            for m in re.finditer(r"[-•]\s*(/[^\s\n]+|~/[^\s\n]+)", payload.description):
                p = os.path.expanduser(m.group(1).strip())
                if os.path.exists(p) and p not in file_refs:
                    file_refs.append(p)
            # 格式2: 描述中内嵌的绝对路径（如 "修改 /Users/xxx/file.html"）
            if not file_refs:
                for m in re.finditer(r'(/(?:Users|home|tmp|var|opt)/[^\s"\'\\,，；；、\]\)>\n]+)', payload.description):
                    p = m.group(1).rstrip("。.）)")
                    if os.path.exists(p) and p not in file_refs:
                        file_refs.append(p)
        if file_refs:
            parts.append(f"\n【相关文件路径】{', '.join(file_refs)}")
            try:
                from services.file_structure_service import build_file_refs_with_summary
                summary_block = build_file_refs_with_summary(file_refs)
                if summary_block:
                    parts.append(f"\n【文件结构摘要】（大文件已压缩，可分段 read_file 按需读取详情）\n{summary_block}")
            except Exception as _e:
                logger.warning(f"File structure summary failed: {_e}")

        desc = clean_desc
        has_explicit_path = self._desc_has_explicit_output_path(desc)
        has_modify_intent = self._desc_has_modify_existing_intent(desc)

        if sandbox:
            if has_explicit_path:
                # 任务描述中有明确输出路径，尊重用户意图
                parts.append(
                    f"\n【工作目录】沙箱工作区: {sandbox.workspace_dir}"
                    f"\n⚠️ 注意：任务描述中已指定了输出路径，请将文件保存到任务描述中指定的路径，而非沙箱。"
                    f"\n如需创建临时文件或中间产物，可使用沙箱目录。"
                )
            elif has_modify_intent:
                # 任务是修改现有文件，允许读写原始路径
                parts.append(
                    f"\n【工作目录】沙箱工作区: {sandbox.workspace_dir}"
                    f"\n⚠️ 注意：此任务需要修改现有文件。你可以直接读取和修改原始文件路径。"
                    f"\n完成后将修改后的文件保存回原始路径。沙箱仅用于临时文件。"
                )
            else:
                # 默认行为：保存到沙箱
                parts.append(f"\n【工作目录】请将产出文件保存到: {sandbox.workspace_dir}")

        return "\n".join(parts)

    def _build_retry_description(self, payload: DuckTaskPayload, sandbox, failure_summary: str, attempt: int) -> str:
        """
        v3.8.2: 重试上下文重建 — 创建全新上下文，注入前次失败摘要。
        不追加到旧 context，而是从零开始，附带失败经验。
        保留与 _build_isolated_description 一致的智能路径策略。
        """
        parts = [
            f"【第 {attempt} 次尝试 · 强制执行模式】",
            f"上一次执行未成功完成。失败摘要：{failure_summary[:200]}",
            "",
            "请注意以下要求：",
            "1. 必须实际执行任务，不要只描述或规划。",
            "2. 使用 write_file、run_shell、create_and_run_script 等工具动作。",
            "3. 禁止只输出文字分析。每一步都必须是可执行的 JSON 动作。",
            "",
            f"原始任务：{payload.description}",
        ]

        import re as _re2
        desc = _re2.sub(
            r'[\n\s]*【重要】保存文件时必须使用实际路径[：:][^\n。]*[。\n]?', '', payload.description or ''
        ).strip()
        has_explicit_path = self._desc_has_explicit_output_path(desc)
        has_modify_intent = self._desc_has_modify_existing_intent(desc)

        if sandbox:
            if has_explicit_path:
                parts.append(f"\n【工作目录】沙箱: {sandbox.workspace_dir}")
                parts.append("⚠️ 任务描述中已指定输出路径，请保存到任务指定的路径而非沙箱。")
            elif has_modify_intent:
                parts.append(f"\n【工作目录】沙箱: {sandbox.workspace_dir}")
                parts.append("⚠️ 此任务需修改现有文件，可直接读写原始路径。")
            else:
                parts.append(f"\n【工作目录】{sandbox.workspace_dir}")

        return "\n".join(parts)

    @staticmethod
    def _check_output_is_plan_not_result(output: Any) -> bool:
        """
        检测 agent.run() 的返回结果是否是未执行的 action plan，而非真实完成结果。
        当 LLM 输出 action plan JSON 但未实际执行时，summary 会包含这些 JSON 字符串。
        也检测自然语言形式的计划描述（未真正执行工具）。
        Returns True → 任务未真正完成，需标记失败。
        """
        if output is None:
            return True
        if not isinstance(output, str):
            return False
        stripped = output.strip()
        # 默认返回值，表明 task_complete chunk 从未出现
        if stripped in ("", "任务已结束"):
            return True

        import re

        # ── 正向完成信号检测：如果包含明确的完成/成功标志，直接视为已完成 ──
        completion_signals = [
            r'(?:✓|✅|√)',                                       # 完成标记符号
            r'(?:已保存|已创建|已生成|已写入|已完成)',             # 明确的完成动词（连续）
            r'(?:已经|成功)(?:保存|创建|生成|写入|完成)',          # "已经/成功" + 动词（分离形式）
            r'(?:已将|已把).{0,15}(?:保存|写入|创建)',            # "已将/已把...保存/写入"
            r'(?:saved|written|created|generated)\s+(?:to|at)',  # 英文完成标记
            r'(?:文件|file)\s*(?:大小|size)',                     # 文件大小信息=实际产出
            r'(?:分辨率|resolution)',                             # 图片产出信息
            r'macagent_workspace/ducks/[^\s]+/workspace/',       # 包含沙箱路径 = 已写入工作区
            r'Written to:',                                       # write_file 成功标志
        ]
        completion_score = sum(1 for p in completion_signals if re.search(p, stripped, re.IGNORECASE))
        if completion_score >= 1:
            return False  # 有明确完成信号，不是计划

        # 检查 output 是否包含 action plan JSON 结构
        # 用正则直接提取 action_type 的值（兼容嵌套 JSON）
        if '"action_type"' in stripped and '"reasoning"' in stripped:
            for m in re.finditer(r'"action_type"\s*:\s*"([^"]+)"', stripped):
                atype = m.group(1)
                if atype and atype != "finish":
                    # 找到非 finish 的 action plan → 任务未完成
                    return True
        # 检测自然语言形式的计划描述（LLM 只描述了要做什么，没实际执行）
        plan_indicators = [
            r'(?:任务|执行)\s*(?:分析|策略|规划|计划)',
            r'(?:我来|接下来|首先).*(?:分析|规划|创建|编写)',
            r'(?:需要|应该|将会|可以).*(?:创建|编写|实现|开发)',
        ]
        plan_score = sum(1 for p in plan_indicators if re.search(p, stripped))
        # 如果输出很短（<500字符）且包含多个计划指标词，很可能只是描述
        if len(stripped) < 500 and plan_score >= 2:
            return True
        return False

    async def _do_work_with_monitoring(self, payload: DuckTaskPayload, source_session: str) -> Any:
        """
        流式执行任务并将每一步广播到监控面板（带 Duck 身份标识）。
        替代原 _do_work，使 Duck 执行过程在"AI 监控中心"实时可见，包含完整 action 链路。
        """
        from ws_handler import broadcast_monitor_event
        from app_state import set_duck_context

        # 获取最新 Duck 配置（用户可能已更新 llm_config）
        registry = DuckRegistry.get_instance()
        duck = await registry.get(self.duck_id)
        if duck:
            self.llm_api_key = duck.llm_api_key
            self.llm_base_url = duck.llm_base_url
            self.llm_model = duck.llm_model
            self.llm_provider_ref = duck.llm_provider_ref

        duck_llm = self._create_duck_llm_client()
        if duck_llm is None:
            logger.warning("Duck %s: duck_llm is None, will use main agent's LLM (provider_ref=%s)",
                           self.duck_id, getattr(self, 'llm_provider_ref', None))

        # 为每个任务创建独立的 AutonomousAgent 实例（不共享全局 agent，避免并发竞争）
        agent = self._create_independent_agent(duck_llm)

        # v3.8: 为 Duck 任务创建隔离沙箱
        # 使用任务描述的前 15 个非空字符作为可读标签（中英文均可）
        _sandbox = None
        try:
            from services.duck_sandbox import get_duck_sandbox
            import re as _re
            _raw_desc = (payload.original_description or payload.description or "").strip()
            _label_text = _re.sub(r'\s+', '', _raw_desc)[:15]  # 去空白后取前15字符
            _sandbox_mgr = get_duck_sandbox()
            _sandbox = _sandbox_mgr.create_sandbox(
                self.duck_id, payload.task_id[:8], label=_label_text
            )
        except Exception as _sb_err:
            logger.debug(f"Sandbox creation skipped: {_sb_err}")

        duck_ctx = {
            "name": self.name,
            "duck_type": self.duck_type.value,
            "skills": self.skills,
        }
        if _sandbox:
            duck_ctx["sandbox_dir"] = _sandbox.workspace_dir
        set_duck_context(duck_ctx)

        # v3.8.1: 构建隔离上下文 —— Duck 只收到任务描述 + 必要文件引用，不含主 Agent 会话历史
        isolated_desc = self._build_isolated_description(payload, _sandbox)

        # 使用 task_id 构建隔离的 duck session，避免与主 Agent session 状态混用
        duck_session = f"duck_{self.duck_id}_{payload.task_id[:6]}"

        # 活跃时间追踪（每个 chunk 到来时更新），用于惰性超时检测
        last_active: list = [time.time()]
        # v3.8.2: 相位感知超时 — 监听 Duck 是否因工作导致超时
        # 若 Duck 正在工作（LLM 处理/工具执行），给予更长时间；仅当空闲且无下一步才判断失败
        duck_phase: list = ["idle"]  # "idle" | "llm_waiting" | "tool_executing"
        IDLE_INACTIVITY_TIMEOUT = 90     # 空闲：90s 无任何 chunk → 真正卡死
        LLM_INACTIVITY_TIMEOUT = 120     # LLM 处理中：2 分钟（减少卡死等待时间）
        TOOL_INACTIVITY_TIMEOUT = 180    # 工具执行中：3 分钟（如 create_and_run_script 生成大文件）

        # 获取 scheduler 引用，用于更新任务活跃时间
        from services.duck_task_scheduler import get_task_scheduler
        _scheduler = get_task_scheduler()

        # 工具调用计数器，用于向 Chat 发送关键里程碑通知
        _tool_call_count: list = [0]

        async def _stream_run(description: str) -> str:
            """流式迭代 run_autonomous，广播每个 chunk，返回最终 summary"""
            summary = ""
            async for chunk in agent.run_autonomous(description, session_id=duck_session):
                last_active[0] = time.time()  # 有进展，更新活跃时间
                _scheduler.update_task_activity(payload.task_id)  # 同步更新调度器层面的活跃时间

                # v3.8.2: 相位感知 — 根据 chunk 类型更新 duck_phase（工作导致超时则延长时间）
                chunk_type = chunk.get("type", "")
                if chunk_type == "llm_request_start":
                    duck_phase[0] = "llm_waiting"
                elif chunk_type == "llm_request_end":
                    duck_phase[0] = "idle"
                elif chunk_type in ("tool_call",):
                    duck_phase[0] = "tool_executing"
                    # 向 Chat 发送关键工具调用进度
                    _tool_call_count[0] += 1
                    tool_name = chunk.get("tool_name", chunk.get("action_type", ""))
                    if tool_name and _tool_call_count[0] <= 10:  # 最多推送10条进度
                        await _scheduler._notify_session_duck_progress(
                            source_session, payload.task_id,
                            f"⚙️ Duck 正在执行：{tool_name}（第 {_tool_call_count[0]} 步）"
                        )
                elif chunk_type == "tool_result":
                    duck_phase[0] = "idle"  # 工具返回后可能马上发起下一轮 LLM
                elif chunk_type == "chunk":
                    # 流式内容：若在 LLM 输出中则视为 llm_waiting，避免长生成被误判卡死
                    if duck_phase[0] == "llm_waiting":
                        pass  # 保持
                    else:
                        duck_phase[0] = "llm_waiting"  # 收到内容即视为 LLM 在工作

                # 实时广播执行步骤到全局监控面板
                await broadcast_monitor_event(
                    session_id=source_session,
                    task_id=payload.task_id,
                    event=chunk,
                    task_type="duck",
                    worker_type="local_duck",
                    worker_id=self.duck_id,
                )
                if chunk_type == "task_complete":
                    summary = chunk.get("summary", "") or ""
                    break
                if chunk_type == "task_stopped":
                    raise RuntimeError(chunk.get("message", "任务被停止"))
                if chunk_type == "error":
                    raise RuntimeError(chunk.get("error", "任务执行错误"))
            return summary or "任务已结束"

        async def _run_smart(description: str, hard_timeout: float) -> str:
            """
            v3.8.2 智能相位感知超时执行：
            - 每 20s 检查 Duck 是否仍活跃（有 chunk 产出）
            - 根据 Duck 当前相位使用不同超时阈值：
              * idle: 90s （真正无事可做）
              * llm_waiting: 300s （LLM 处理大上下文可能很慢）
              * tool_executing: 180s （工具执行如生成大文件）
            - 若超过 hard_timeout 硬上限 → 取消任务
            只要 Duck 持续工作，就不会被误杀。
            """
            last_active[0] = time.time()
            hard_deadline = time.time() + hard_timeout
            stream_task = asyncio.ensure_future(_stream_run(description))
            try:
                while True:
                    done, _ = await asyncio.wait({stream_task}, timeout=20)
                    if stream_task in done:
                        try:
                            return stream_task.result()
                        except asyncio.CancelledError:
                            raise RuntimeError("任务被外部取消")
                    now = time.time()
                    inactivity = now - last_active[0]
                    if now >= hard_deadline:
                        stream_task.cancel()
                        await asyncio.gather(stream_task, return_exceptions=True)
                        raise asyncio.TimeoutError(
                            f"任务超时：总执行时间超过 {int(hard_timeout)}s 上限"
                        )
                    # v3.8.2: 根据当前相位选择超时阈值
                    current_phase = duck_phase[0]
                    if current_phase == "llm_waiting":
                        timeout_threshold = LLM_INACTIVITY_TIMEOUT
                    elif current_phase == "tool_executing":
                        timeout_threshold = TOOL_INACTIVITY_TIMEOUT
                    else:
                        timeout_threshold = IDLE_INACTIVITY_TIMEOUT

                    if inactivity > timeout_threshold:
                        stream_task.cancel()
                        await asyncio.gather(stream_task, return_exceptions=True)
                        raise asyncio.TimeoutError(
                            f"任务卡死：{int(inactivity)}s 内无任何进展"
                            f"（相位={current_phase}，阈值={timeout_threshold}s），Duck 可能已挂起"
                        )
            finally:
                if not stream_task.done():
                    stream_task.cancel()
                    await asyncio.gather(stream_task, return_exceptions=True)

        try:
            # v3.9: 使用确定性计划执行引擎（有 sandbox 时启用）
            if _sandbox:
                from services.duck_plan_executor import run_duck_task_with_plan

                async def _broadcast_chunk(chunk: dict) -> None:
                    """计划执行器的广播回调"""
                    last_active[0] = time.time()
                    _scheduler.update_task_activity(payload.task_id)
                    chunk_type = chunk.get("type", "")
                    if chunk_type == "llm_request_start":
                        duck_phase[0] = "llm_waiting"
                    elif chunk_type in ("llm_request_end", "tool_result"):
                        duck_phase[0] = "idle"
                    elif chunk_type == "tool_call":
                        duck_phase[0] = "tool_executing"
                    await broadcast_monitor_event(
                        session_id=source_session,
                        task_id=payload.task_id,
                        event=chunk,
                        task_type="duck",
                        worker_type="local_duck",
                        worker_id=self.duck_id,
                    )

                # 获取用于规划的 LLM（duck_llm 优先，否则使用主 LLM）
                _plan_llm = duck_llm
                if _plan_llm is None:
                    try:
                        from app_state import get_llm_client
                        _plan_llm = get_llm_client()
                    except Exception:
                        pass

                result = await asyncio.wait_for(
                    run_duck_task_with_plan(
                        agent=agent,
                        llm_client=_plan_llm,
                        task_description=isolated_desc,
                        workspace_dir=_sandbox.workspace_dir,
                        task_id=payload.task_id,
                        session_id=duck_session,
                        duck_type=self.duck_type.value if hasattr(self.duck_type, 'value') else str(self.duck_type),
                        hard_timeout=min(float(payload.timeout), 540.0),
                        broadcast_fn=_broadcast_chunk,
                    ),
                    timeout=float(payload.timeout),
                )
            else:
                result = await _run_smart(isolated_desc, float(payload.timeout))
            # 检测结果是否只是计划描述，而非真正执行结果
            if self._check_output_is_plan_not_result(result):
                # 先检查 workspace 是否有实际产出文件 — 有则直接视为成功，跳过重试
                _ws_files_early = []
                if _sandbox:
                    try:
                        _ws = _sandbox.workspace_dir
                        for _dp, _dd, _ff in os.walk(_ws):
                            for _fn in _ff:
                                if not _fn.startswith("."):
                                    _ws_files_early.append(os.path.join(_dp, _fn))
                    except Exception:
                        pass
                if _ws_files_early:
                    logger.info(
                        f"Duck {self.duck_id} output may be plan-text but workspace has {len(_ws_files_early)} file(s), treating as success"
                    )
                    # 将 workspace 产出追加到结果
                    result = (result or "") + (
                        f"\n\n【工作区产出】目录: {_sandbox.workspace_dir}\n"
                        + "\n".join(f"  - {f}" for f in _ws_files_early[:30])
                    )
                else:
                    logger.warning(
                        f"Duck {self.duck_id} returned plan instead of result, retrying with context rebuild"
                    )
                    # v3.8.1: 重试上下文重建 — 创建全新 agent 实例 + 注入失败摘要
                    agent = self._create_independent_agent(duck_llm)
                    failure_summary = (result or "")[:300]
                    reinforced_desc = self._build_retry_description(
                        payload, _sandbox, failure_summary, attempt=2
                    )
                    remaining_timeout = max(float(payload.timeout) * 0.7, 60.0)
                    result = await _run_smart(reinforced_desc, remaining_timeout)
                    if self._check_output_is_plan_not_result(result):
                        raise RuntimeError(
                            "任务未真正完成：Duck 返回了执行计划而非结果，可能是依赖缺失或脚本执行失败。"
                            f"请重新指派任务或让主 Agent 直接处理。"
                            f"（输出摘要：{str(result)[:150]}）"
                        )
            # 将沙箱工作区产出文件清单追加到结果，供下游节点（input_mapping）引用
            if _sandbox:
                try:
                    ws = _sandbox.workspace_dir
                    if os.path.isdir(ws):
                        ws_files = []
                        for _dp, _dd, _ff in os.walk(ws):
                            for _fn in _ff:
                                if not _fn.startswith("."):
                                    ws_files.append(os.path.join(_dp, _fn))
                        if ws_files:
                            result = (result or "") + (
                                f"\n\n【工作区产出】目录: {ws}\n"
                                + "\n".join(f"  - {f}" for f in ws_files[:30])
                            )
                except Exception:
                    pass
            return result
        except asyncio.TimeoutError as e:
            raise RuntimeError(str(e))
        except Exception as e:
            # 任务异常前先检查 workspace 是否已有产出文件（如 LLM 超时但文件已写完）
            if _sandbox:
                try:
                    _ws = _sandbox.workspace_dir
                    _rescue_files = []
                    if os.path.isdir(_ws):
                        for _dp, _dd, _ff in os.walk(_ws):
                            for _fn in _ff:
                                if not _fn.startswith("."):
                                    _rescue_files.append(os.path.join(_dp, _fn))
                    if _rescue_files:
                        logger.info(
                            f"Duck {self.duck_id} failed ({e}) but workspace has {len(_rescue_files)} file(s), treating as success"
                        )
                        _rescue_result = (
                            f"任务在执行中因异常中断（{str(e)[:100]}），但工作区已有产出文件：\n\n"
                            f"【工作区产出】目录: {_ws}\n"
                            + "\n".join(f"  - {f}" for f in _rescue_files[:30])
                        )
                        return _rescue_result
                except Exception:
                    pass
            logger.warning(f"Local Duck agent run failed, attempting LLM fallback: {e}")
            # 若任务涉及文件创建，LLM 无法真正写文件，不降级
            desc = (payload.description or "").lower()
            if any(k in desc for k in ("保存", "创建", "写入", "write", "create", ".html", ".md")):
                raise RuntimeError(
                    f"任务涉及文件创建，但 Agent 执行失败（{e}）。请重试或由主 Agent 直接处理。"
                )
            # 降级：直接用 LLM 补全（无工具）
            try:
                from app_state import get_llm_client
                client = get_llm_client()
                if client is None:
                    raise RuntimeError("No LLM client available")
                prompt = self._build_prompt(payload)
                resp = await asyncio.wait_for(
                    client.chat(messages=[{"role": "user", "content": prompt}]),
                    timeout=float(payload.timeout),
                )
                content = resp.get("content", "") if isinstance(resp, dict) else str(resp)
                return content
            except Exception as llm_err:
                raise RuntimeError(f"Local Duck fallback LLM failed: {llm_err}")
        finally:
            set_duck_context(None)            # v3.8: 归档沙箱产出
            # 归档目标：macagent_workspace/outputs/ 而非桌面，避免污染用户桌面。
            # 文件仍保留在 workspace_dir 中，同时备份到 outputs/ 供查阅。
            if _sandbox:
                try:
                    from services.duck_sandbox import get_duck_sandbox as _get_sb
                    import os as _os
                    _sb = _get_sb()
                    outputs = _sb.collect_outputs(_sandbox)
                    if outputs:
                        _outputs_dir = _os.path.expanduser(
                            "~/Desktop/macagent_workspace/outputs"
                        )
                        _sb.archive_sandbox(_sandbox, archive_dir=_outputs_dir)
                    else:
                        _sb.cleanup_sandbox(_sandbox, force=True)
                except Exception as _sb_err:
                    logger.debug(f"Sandbox archive/cleanup failed: {_sb_err}")
    async def _do_work(self, payload: DuckTaskPayload) -> Any:
        """
        实际执行任务逻辑。
        使用本地 AutonomousAgent 执行，使其拥有截图、终端、文件等全套工具。
        注入 Duck 身份（name/duck_type/skills）到 prompt，使 Agent 知晓专项技能。
        若分身配置了独立 LLM（api_key/base_url/model），优先使用以更有效运用大模型。
        """
        from app_state import set_duck_context

        # 从 registry 获取最新配置（用户可能已更新 llm_config）
        registry = DuckRegistry.get_instance()
        duck = await registry.get(self.duck_id)
        if duck:
            self.llm_api_key = duck.llm_api_key
            self.llm_base_url = duck.llm_base_url
            self.llm_model = duck.llm_model

        duck_ctx = {
            "name": self.name,
            "duck_type": self.duck_type.value,
            "skills": self.skills,
        }
        set_duck_context(duck_ctx)
        duck_llm = self._create_duck_llm_client()
        try:
            # 为每个任务创建独立 agent 实例
            agent = self._create_independent_agent(duck_llm)

            # v3.8.1: 使用隔离上下文描述
            isolated_desc = self._build_isolated_description(payload, None)

            # 首次执行
            result = await asyncio.wait_for(
                agent.run(isolated_desc),
                timeout=float(payload.timeout),
            )
            # 检测是否真正完成：若 summary 是 action plan JSON 而非结果，说明任务未完成
            if self._check_output_is_plan_not_result(result):
                # v3.8.1: 重试上下文重建 — 创建全新 agent + 注入失败摘要
                logger.warning(
                    f"Duck {self.duck_id} returned plan instead of result, retrying with context rebuild"
                )
                agent = self._create_independent_agent(duck_llm)
                failure_summary = (result or "")[:300]
                reinforced_desc = self._build_retry_description(
                    payload, None, failure_summary, attempt=2
                )
                remaining_timeout = max(
                    float(payload.timeout) * 0.7, 60.0
                )
                result = await asyncio.wait_for(
                    agent.run(reinforced_desc),
                    timeout=remaining_timeout,
                )
                if self._check_output_is_plan_not_result(result):
                    raise RuntimeError(
                        "任务未真正完成：Duck 返回了执行计划而非结果，可能是依赖缺失或脚本执行失败。"
                        f"请重新指派任务或让主 Agent 直接处理。"
                        f"（输出摘要：{str(result)[:150]}）"
                    )
            return result
        except asyncio.TimeoutError:
            raise RuntimeError(f"Local Duck task timed out after {payload.timeout}s")
        except Exception as e:
            logger.warning(f"Local Duck agent.run failed, attempting LLM fallback: {e}")
            # 若任务涉及文件创建，LLM 无法真正写文件，不降级
            desc = (payload.description or "").lower()
            if any(k in desc for k in ("保存", "创建", "写入", "write", "create", ".html", ".md")):
                raise RuntimeError(
                    f"任务涉及文件创建，但 Agent 执行失败（{e}）。请重试或由主 Agent 直接处理。"
                )
            # 降级：直接用 LLM 补全（无工具）
            try:
                from app_state import get_llm_client
                client = get_llm_client()
                if client is None:
                    raise RuntimeError("No LLM client available")
                prompt = self._build_prompt(payload)
                resp = await asyncio.wait_for(
                    client.chat(messages=[{"role": "user", "content": prompt}]),
                    timeout=float(payload.timeout),
                )
                content = resp.get("content", "") if isinstance(resp, dict) else str(resp)
                return content
            except Exception as llm_err:
                raise RuntimeError(f"Local Duck fallback LLM failed: {llm_err}")
        finally:
            set_duck_context(None)

    def _build_prompt(self, payload: DuckTaskPayload) -> str:
        """根据任务构建 LLM 提示"""
        parts = [f"You are a specialized {self.duck_type.value} agent named {self.name}."]
        if self.skills:
            parts.append(f"Your skills: {', '.join(self.skills)}")
        parts.append(f"\nTask: {payload.description}")
        if payload.params:
            parts.append(f"Parameters: {payload.params}")
        return "\n".join(parts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Local Duck Manager — 管理所有本地 Duck 实例
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class LocalDuckManager:
    """管理所有本地 Duck 实例（单例）"""

    _instance: Optional["LocalDuckManager"] = None

    def __init__(self):
        self._workers: Dict[str, LocalDuckWorker] = {}

    @classmethod
    def get_instance(cls) -> "LocalDuckManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def create_local_duck(
        self,
        name: str,
        duck_type: DuckType = DuckType.GENERAL,
        skills: list[str] | None = None,
        llm_api_key: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_model: Optional[str] = None,
    ) -> DuckInfo:
        """创建并启动一个新的本地 Duck"""
        duck_id = f"local_{uuid.uuid4().hex[:8]}"

        worker = LocalDuckWorker(
            duck_id=duck_id,
            name=name,
            duck_type=duck_type,
            skills=skills,
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
        )
        await worker.start()
        self._workers[duck_id] = worker

        registry = DuckRegistry.get_instance()
        info = await registry.get(duck_id)
        logger.info(f"Local Duck created: {duck_id}")
        return info  # type: ignore

    async def destroy_local_duck(self, duck_id: str) -> bool:
        """停止并删除一个本地 Duck"""
        worker = self._workers.pop(duck_id, None)
        if not worker:
            return False
        await worker.stop()

        registry = DuckRegistry.get_instance()
        await registry.unregister(duck_id)
        logger.info(f"Local Duck destroyed: {duck_id}")
        return True

    async def destroy_all(self):
        """停止所有本地 Duck"""
        for duck_id in list(self._workers.keys()):
            await self.destroy_local_duck(duck_id)

    def get_worker(self, duck_id: str) -> Optional[LocalDuckWorker]:
        return self._workers.get(duck_id)

    async def start_local_duck(self, duck_id: str) -> Optional[DuckInfo]:
        """启动离线的本地 Duck（从 Registry 恢复，用于后端重启后）"""
        registry = DuckRegistry.get_instance()
        await registry.initialize()
        duck = await registry.get(duck_id)
        if not duck or not duck.is_local:
            return None
        if self.get_worker(duck_id):
            return duck  # 已在运行

        worker = LocalDuckWorker(
            duck_id=duck_id,
            name=duck.name,
            duck_type=duck.duck_type,
            skills=duck.skills or [],
            llm_api_key=duck.llm_api_key,
            llm_base_url=duck.llm_base_url,
            llm_model=duck.llm_model,
            llm_provider_ref=duck.llm_provider_ref,
        )
        await worker.start()
        self._workers[duck_id] = worker
        return await registry.get(duck_id)

    def list_local_ducks(self) -> list[str]:
        return list(self._workers.keys())

    @property
    def count(self) -> int:
        return len(self._workers)


def get_local_duck_manager() -> LocalDuckManager:
    return LocalDuckManager.get_instance()
