"""
Reflection Engine for Autonomous Agent
Uses local Ollama model to analyze execution and extract insights

v3.1: 基础反思引擎（任务级反思、策略提取、模式分析）
Phase C 增强:
  - FailureType: 失败类型枚举（7 类）
  - classify_failure_type(): 根据错误信息自动分类
  - FAILURE_REFLECTION_TEMPLATES: 失败类型专属反思 prompt 模板
  - reflect() 在 ENABLE_FAILURE_TYPE_REFLECTION=true 时使用专属模板
"""

import json
import logging
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import AsyncOpenAI

from .action_schema import TaskContext, ActionLog
from .llm_utils import extract_text_from_content

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Phase C：失败类型分类与反思模板
# ─────────────────────────────────────────────────────────────────────────────

class FailureType(str, Enum):
    """Agent 执行失败的 7 类主要原因。"""
    COMMAND_ERROR    = "command_error"      # shell 命令语法/运行错误
    PERMISSION        = "permission"         # 权限不足（sudo、系统路径）
    FILE_NOT_FOUND   = "file_not_found"     # 文件/路径不存在
    NETWORK_ERROR    = "network_error"      # 网络请求失败、超时
    TIMEOUT          = "timeout"            # 执行超时
    LOGIC_ERROR      = "logic_error"        # 逻辑/语义错误（错误理解任务）
    UNKNOWN          = "unknown"            # 无法识别


# 每种失败类型的关键词（用于启发式分类）
_FAILURE_KEYWORDS: Dict[FailureType, List[str]] = {
    FailureType.COMMAND_ERROR:  ["command not found", "syntax error", "exit code", "error:", "returned non-zero", "bash:", "zsh:"],
    FailureType.PERMISSION:     ["permission denied", "operation not permitted", "sudo", "access denied", "不允许", "没有权限"],
    FailureType.FILE_NOT_FOUND: ["no such file", "not found", "does not exist", "文件不存在", "找不到文件", "path not found"],
    FailureType.NETWORK_ERROR:  ["connection refused", "network", "timeout", "ssl", "dns", "http error", "requests.exceptions", "网络"],
    FailureType.TIMEOUT:        ["timed out", "timeout", "超时", "time limit"],
    FailureType.LOGIC_ERROR:    ["logic", "incorrect", "wrong", "unexpected", "逻辑", "理解错误", "结果不对"],
}


# 失败类型 → 专属反思 prompt 模板
FAILURE_REFLECTION_TEMPLATES: Dict[FailureType, str] = {
    FailureType.COMMAND_ERROR: """\
## Failure Analysis (Command Execution Error)

Task: {task}
Failed step summary:
{action_summary}

Focus your analysis on:
1. Which command failed? What was the error message?
2. Was it a format, argument, or path issue?
3. What would the correct command be?
4. What command conventions should be followed for similar tasks?

Output as JSON:
```json
{{
  "efficiency_score": 5,
  "root_cause": "root cause",
  "correct_approach": "correct approach",
  "successes": [],
  "failures": ["failure reason"],
  "strategies": ["future strategy"],
  "improvements": ["improvement suggestion"]
}}
```""",

    FailureType.PERMISSION: """\
## Failure Analysis (Permission Issue)

Task: {task}
Failed step summary:
{action_summary}

Focus your analysis on:
1. Which operation triggered the permission denial?
2. Is sudo required? Are there security restrictions?
3. Are there alternative approaches (paths not requiring elevated privileges)?
4. How to proactively identify permission requirements in the future?

Output as JSON with same fields as above.""",

    FailureType.FILE_NOT_FOUND: """\
## Failure Analysis (File/Path Not Found)

Task: {task}
Failed step summary:
{action_summary}

Focus your analysis on:
1. What path was accessed? Why does it not exist?
2. Should list_directory be used first to verify the path?
3. Is the path relative or absolute? Any typos?
4. How to validate file existence before operations in the future?

Output as JSON with same fields as above.""",

    FailureType.NETWORK_ERROR: """\
## Failure Analysis (Network Error)

Task: {task}
Failed step summary:
{action_summary}

Focus your analysis on:
1. Specific cause of network failure (timeout/DNS/connection refused)?
2. Can the request be retried? Is a proxy or other config needed?
3. Are there offline alternatives?
4. How to design fault tolerance for network tasks in the future?

Output as JSON with same fields as above.""",

    FailureType.TIMEOUT: """\
## Failure Analysis (Timeout)

Task: {task}
Failed step summary:
{action_summary}

Focus your analysis on:
1. Which step timed out? What was the expected execution time?
2. Should background=true or async execution be used?
3. How to split into smaller sub-tasks?
4. How to plan for time-consuming operations in the future?

Output as JSON with same fields as above.""",

    FailureType.LOGIC_ERROR: """\
## Failure Analysis (Logic/Semantic Error)

Task: {task}
Failed step summary:
{action_summary}

Focus your analysis on:
1. Was the task understanding inaccurate?
2. Did the execution strategy match the user's actual intent?
3. Which step had a logical judgment error?
4. How to better understand the task during the Gather phase in the future?

Output as JSON with same fields as above.""",

    FailureType.UNKNOWN: """\
## Failure Analysis

Task: {task}
Execution stats: {status}, {total_actions} steps, {iterations} iterations
Failed step summary:
{action_summary}

Analyze:
1. Overall execution efficiency (1-10 score)
2. Successful steps
3. Failed steps and their causes
4. Reusable strategies to extract
5. Improvement suggestions

Output as JSON:
```json
{{
  "efficiency_score": 7,
  "successes": [],
  "failures": [],
  "strategies": [],
  "improvements": []
}}
```""",
}


def classify_failure_type(error_text: str) -> FailureType:
    """
    启发式分类失败类型。
    按 COMMAND_ERROR → PERMISSION → FILE_NOT_FOUND → NETWORK → TIMEOUT → LOGIC → UNKNOWN 顺序匹配。
    """
    if not error_text:
        return FailureType.UNKNOWN
    text_lower = error_text.lower()
    for ftype, keywords in _FAILURE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return ftype
    return FailureType.UNKNOWN


def classify_action_logs_failure(action_logs: "List[ActionLog]") -> FailureType:
    """从 action_log 中提取失败错误信息，综合分类主要失败类型。"""
    error_texts = []
    for log in action_logs:
        if not log.result.success and log.result.error:
            error_texts.append(log.result.error)
    combined = " ".join(error_texts)
    return classify_failure_type(combined)


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ReflectResult:
    """Result of reflection analysis"""
    efficiency_score: int  # 1-10
    successes: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    strategies: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    raw_response: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    # Phase C: 失败类型（分类结果）
    failure_type: FailureType = FailureType.UNKNOWN
    root_cause: str = ""
    correct_approach: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "efficiency_score": self.efficiency_score,
            "successes": self.successes,
            "failures": self.failures,
            "strategies": self.strategies,
            "improvements": self.improvements,
            "timestamp": self.timestamp.isoformat(),
            "failure_type": self.failure_type.value,
            "root_cause": self.root_cause,
            "correct_approach": self.correct_approach,
        }

    @classmethod
    def from_llm_response(
        cls,
        response: str,
        failure_type: FailureType = FailureType.UNKNOWN,
    ) -> "ReflectResult":
        """Parse LLM response into ReflectResult"""
        try:
            text = response.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            data = json.loads(text)

            return cls(
                efficiency_score=data.get("efficiency_score", 5),
                successes=data.get("successes", []),
                failures=data.get("failures", []),
                strategies=data.get("strategies", []),
                improvements=data.get("improvements", []),
                raw_response=response,
                failure_type=failure_type,
                root_cause=data.get("root_cause", ""),
                correct_approach=data.get("correct_approach", ""),
            )
        except (json.JSONDecodeError, KeyError):
            return cls(
                efficiency_score=5,
                raw_response=response,
                failure_type=failure_type,
            )


@dataclass
class Strategy:
    """A learned strategy from reflection"""
    strategy_id: str
    name: str
    description: str
    applicable_tasks: List[str]
    success_rate: float = 0.0
    usage_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "applicable_tasks": self.applicable_tasks,
            "success_rate": self.success_rate,
            "usage_count": self.usage_count,
            "created_at": self.created_at.isoformat()
        }


class ReflectEngine:
    """
    Reflection engine that analyzes task execution and extracts insights
    Uses local Ollama model for analysis
    """
    
    def __init__(
        self,
        ollama_url: str = "http://localhost:11434/v1",
        model: str = "qwen2.5:7b"
    ):
        self.client = AsyncOpenAI(
            base_url=ollama_url,
            api_key="ollama"
        )
        self.model = model
    
    def update_config(self, ollama_url: str, model: str):
        """Update Ollama configuration"""
        self.client = AsyncOpenAI(
            base_url=ollama_url,
            api_key="ollama"
        )
        self.model = model
    
    async def reflect(self, context: TaskContext) -> ReflectResult:
        """
        Analyze a completed task and extract insights.
        Phase C：若 ENABLE_FAILURE_TYPE_REFLECTION=true，自动分类失败类型并使用专属模板。
        """
        action_summary = self._summarize_actions(context.action_logs)

        # Phase C：失败类型分类 + 专属模板
        try:
            from app_state import ENABLE_FAILURE_TYPE_REFLECTION  # type: ignore
        except ImportError:
            ENABLE_FAILURE_TYPE_REFLECTION = True

        failure_type = FailureType.UNKNOWN
        if ENABLE_FAILURE_TYPE_REFLECTION and context.action_logs:
            failure_type = classify_action_logs_failure(context.action_logs)

        if ENABLE_FAILURE_TYPE_REFLECTION and failure_type != FailureType.UNKNOWN:
            template = FAILURE_REFLECTION_TEMPLATES[failure_type]
            prompt = template.format(
                task=context.task_description,
                status=context.status,
                total_actions=len(context.action_logs),
                iterations=context.current_iteration,
                action_summary=action_summary,
            )
        else:
            # 通用反思 prompt（兼容旧行为）
            template = FAILURE_REFLECTION_TEMPLATES[FailureType.UNKNOWN]
            prompt = template.format(
                task=context.task_description,
                status=context.status,
                total_actions=len(context.action_logs),
                iterations=context.current_iteration,
                action_summary=action_summary,
            )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )

            raw = getattr(response.choices[0].message, "content", None)
            content = extract_text_from_content(raw)
            result = ReflectResult.from_llm_response(content, failure_type=failure_type)
            logger.info(
                f"Reflection done: failure_type={failure_type.value} "
                f"efficiency={result.efficiency_score}"
            )
            return result

        except Exception as e:
            logger.error(f"Reflection error: {e}")
            return ReflectResult(
                efficiency_score=5,
                raw_response=f"Error: {str(e)}",
                failure_type=failure_type,
            )
    
    async def suggest_strategies(
        self,
        failed_actions: List[ActionLog]
    ) -> List[Strategy]:
        """
        Generate strategy suggestions based on failed actions
        """
        if not failed_actions:
            return []
        
        failures_desc = "\n".join([
            f"- {log.action.action_type.value}: {log.action.reasoning}\n  错误: {log.result.error}"
            for log in failed_actions[:5]
        ])
        
        prompt = f"""分析以下失败的操作，提出改进策略：

## 失败的操作
{failures_desc}

## 要求
针对这些失败，提出具体的改进策略。每个策略应该是可重用的。

请以 JSON 格式输出：
```json
{{
  "strategies": [
    {{
      "name": "策略名称",
      "description": "详细描述",
      "applicable_tasks": ["任务类型1", "任务类型2"]
    }}
  ]
}}
```"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            raw = getattr(response.choices[0].message, "content", None)
            content = extract_text_from_content(raw)
            
            text = content.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            
            data = json.loads(text.strip())
            strategies = []
            
            for i, s in enumerate(data.get("strategies", [])):
                strategies.append(Strategy(
                    strategy_id=f"strat_{i}",
                    name=s.get("name", ""),
                    description=s.get("description", ""),
                    applicable_tasks=s.get("applicable_tasks", [])
                ))
            
            return strategies
            
        except Exception as e:
            logger.error(f"Strategy suggestion error: {e}")
            return []
    
    async def analyze_pattern(
        self,
        task_contexts: List[TaskContext]
    ) -> Dict[str, Any]:
        """
        Analyze patterns across multiple task executions
        """
        if len(task_contexts) < 2:
            return {"patterns": [], "recommendations": []}
        
        summaries = []
        for ctx in task_contexts[-10:]:
            success_rate = sum(
                1 for log in ctx.action_logs if log.result.success
            ) / max(len(ctx.action_logs), 1)
            
            summaries.append({
                "task": ctx.task_description[:50],
                "status": ctx.status,
                "actions": len(ctx.action_logs),
                "success_rate": round(success_rate, 2)
            })
        
        prompt = f"""分析以下多个任务的执行模式：

{json.dumps(summaries, ensure_ascii=False, indent=2)}

请识别：
1. 常见的成功模式
2. 常见的失败模式
3. 改进建议

以 JSON 格式输出：
```json
{{
  "patterns": ["模式1", "模式2"],
  "recommendations": ["建议1", "建议2"]
}}
```"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            raw = getattr(response.choices[0].message, "content", None)
            content = extract_text_from_content(raw)
            
            text = content.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            
            return json.loads(text.strip())
            
        except Exception as e:
            logger.error(f"Pattern analysis error: {e}")
            return {"patterns": [], "recommendations": [], "error": str(e)}
    
    def _summarize_actions(self, action_logs: List[ActionLog]) -> str:
        """Create a summary of actions for the prompt"""
        lines = []
        for i, log in enumerate(action_logs[-15:], 1):
            status = "✓" if log.result.success else "✗"
            line = f"{i}. [{status}] {log.action.action_type.value}"
            line += f"\n   原因: {log.action.reasoning[:80]}"
            
            if log.result.output:
                output_str = str(log.result.output)[:100]
                line += f"\n   输出: {output_str}"
            
            if log.result.error:
                line += f"\n   错误: {log.result.error[:80]}"
            
            lines.append(line)
        
        return "\n".join(lines)


# Global instance
_reflect_engine: Optional[ReflectEngine] = None


def get_reflect_engine(
    ollama_url: str = "http://localhost:11434/v1",
    model: str = "qwen2.5:7b"
) -> ReflectEngine:
    """Get or create the global reflection engine"""
    global _reflect_engine
    
    if _reflect_engine is None:
        _reflect_engine = ReflectEngine(ollama_url, model)
    
    return _reflect_engine
