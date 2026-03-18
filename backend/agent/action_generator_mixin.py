"""
ActionGeneratorMixin — LLM-based action generation (_generate_action).
Extracted from autonomous_agent.py.
"""

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional

from .action_schema import AgentAction, ActionType, TaskContext, validate_action
from .agent_prompts import AUTONOMOUS_SYSTEM_PROMPT, _looks_like_json_or_code
from .context_builder import ContextBuilder
from .llm_call_builder import LLMCallBuilder
from .llm_utils import extract_text_from_content
from .prompt_loader import get_project_context_for_prompt
from .error_recovery import FIRST_STEP_PLAIN_TEXT_MIN_LEN

logger = logging.getLogger(__name__)


class ActionGeneratorMixin:
    """Mixin providing LLM-based action generation for AutonomousAgent."""

    async def _generate_action(
        self, context: TaskContext, llm_events: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[AgentAction]:
        """Generate the next action using LLM with context enrichment.
        If llm_events is provided, append llm_request_start/llm_request_end for monitoring.
        """
        # Build system prompt with user context (layer 1)
        # LEGACY PATH (DO NOT EXTEND) — Autonomous 模式的 system prompt 拼装仍为内联；
        # 新提示注入请通过 ContextBuilder 添加。
        user_ctx = getattr(self, "_user_context", "")

        # 注入共享 GUI 规则（single source of truth）
        from .shared_rules import GUI_RULES
        system_prompt = AUTONOMOUS_SYSTEM_PROMPT.replace(
            "{gui_rules}", GUI_RULES
        ).replace(
            "{user_context}", user_ctx if user_ctx else ""
        )

        # Duck 模式下剥离委派相关段落，防止 Duck 递归创建 DAG/委派子任务
        try:
            from app_state import IS_DUCK_MODE as _is_duck_prompt
        except ImportError:
            _is_duck_prompt = False
        if _is_duck_prompt:
            # 移除 action type 12 (delegate_duck) 和 13 (delegate_dag)
            system_prompt = re.sub(
                r'12\.\s*\*\*delegate_duck\*\*.*?(?=\n\d+\.\s*\*\*)',
                '', system_prompt, flags=re.DOTALL,
            )
            system_prompt = re.sub(
                r'13\.\s*\*\*delegate_dag\*\*.*?(?=\n\d+\.\s*\*\*)',
                '', system_prompt, flags=re.DOTALL,
            )
            # 移除规则 11（Multi-step task delegation）
            system_prompt = re.sub(
                r'11\.\s*\*\*Multi-step task delegation\*\*.*?(?=\n\d+\.\s*\*\*|\n\n##)',
                '', system_prompt, flags=re.DOTALL,
            )

        # 注入 Duck 分身身份与专项规范（Local Duck 执行时）
        try:
            from app_state import get_duck_context
            from services.duck_protocol import DuckType
            from services.duck_template import get_template
            duck_ctx = get_duck_context()
            if duck_ctx:
                duck_type_str = duck_ctx.get("duck_type", "general")
                try:
                    dt = DuckType(duck_type_str)
                    template = get_template(dt)
                    # 注入 Duck 模板的完整 system_prompt（含 _design_spec.md、analyze_local_image 等专项规范）
                    template_prompt = template.system_prompt.strip()
                except (ValueError, ImportError):
                    template_prompt = ""
                parts = [
                    f"[Duck Identity] You are {duck_ctx.get('name', 'Duck')}, specialized type: {duck_type_str}."
                ]
                if template_prompt:
                    parts.append(f"\n[Specialization Rules]\n{template_prompt}")
                if duck_ctx.get("skills"):
                    parts.append(f"\nYour specialized skills: {', '.join(duck_ctx['skills'])}. Prioritize using these skills to complete the task.")
                parts.append(
                    "\n[CRITICAL: Execution Rules] You are an executor, NOT a planner. You MUST:\n"
                    "1. Use tools directly (run_shell, write_file, call_tool, etc.) to execute the task — never just describe or plan.\n"
                    "2. If the task requires creating files, output write_file or create_and_run_script actions to actually create them.\n"
                    "3. NEVER output just text analysis or strategy descriptions. Every step must be an executable JSON action.\n"
                    "4. Do NOT finish on the first step unless the task is truly complete (files created, commands executed, etc.).\n"
                    "5. For code/HTML/file creation, use create_and_run_script (NEVER put very long content in write_file's content field)."
                )
                # 沙箱工作目录强制约束 — 确保产出文件写入分配的工作区而非桌面
                sandbox_dir = duck_ctx.get("sandbox_dir")
                if sandbox_dir:
                    parts.append(
                        f"\n[WORKSPACE — MANDATORY] Your ONLY output directory is: {sandbox_dir}\n"
                        "ALL files you create or write MUST be saved inside this directory.\n"
                        "⛔ NEVER save files to ~/Desktop, /tmp, or any other location.\n"
                        "⛔ IGNORE any '桌面路径' (Desktop path) hint shown below — it does NOT apply to your tasks.\n"
                        f"Example: to create output.html → write_file path: \"{sandbox_dir}/output.html\""
                    )
                duck_block = "\n".join(parts)
                system_prompt = duck_block + "\n\n---\n\n" + system_prompt
        except Exception:
            pass
        # 注入项目上下文（MACAGENT.md），每轮携带项目约定与能力边界
        project_ctx = get_project_context_for_prompt()
        if project_ctx:
            system_prompt = project_ctx + "\n\n---\n\n" + system_prompt

        # 注入 extra_system_prompt（来自 web augmentation 等外部上下文）
        _extra_sp = getattr(self, "_extra_system_prompt", "")
        if _extra_sp:
            system_prompt = system_prompt + "\n\n" + _extra_sp

        # v3.1: 结构化上下文（可选）+ Goal 重述
        try:
            from app_state import USE_SUMMARIZED_CONTEXT, GOAL_RESTATE_EVERY_N
        except ImportError:
            USE_SUMMARIZED_CONTEXT = True
            GOAL_RESTATE_EVERY_N = 6
        if USE_SUMMARIZED_CONTEXT and hasattr(context, "summarize_history_for_llm"):
            # 按 token 预算分配：默认 4000 tokens 给任务上下文
            _ctx_tokens = getattr(self.llm.config, "max_tokens", 4096) or 4096
            context_str = context.summarize_history_for_llm(
                max_recent=5, max_chars=5000, max_context_tokens=min(6000, _ctx_tokens * 2)
            )
        else:
            context_str = context.get_context_for_llm()
        if GOAL_RESTATE_EVERY_N and context.current_iteration > 0 and context.current_iteration % GOAL_RESTATE_EVERY_N == 0:
            context_str = f"[Current Goal] Original task: {context.task_description}\n\n" + context_str
        plan = getattr(self, "_current_plan", []) or []
        plan_index = getattr(self, "_current_plan_index", 0)
        if plan and plan_index < len(plan):
            remaining_count = len(plan) - plan_index
            context_str += (
                f"\n\n[Execution Plan] {len(plan)} total steps, currently on step {plan_index + 1}: {plan[plan_index]}"
                f"\nRemaining: {plan[plan_index:]}"
                f"\n⚠️ You MUST complete all steps in order. Do NOT finish the task before the plan is fully completed."
            )

        # v3.5: 注入环境状态 + 最近观察
        try:
            _env_ctx = self._observation_loop.env_state.get_context_for_llm()
            if _env_ctx and _env_ctx != "环境状态未知":
                context_str += f"\n\n[Environment State] {_env_ctx}"
            _obs_ctx = self._observation_loop.get_recent_observations_for_llm(n=2, max_chars=600)
            if _obs_ctx:
                context_str += f"\n\n[Recent Observations]\n{_obs_ctx}"
        except Exception:
            pass

        # v3.5: 注入任务进度 + 工具指标 + 失败记忆 + 策略建议
        try:
            _goal_ctx = self._goal_tracker.get_context_for_llm(max_chars=400)
            if _goal_ctx:
                context_str += f"\n\n{_goal_ctx}"
            _intel_ctx = self._runtime_intel.get_context_for_llm(max_chars=500)
            if _intel_ctx:
                context_str += f"\n\n{_intel_ctx}"
            _fail_mem = self._execution_controller.failure_memory.get_failure_summary(n=5)
            if _fail_mem:
                context_str += f"\n\n[Failure Memory]\n{_fail_mem}"
        except Exception:
            pass

        # v3.6: 动态注入在线 Duck 信息 — 委托给 ContextBuilder
        duck_status = await ContextBuilder.get_duck_status_context()
        if duck_status:
            context_str += f"\n\n{duck_status}"

        # v3.8: 注入持久化经验事实
        try:
            from .persistent_memory import get_factbase
            fact_hint = get_factbase().recall_for_prompt(context.task_description, max_chars=800)
            if fact_hint:
                context_str += f"\n\n{fact_hint}"
        except Exception:
            pass

        # LEGACY PATH (DO NOT EXTEND) — 消息构建内联；新增消息逻辑请通过 ContextBuilder。
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_str}
        ]

        if not context.action_logs:
            first_content = ""
            task_guidance = getattr(self, "_task_guidance", "").strip()
            if task_guidance:
                first_content = f"{task_guidance}\n\n"
            # 注入截断提示（若上轮 JSON 因 token 限制被截断）
            truncation_hint = getattr(context, "_truncation_hint", "")
            if truncation_hint:
                first_content += f"{truncation_hint}\n\n"
                context._truncation_hint = ""  # 只用一次
            first_content += "开始执行任务。请分析任务并输出第一步动作的 JSON。"
            if getattr(context, "retry_count", 0) > 0:
                first_content += "\n\n【重要】你必须只输出一个 JSON 动作（例如 run_shell、call_tool、read_file 等），不要输出大段自然语言说明。即使你认为任务难以完成，也请先输出一个尝试性动作的 JSON。"
            messages.append({
                "role": "user",
                "content": first_content
            })
        else:
            last_log = context.action_logs[-1]
            result_summary = ""
            if last_log.result.success:
                out = last_log.result.output
                out_str = (
                    out.get("content", out.get("output", ""))
                    if isinstance(out, dict) else str(out)
                )
                # read_file / file_operations read 结果需完整传递，避免 Agent 反复读取
                is_read = (
                    last_log.action.action_type == ActionType.READ_FILE
                    or (
                        last_log.action.action_type == ActionType.CALL_TOOL
                        and (last_log.action.params.get("args") or {}).get("action") == "read"
                    )
                )
                # 限制 read_file 结果注入 LLM 上下文的大小，防止超时
                _is_duck_mode = getattr(self, 'isolated_context', False)
                if not _is_duck_mode:
                    try:
                        from app_state import get_duck_context as _gdc_rd
                        _is_duck_mode = bool(_gdc_rd())
                    except Exception:
                        pass
                # 判断是否为 call_tool（搜索/爬虫类工具，结果可能较长）
                _is_call_tool = last_log.action.action_type == ActionType.CALL_TOOL
                _tool_name = (last_log.action.params.get("tool_name") or "").lower()
                _is_search_tool = _is_call_tool and any(
                    k in _tool_name for k in ("search", "web", "browser", "crawl", "fetch")
                )
                if is_read and _is_duck_mode:
                    out_limit = 2500  # Duck 模式读文件（从 3000 降低，防止后续 LLM 超时）
                elif is_read:
                    out_limit = 4000  # 普通模式（从 5000 降至 4000）
                elif _is_search_tool and _is_duck_mode:
                    out_limit = 1500  # Duck 模式搜索结果
                elif _is_call_tool and _is_duck_mode:
                    out_limit = 600   # Duck 模式其他工具调用
                else:
                    out_limit = 300
                result_summary = f"上一步执行成功。输出: {out_str[:out_limit]}{'...[已截断]' if len(out_str) > out_limit else ''}"
                # 截图类任务：一旦截图成功，强制要求立即 finish，避免重复截图
                task_desc = getattr(context, "task_description", "") or ""
                if any(k in task_desc for k in ("截图", "截屏", "screenshot", "屏幕")):
                    if last_log.action.action_type == ActionType.CALL_TOOL and (
                        (last_log.action.params.get("tool_name") or "").lower() == "screenshot"
                    ):
                        result_summary += "\n\n【重要】截图已成功，请立即输出 finish 动作结束任务，勿再截图或重复操作。"
            else:
                result_summary = f"上一步执行失败。错误: {last_log.result.error}"

            # Inject escalation prompt (layer 2 & 3) when triggered
            escalation = getattr(self, "_escalation_prompt", "")
            if escalation:
                result_summary += f"\n\n{escalation}"
            # v3.1 中途反思建议回写
            mid_hint = getattr(self, "_mid_reflection_hint", "") or ""
            # v3.8: 合并中间件链提示
            mw_hints = self._middleware_chain.collect_hints(context) if hasattr(self, '_middleware_chain') else ""
            if mw_hints:
                mid_hint = f"{mid_hint}\n{mw_hints}".strip() if mid_hint else mw_hints
            if mid_hint:
                result_summary += f"\n\n【中途反思建议】{mid_hint}"
                self._mid_reflection_hint = ""

            # 重复验证检测 — 委托给 ContextBuilder
            _verify_hint = ContextBuilder.build_verification_hint(context.action_logs)
            if _verify_hint:
                result_summary += f"\n\n{_verify_hint}"

            next_prompt = f"{result_summary}\n\n请分析结果并输出下一步动作的 JSON。"
            # 注入 phase verify 消息（来自上一轮 execution loop）
            phase_verify = getattr(context, "_phase_verify_message", None)
            if phase_verify and isinstance(phase_verify, dict):
                next_prompt = f"{next_prompt}\n\n{phase_verify.get('content', '')}"
                delattr(context, "_phase_verify_message")
            # 注入截断提示（若上轮 JSON 因 token 限制被截断）
            truncation_hint = getattr(context, "_truncation_hint", "")
            if truncation_hint:
                next_prompt += f"\n\n{truncation_hint}"
                context._truncation_hint = ""  # 只用一次
            # 多步且任务含报告/生成时，提示避免单次 JSON 过长被截断
            task_desc = getattr(context, "task_description", "") or ""
            if len(context.action_logs) >= 5 and any(k in task_desc for k in ("报告", "生成", "Markdown", "保存")):
                next_prompt += "\n\n【注意】若需写入长报告，请先输出 call_tool(file_operations) 或 write_file，content 可分段；或先 finish 简要总结。避免单次 JSON 过长被截断。"
            # 解析失败重试时，若已有较多步骤，提示简化输出
            if getattr(context, "retry_count", 0) > 0:
                next_prompt += "\n\n【重试提示】上轮输出可能被截断。请只输出一个简洁的 JSON 动作，报告内容不要全部内嵌在 content 中；可先 finish 简要总结，或分步 write_file。"
            # Duck 任务步数过多时主动催收尾（防止上下文爆炸导致卡死）
            try:
                from app_state import get_duck_context
                _is_duck = bool(get_duck_context())
            except Exception:
                _is_duck = False
            _steps_done = len(context.action_logs)
            if _is_duck and _steps_done >= 6 and not getattr(context, "_wrap_up_injected", False):
                context._wrap_up_injected = True
                next_prompt += (
                    "\n\n【⚠️ 收尾提示】你已执行了较多步骤，请立即将所有收集到的内容写入工作区，"
                    "然后用 finish 动作输出总结并结束任务。不要再进行新的搜索，专注于写文件和收尾。"
                )

            # ── 多模态注入：若上一步结果含图像（如 analyze_local_image / capture_and_analyze），
            #    将图像 base64 注入到消息中供视觉模型分析，避免 Agent 反复截图
            _last_output = last_log.result.output if last_log.result.success else None
            _image_base64 = None
            _image_mime = "image/png"
            if isinstance(_last_output, dict):
                _image_base64 = _last_output.get("image_base64")
                _image_mime = _last_output.get("mime_type", "image/png")
            if _image_base64:
                # 构建多模态消息
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": next_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{_image_mime};base64,{_image_base64}",
                                "detail": "high",
                            },
                        },
                    ],
                })
            else:
                messages.append({"role": "user", "content": next_prompt})

        llm_start = time.time()
        try:
            model_info = f"{self.llm.config.provider}/{self.llm.config.model}"
            logger.info(f"Generating action with LLM: {model_info}")
            if llm_events is not None:
                llm_events.append({
                    "type": "llm_request_start",
                    "provider": self.llm.config.provider,
                    "model": self.llm.config.model or "",
                    "iteration": context.current_iteration,
                })
            # 多步任务后易输出长 JSON（如报告），提高 max_tokens 避免截断
            extra_tokens = self._call_builder.compute_max_tokens(
                step_count=len(context.action_logs)
            )

            # Phase C：Extended Thinking / CoT 支持
            # v3.5: 上下文压缩 — 在发送给 LLM 前压缩消息列表
            try:
                try:
                    from app_state import get_duck_context
                    _keep = 4 if get_duck_context() else 6
                except Exception:
                    _keep = 6
                messages = self._context_compressor.compress(
                    messages,
                    current_query=context.task_description,
                    keep_recent=_keep,
                )
            except Exception as _comp_err:
                logger.debug("Context compression failed: %s", _comp_err)

            # 安全网：确保 messages 含至少一条 user 消息（防压缩器误删）
            messages = ContextBuilder.ensure_user_message_present(
                messages, context.task_description
            )

            chat_extra_body: Optional[Dict[str, Any]] = None
            try:
                from app_state import (  # type: ignore
                    ENABLE_EXTENDED_THINKING,
                    EXTENDED_THINKING_BUDGET_TOKENS,
                )
            except ImportError:
                ENABLE_EXTENDED_THINKING = False
                EXTENDED_THINKING_BUDGET_TOKENS = 8000
            if ENABLE_EXTENDED_THINKING:
                messages, chat_extra_body = self._call_builder.inject_cot(
                    messages,
                    enable_extended_thinking=True,
                    thinking_budget_tokens=EXTENDED_THINKING_BUDGET_TOKENS,
                )

            chat_coro = self.llm.chat(
                messages=messages,
                max_tokens=extra_tokens,
                extra_body=chat_extra_body,
            )
            try:
                from core.timeout_policy import get_timeout_policy
                if get_timeout_policy is not None:
                    response = await get_timeout_policy().with_llm_timeout(chat_coro)
                else:
                    response = await asyncio.wait_for(chat_coro, timeout=120.0)
            except ImportError:
                response = await asyncio.wait_for(chat_coro, timeout=120.0)
            raw_content = response.get("content", "")
            content = extract_text_from_content(raw_content)
            finish_reason = response.get("finish_reason", "")
            usage = response.get("usage") or {}
            tokens = usage.get("total_tokens", 0)
            context.total_tokens += tokens
            context.total_prompt_tokens += usage.get("prompt_tokens", 0)
            context.total_completion_tokens += usage.get("completion_tokens", 0)
            setattr(self, "_last_llm_tokens", tokens)
            latency_ms = int((time.time() - llm_start) * 1000)
            if llm_events is not None:
                llm_events.append({
                    "type": "llm_request_end",
                    "provider": self.llm.config.provider,
                    "model": self.llm.config.model or "",
                    "iteration": context.current_iteration,
                    "latency_ms": latency_ms,
                    "usage": {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": tokens,
                    },
                    "response_preview": (content[:200] + "…") if len(content) > 200 else content,
                })

            if not content:
                logger.warning("Empty LLM response (finish_reason=%s)", finish_reason)
                return None

            action = AgentAction.from_llm_response(content)
            if action is None:
                # 诊断：记录 finish_reason（length=截断）、首尾片段，便于定位解析失败原因
                tail = content[-500:] if len(content) > 500 else content
                logger.warning(
                    "Failed to parse LLM output | len=%d | finish_reason=%s | step=%d | first 600: %s",
                    len(content), finish_reason, len(context.action_logs), content[:600]
                )
                logger.warning(
                    "Parse fail | last 500 chars: %s",
                    tail
                )
                # 兜底1：疑似截断的 JSON（finish_reason=length）+ 多步成功 → 视为任务完成，避免无限重试
                steps = len(context.action_logs)
                success_count = sum(1 for log in context.action_logs if log.result.success)
                # 部分 API 网关（如 newapi/claude-haiku）不正确上报 finish_reason=length，
                # 补充检测：completion_tokens 达到本次 max_tokens 上限也视为截断
                completion_tokens = usage.get("completion_tokens", 0)
                _effective_max_tokens = extra_tokens or self.llm.config.max_tokens or 4096
                is_truncated = LLMCallBuilder.is_truncated(
                    finish_reason, completion_tokens, _effective_max_tokens
                )
                if is_truncated and finish_reason != "length":
                    logger.info(
                        "Supplementary truncation detection: completion_tokens=%d >= max_tokens=%d",
                        completion_tokens, _effective_max_tokens,
                    )
                # 条件放宽：截断时 ≥5 步且 ≥3 成功即视为完成；或最后一次重试且 ≥8 步 ≥6 成功（任务已基本完成）
                retry_count = getattr(context, "retry_count", 0)
                is_last_retry = retry_count >= context.max_retries - 1
                if (is_truncated and steps >= 5 and success_count >= 3) or (is_last_retry and steps >= 8 and success_count >= 6):
                        logger.info(
                            "Treating as finish (truncated=%s, last_retry=%s, steps=%d, success=%d)",
                            is_truncated, is_last_retry, steps, success_count,
                        )
                        action = AgentAction(
                            action_type=ActionType.FINISH,
                            params={"summary": "任务已执行多步。请检查桌面或目标路径是否已有生成内容。", "success": True},
                            reasoning="基于已成功步骤视为完成。",
                        )
                # 兜底1.5：截断的 JSON action（首步 write_file 等被截断）→ 注入文件拆分提示并重试
                if action is None and is_truncated and '"action_type"' in content:
                    logger.info(
                        "Truncated JSON action detected at step %d, injecting split-file hint",
                        steps,
                    )
                    # 不创建 finish action，让重试机制加入拆分提示
                    context._truncation_hint = (
                        "【输出被截断警告】你上次尝试输出了过大的 JSON，导致被截断。"
                        "请将大文件内容拆分：使用 create_and_run_script 编写 Python 脚本生成文件，"
                        "或使用 run_shell 通过 cat << 'HEREDOC' 写入。禁止在 write_file 中放入超长内容。"
                    )
                # 兜底2：LLM 返回了纯自然语言（如打招呼回复）时，视为 finish，把整段内容作为 summary 返回
                if action is None:
                    text = content.strip()[:4000]
                    if text and not _looks_like_json_or_code(content):
                        # 第一步且长文本：多为模型"说明无法完成"，先重试强提示 JSON；最后一次重试时不再拒绝，避免连续解析失败
                        retry_count = getattr(context, "retry_count", 0)
                        is_last_retry = retry_count >= context.max_retries - 1
                        if not context.action_logs and len(text) > FIRST_STEP_PLAIN_TEXT_MIN_LEN and not is_last_retry:
                            logger.info(
                                "First step: rejecting long plain-text as finish (len=%d), will retry with JSON reminder",
                                len(text),
                            )
                            action = None
                    elif text and _looks_like_json_or_code(content):
                        # 内容含 JSON 标记但解析失败（GLM/部分模型把 JSON 包在 markdown 代码块里，
                        # 或 max_tokens 截断导致 JSON 不完整）→ 注入格式提示后重试，不当作 finish
                        retry_count = getattr(context, "retry_count", 0)
                        is_last_retry = retry_count >= context.max_retries - 1
                        if not is_last_retry:
                            logger.info(
                                "Content looks like JSON/code but failed to parse (len=%d, finish_reason=%s), injecting format reminder",
                                len(text), finish_reason,
                            )
                            context._truncation_hint = (
                                "【JSON 格式错误】你的上一步输出包含了代码块或 JSON，但系统无法正确解析。"
                                "请直接输出一个纯 JSON 对象，不要用 ```json 代码块包裹，不要在 JSON 前后添加任何说明文字。"
                                '{"action_type": "write_file", "params": {"path": "/path/to/file", "content": "..."}, "reasoning": "..."}'
                            )
                            action = None  # 触发重试
                        else:
                            # 最后一次重试：若内容疑似 write_file 被截断（含 path、content、html 等），
                            # 注入 create_and_run_script 提示并允许再试一次，避免「显示成功但 HTML 为空」
                            has_write_file_indicators = (
                                '"write_file"' in content and '"path"' in content
                                and ('"content"' in content or "'content'" in content)
                                and ("<!DOCTYPE" in content or "<html" in content or "html" in content.lower())
                            )
                            if has_write_file_indicators and len(content) > 2000:
                                logger.info(
                                    "Last retry: content looks like truncated write_file (len=%d), "
                                    "injecting create_and_run_script hint for one more attempt",
                                    len(content),
                                )
                                context._truncation_hint = (
                                    "【输出被截断】你上次尝试在 write_file 的 content 中放入超长 HTML，导致 JSON 被截断无法解析。"
                                    "**必须**改用 create_and_run_script：编写 Python 脚本，在脚本中用变量存储 HTML 字符串，"
                                    "然后 with open(path,'w') as f: f.write(html) 写入文件。禁止在 JSON 的 content 中直接放超长内容。"
                                )
                                context._allow_one_more_retry = True  # 允许再试一次
                                action = None
                            else:
                                logger.info("Last retry: treating JSON-like but unparseable content as finish")
                                action = AgentAction(
                                    action_type=ActionType.FINISH,
                                    params={"summary": text, "success": True},
                                    reasoning="LLM 返回了纯文本回复，已作为最终回复。"
                                )

            if action:
                validation_error = validate_action(action)
                if validation_error:
                    logger.warning(f"Action validation failed: {validation_error}")
                    return None

            try:
                from core.trace_logger import append_span as trace_append_span
                if trace_append_span:
                    span = {
                        "iteration": context.current_iteration,
                        "type": "llm",
                        "model": model_info,
                        "latency_ms": int((time.time() - llm_start) * 1000),
                        "success": action is not None,
                    }
                    if action is None:
                        span["error"] = "parse_failed"
                    trace_append_span(context.task_id, span)
            except ImportError:
                pass
            return action

        except asyncio.TimeoutError:
            logger.error("LLM request timed out (TimeoutPolicy.llm_timeout or 120s fallback)")
            # 标记超时，让调用方区分超时 vs 解析失败，采取不同重试策略
            context._last_llm_timeout = True
            if llm_events is not None:
                llm_events.append({
                    "type": "llm_request_end",
                    "provider": self.llm.config.provider,
                    "model": self.llm.config.model or "",
                    "iteration": context.current_iteration,
                    "latency_ms": int((time.time() - llm_start) * 1000),
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "response_preview": None,
                    "error": "timeout",
                })
            return None
        except Exception as e:
            logger.error(f"Error generating action: {e}", exc_info=True)
            # 上下文超限检测：标记 timeout 并注入压缩提示，让调用方缩减上下文后重试
            err_str = str(e).lower()
            if any(k in err_str for k in ("context_length", "context length", "token limit",
                                           "max_tokens", "maximum context", "too many tokens",
                                           "reduce the length", "context window",
                                           "context_too_large")):
                logger.warning("Context too large in _generate_action, marking for context reduction")
                context._last_llm_timeout = True
                context._truncation_hint = (
                    "【上下文超限】LLM 请求因上下文过大而失败。\n"
                    "请采取以下策略：\n"
                    "1. 使用 create_and_run_script 编写 Python 脚本来读取和处理文件，而不是通过 read_file 把全文放入上下文\n"
                    "2. 如果已有足够信息，直接用 finish 完成任务\n"
                    "3. 操作文件时使用 sed/awk 等命令操作，避免大段内容传递"
                )
            if llm_events is not None:
                llm_events.append({
                    "type": "llm_request_end",
                    "provider": self.llm.config.provider,
                    "model": self.llm.config.model or "",
                    "iteration": context.current_iteration,
                    "latency_ms": int((time.time() - llm_start) * 1000),
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "response_preview": None,
                    "error": str(e)[:200],
                })
            return None
