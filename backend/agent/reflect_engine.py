"""
Reflection Engine for Autonomous Agent
Uses local Ollama model to analyze execution and extract insights
"""

import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import AsyncOpenAI

from .action_schema import TaskContext, ActionLog
from .llm_utils import extract_text_from_content

logger = logging.getLogger(__name__)


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
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "efficiency_score": self.efficiency_score,
            "successes": self.successes,
            "failures": self.failures,
            "strategies": self.strategies,
            "improvements": self.improvements,
            "timestamp": self.timestamp.isoformat()
        }
    
    @classmethod
    def from_llm_response(cls, response: str) -> "ReflectResult":
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
                raw_response=response
            )
        except (json.JSONDecodeError, KeyError):
            return cls(
                efficiency_score=5,
                raw_response=response
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
        Analyze a completed task and extract insights
        """
        action_summary = self._summarize_actions(context.action_logs)
        
        prompt = f"""分析以下任务执行过程，提取经验和改进建议：

## 任务
{context.task_description}

## 执行结果
状态: {context.status}
总迭代次数: {context.current_iteration}
总动作数: {len(context.action_logs)}

## 动作日志
{action_summary}

## 分析要求
请分析：
1. 执行效率如何？（1-10分）
2. 哪些步骤执行得好？
3. 哪些步骤失败了？原因是什么？
4. 可以提取哪些可复用的策略？
5. 有哪些改进建议？

请以 JSON 格式输出：
```json
{{
  "efficiency_score": 7,
  "successes": ["成功点1", "成功点2"],
  "failures": ["失败点1及原因"],
  "strategies": ["策略1: 描述", "策略2: 描述"],
  "improvements": ["改进建议1", "改进建议2"]
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
            return ReflectResult.from_llm_response(content)
            
        except Exception as e:
            logger.error(f"Reflection error: {e}")
            return ReflectResult(
                efficiency_score=5,
                raw_response=f"Error: {str(e)}"
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
