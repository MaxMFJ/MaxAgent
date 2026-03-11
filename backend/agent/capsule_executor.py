"""
Capsule Executor - 将 Capsule procedure 转换为 Agent 可执行步骤
支持：
  - tool 调用与参数映射（{{input.xxx}}, {{output.stepN.xxx}}）
  - 子任务（subtask）
  - 条件执行（condition）
  - 并行步骤（parallel）
  - 重试与回退（retry / fallback_tool）
  - 超时控制（timeout）
  - 执行日志与统计
"""

import asyncio
import re
import logging
import time
from typing import Any, Dict, List, Optional

from .capsule_models import SkillCapsule, StepDef

logger = logging.getLogger(__name__)

PLACEHOLDER_INPUT = re.compile(r"\{\{\s*input\.(\w+)\s*\}\}")
PLACEHOLDER_OUTPUT = re.compile(r"\{\{\s*output\.(?:step_)?(\w+)\.(\w+)\s*\}\}")
CONDITION_PATTERN = re.compile(r"\{\{\s*output\.(?:step_)?(\w+)\.(\w+)\s*\}\}\s*(==|!=|>|<|>=|<=)\s*(.+)")


def _resolve_value(value: Any, inputs: Dict[str, Any], step_outputs: Dict[str, Dict[str, Any]]) -> Any:
    """递归解析字符串中的占位符。step_outputs 以 step_id 为键。"""
    if isinstance(value, str):
        def repl_input(m):
            val = inputs.get(m.group(1))
            return str(val) if val is not None else ""

        def repl_output(m):
            step_key = m.group(1)
            field_key = m.group(2)
            out = step_outputs.get(step_key) or step_outputs.get(f"step_{step_key}", {})
            if isinstance(out, dict) and field_key in out:
                return str(out[field_key])
            return m.group(0)

        s = PLACEHOLDER_INPUT.sub(repl_input, value)
        s = PLACEHOLDER_OUTPUT.sub(repl_output, s)
        return s
    if isinstance(value, dict):
        return {k: _resolve_value(v, inputs, step_outputs) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_value(v, inputs, step_outputs) for v in value]
    return value


def _evaluate_condition(
    condition: str,
    inputs: Dict[str, Any],
    step_outputs: Dict[str, Dict[str, Any]],
) -> bool:
    """评估条件表达式。支持 {{output.step_X.field}} == value 格式。"""
    if not condition or not condition.strip():
        return True

    resolved = _resolve_value(condition, inputs, step_outputs)

    m = re.match(r"(.+?)\s*(==|!=|>|<|>=|<=)\s*(.+)", resolved.strip())
    if not m:
        return bool(resolved.strip() and resolved.strip().lower() not in ("false", "0", "none", ""))

    left, op, right = m.group(1).strip(), m.group(2), m.group(3).strip()
    right = right.strip("'\"")

    try:
        left_num, right_num = float(left), float(right)
        ops = {"==": left_num == right_num, "!=": left_num != right_num,
               ">": left_num > right_num, "<": left_num < right_num,
               ">=": left_num >= right_num, "<=": left_num <= right_num}
        return ops.get(op, False)
    except (ValueError, TypeError):
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        return False


async def execute_capsule(
    capsule: SkillCapsule,
    inputs: Dict[str, Any],
    tool_registry=None,
    bind_target_fn=None,
) -> Dict[str, Any]:
    """
    执行 Capsule 的 procedure/steps。
    支持 tool / subtask / condition / parallel 类型步骤。
    支持 retry / fallback / timeout。
    返回: { "success": bool, "outputs": {...}, "steps": [...], "error": optional, "duration_ms": int }
    """
    from tools.router import execute_tool

    start_time = time.time()

    # 校验 inputs 是否包含 capsule 定义的必需参数
    cap_inputs = getattr(capsule, 'inputs', None) or {}
    if isinstance(cap_inputs, dict) and cap_inputs:
        missing = [k for k, v in cap_inputs.items()
                   if k not in inputs
                   and not (isinstance(v, dict) and v.get("default") is not None)]
        if missing:
            return {
                "success": False,
                "outputs": {},
                "steps": [],
                "error": f"缺少必需的输入参数: {', '.join(missing)}。capsule 需要: {list(cap_inputs.keys())}，实际传入: {list(inputs.keys())}",
                "duration_ms": 0,
            }
        # 为有默认值但未传入的参数填充默认值
        for k, v in cap_inputs.items():
            if k not in inputs and isinstance(v, dict) and v.get("default") is not None:
                inputs[k] = v["default"]

    step_defs = capsule.get_step_defs()
    if not step_defs:
        return {"success": True, "outputs": {}, "steps": [], "error": None, "duration_ms": 0}

    step_outputs: Dict[str, Dict[str, Any]] = {}
    step_results: List[Dict[str, Any]] = []

    for i, step_def in enumerate(step_defs):
        step_id = step_def.id or step_def.name or f"step_{i}"

        # 条件检查
        if step_def.condition:
            if not _evaluate_condition(step_def.condition, inputs, step_outputs):
                res = {"success": True, "step_id": step_id, "skipped": True, "reason": "condition not met"}
                step_results.append(res)
                step_outputs[step_id] = res
                continue

        step_type = step_def.type.lower()

        if step_type == "tool":
            res = await _execute_tool_step(step_def, step_id, inputs, step_outputs, tool_registry, bind_target_fn)
        elif step_type == "subtask":
            res = _execute_subtask_step(step_def, step_id, inputs, step_outputs)
        elif step_type == "parallel":
            res = await _execute_parallel_step(step_def, step_id, inputs, step_outputs, tool_registry, bind_target_fn)
        elif step_type == "condition":
            res = _execute_condition_step(step_def, step_id, inputs, step_outputs)
        elif step_def.tool or step_def.name:
            # 非标准 type 但指定了 tool/name → 当作 tool 步骤执行
            res = await _execute_tool_step(step_def, step_id, inputs, step_outputs, tool_registry, bind_target_fn)
        else:
            res = {"success": False, "step_id": step_id, "error": f"Unknown step type: {step_type}"}

        step_results.append(res)
        step_outputs[step_id] = res

        if not res.get("success") and not res.get("skipped"):
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "outputs": _build_outputs(capsule.outputs, step_outputs, step_results),
                "steps": step_results,
                "error": res.get("error", "Step failed"),
                "duration_ms": duration_ms,
            }

    duration_ms = int((time.time() - start_time) * 1000)
    outputs = _build_outputs(capsule.outputs, step_outputs, step_results)

    # 检测是否为"指令型"Capsule（所有步骤均为 subtask，无实际 tool 调用）
    is_instruction_only = all(
        r.get("type") == "subtask" or r.get("skipped")
        for r in step_results
    )
    if is_instruction_only:
        instructions = _collect_instructions(step_results, capsule)
        outputs["instructions"] = instructions
        outputs["instruction_mode"] = True

    return {"success": True, "outputs": outputs, "steps": step_results, "error": None, "duration_ms": duration_ms}


async def _execute_tool_step(
    step_def: StepDef,
    step_id: str,
    inputs: Dict[str, Any],
    step_outputs: Dict[str, Dict[str, Any]],
    tool_registry,
    bind_target_fn,
) -> Dict[str, Any]:
    """执行 tool 类型步骤，支持 retry 和 fallback。"""
    from tools.router import execute_tool

    tool_name = step_def.tool or step_def.name
    if not tool_name:
        return {"success": False, "step_id": step_id, "error": "Missing tool name"}

    raw_args = step_def.args or step_def.parameters or {}
    args = _resolve_value(raw_args, inputs, step_outputs)
    if not isinstance(args, dict):
        args = {}

    max_attempts = 1 + max(step_def.retry, 0)
    last_error = ""

    for attempt in range(max_attempts):
        try:
            if step_def.timeout > 0:
                result = await asyncio.wait_for(
                    execute_tool(tool_name, args, registry=tool_registry, bind_target_fn=bind_target_fn),
                    timeout=step_def.timeout,
                )
            else:
                result = await execute_tool(tool_name, args, registry=tool_registry, bind_target_fn=bind_target_fn)

            if result.success:
                res = {"success": True, "step_id": step_id, "tool": tool_name, "attempt": attempt + 1}
                if result.data is not None:
                    res["data"] = result.data
                return res
            else:
                last_error = result.error or "Tool failed"
                if attempt < max_attempts - 1:
                    logger.debug(f"Step {step_id} attempt {attempt + 1} failed: {last_error}, retrying...")
                    await asyncio.sleep(step_def.retry_delay)

        except asyncio.TimeoutError:
            last_error = f"Timeout after {step_def.timeout}s"
            if attempt < max_attempts - 1:
                await asyncio.sleep(step_def.retry_delay)
        except Exception as e:
            last_error = str(e)
            logger.exception(f"Step {step_id} tool {tool_name} error")
            if attempt < max_attempts - 1:
                await asyncio.sleep(step_def.retry_delay)

    # 所有重试失败，尝试 fallback
    if step_def.fallback_tool:
        logger.info(f"Step {step_id} falling back to {step_def.fallback_tool}")
        fallback_args = _resolve_value(step_def.fallback_args or args, inputs, step_outputs)
        try:
            result = await execute_tool(
                step_def.fallback_tool, fallback_args,
                registry=tool_registry, bind_target_fn=bind_target_fn,
            )
            if result.success:
                res = {"success": True, "step_id": step_id, "tool": step_def.fallback_tool, "fallback": True}
                if result.data is not None:
                    res["data"] = result.data
                return res
            last_error = f"Fallback also failed: {result.error}"
        except Exception as e:
            last_error = f"Fallback error: {e}"

    return {"success": False, "step_id": step_id, "tool": tool_name, "error": last_error}


def _execute_subtask_step(
    step_def: StepDef,
    step_id: str,
    inputs: Dict[str, Any],
    step_outputs: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """执行 subtask 类型步骤（仅记录描述，供上层 Agent 处理）。"""
    desc = step_def.description or ""
    desc = _resolve_value(desc, inputs, step_outputs) if isinstance(desc, str) else str(desc)
    return {"success": True, "step_id": step_id, "type": "subtask", "description": desc}


async def _execute_parallel_step(
    step_def: StepDef,
    step_id: str,
    inputs: Dict[str, Any],
    step_outputs: Dict[str, Dict[str, Any]],
    tool_registry,
    bind_target_fn,
) -> Dict[str, Any]:
    """执行 parallel 类型步骤：并行执行子步骤。"""
    sub_steps = step_def.steps
    if not sub_steps or not isinstance(sub_steps, list):
        return {"success": True, "step_id": step_id, "type": "parallel", "sub_results": []}

    tasks = []
    for j, sub in enumerate(sub_steps):
        sub_def = StepDef.from_dict(sub) if isinstance(sub, dict) else sub
        sub_id = sub_def.id or f"{step_id}_sub_{j}"
        if sub_def.type.lower() == "tool":
            tasks.append(_execute_tool_step(sub_def, sub_id, inputs, step_outputs, tool_registry, bind_target_fn))
        else:
            async def _wrap_subtask(sd=sub_def, sid=sub_id):
                return _execute_subtask_step(sd, sid, inputs, step_outputs)
            tasks.append(_wrap_subtask())

    sub_results = await asyncio.gather(*tasks, return_exceptions=True)
    processed = []
    all_success = True
    for r in sub_results:
        if isinstance(r, Exception):
            processed.append({"success": False, "error": str(r)})
            all_success = False
        elif isinstance(r, dict):
            processed.append(r)
            if not r.get("success"):
                all_success = False
        else:
            processed.append({"success": False, "error": "Unknown result"})
            all_success = False

    return {
        "success": all_success,
        "step_id": step_id,
        "type": "parallel",
        "sub_results": processed,
    }


def _execute_condition_step(
    step_def: StepDef,
    step_id: str,
    inputs: Dict[str, Any],
    step_outputs: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """执行 condition 类型步骤（纯条件判断，结果存入 outputs）。"""
    cond = step_def.condition or step_def.description or ""
    result = _evaluate_condition(cond, inputs, step_outputs)
    return {
        "success": True,
        "step_id": step_id,
        "type": "condition",
        "condition": cond,
        "result": result,
    }


def _build_outputs(
    output_schema: Dict[str, Any],
    step_outputs: Dict[str, Dict[str, Any]],
    step_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """根据 output schema 从步骤结果构建 outputs。"""
    out: Dict[str, Any] = {}
    if not output_schema:
        if step_results:
            last = step_results[-1]
            if last.get("success") and "data" in last:
                out["result"] = last["data"]
        return out

    last_data = None
    for r in reversed(step_results):
        if r.get("success") and "data" in r:
            last_data = r["data"]
            break

    for key in output_schema:
        if last_data is not None:
            if isinstance(last_data, dict) and key in last_data:
                out[key] = last_data[key]
            elif key == "result":
                out[key] = last_data
            else:
                out[key] = last_data
        else:
            out[key] = None
    return out


def _collect_instructions(
    step_results: List[Dict[str, Any]],
    capsule: SkillCapsule,
) -> str:
    """
    将纯 subtask Capsule 的所有步骤描述合并为一段结构化指令文本。
    Agent 收到后按指令使用自己已有的工具执行。
    """
    parts = [f"## 技能指令: {capsule.description}"]
    parts.append(f"来源: {capsule.source or 'local'} | ID: {capsule.id}")
    parts.append("")

    step_num = 0
    for r in step_results:
        if r.get("skipped"):
            continue
        desc = r.get("description", "")
        if not desc:
            continue
        step_num += 1
        parts.append(f"### 步骤 {step_num}")
        parts.append(desc)
        parts.append("")

    if capsule.tags:
        parts.append(f"相关标签: {', '.join(capsule.tags[:8])}")

    parts.append("")
    parts.append("请根据以上指令，使用你已有的工具（如 terminal、file、browser 等）逐步完成任务。")
    return "\n".join(parts)
