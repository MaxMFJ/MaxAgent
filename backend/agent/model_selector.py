"""
Intelligent Model Selector
Automatically selects the best model based on task characteristics
"""

import re
import json
import logging
import hashlib
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelType(Enum):
    LOCAL = "local"      # Ollama / LM Studio
    REMOTE = "remote"    # DeepSeek / OpenAI API


class ModelTier(Enum):
    """v3.4 三级模型路由 — 快 / 强 / 省"""
    FAST   = "fast"    # 本地小模型 / 低延迟 API，用于简单操作
    STRONG = "strong"  # 旗舰远程模型，用于复杂推理
    CHEAP  = "cheap"   # 中等性价比远程模型，平衡质量与成本


# 默认各级路由到的 provider/model（可通过 llm_config.json 中的 tier_models 覆盖）
_DEFAULT_TIER_MODELS: Dict[str, Dict[str, str]] = {
    ModelTier.FAST.value: {
        "provider": "local",
        "model": "",          # 运行时由 local_llm_manager 确定
        "description": "本地模型 / 低延迟",
    },
    ModelTier.STRONG.value: {
        "provider": "deepseek",
        "model": "deepseek-reasoner",
        "description": "旗舰推理模型",
    },
    ModelTier.CHEAP.value: {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "description": "性价比模型",
    },
}


def get_tier_for_task(analysis: "TaskAnalysis") -> ModelTier:
    """
    v3.4 三级路由规则：
      FAST   — 简单操作、敏感数据（隐私保护）、本地脚本
      STRONG — 复杂度≥7、多步规划、需知识查询
      CHEAP  — 其余（代码生成、普通推理）
    """
    if analysis.is_sensitive:
        return ModelTier.FAST
    if analysis.complexity_score >= 7 or analysis.task_type.value in (
        "complex_reasoning", "multi_step_planning", "knowledge_query"
    ):
        return ModelTier.STRONG
    if analysis.task_type.value in ("simple_operation",):
        return ModelTier.FAST
    return ModelTier.CHEAP


class TaskType(Enum):
    SIMPLE_OPERATION = "simple_operation"      # 简单文件/系统操作
    CODE_GENERATION = "code_generation"        # 代码/脚本生成
    COMPLEX_REASONING = "complex_reasoning"    # 复杂推理/规划
    SENSITIVE_DATA = "sensitive_data"          # 敏感数据处理
    KNOWLEDGE_QUERY = "knowledge_query"        # 知识查询
    MULTI_STEP_PLANNING = "multi_step_planning"  # 多步骤规划


@dataclass
class TaskAnalysis:
    """Result of task analysis"""
    task_type: TaskType
    complexity_score: int  # 1-10
    is_sensitive: bool
    requires_knowledge: bool
    requires_long_context: bool
    estimated_steps: int
    keywords: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_type": self.task_type.value,
            "complexity_score": self.complexity_score,
            "is_sensitive": self.is_sensitive,
            "requires_knowledge": self.requires_knowledge,
            "requires_long_context": self.requires_long_context,
            "estimated_steps": self.estimated_steps,
            "keywords": self.keywords
        }


@dataclass
class ModelSelection:
    """Model selection result"""
    model_type: ModelType
    reason: str
    confidence: float  # 0-1
    task_analysis: TaskAnalysis
    tier: "ModelTier" = field(default_factory=lambda: ModelTier.CHEAP)  # v3.4

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_type": self.model_type.value,
            "tier": self.tier.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "task_analysis": self.task_analysis.to_dict()
        }


@dataclass
class SelectionRecord:
    """Record of a model selection for learning"""
    task_hash: str
    task_description: str
    model_type: ModelType
    task_type: TaskType
    success: bool = False
    execution_time_ms: int = 0
    token_usage: int = 0
    quality_score: float = 0.0  # 0-1
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_hash": self.task_hash,
            "task_description": self.task_description[:100],
            "model_type": self.model_type.value,
            "task_type": self.task_type.value,
            "success": self.success,
            "execution_time_ms": self.execution_time_ms,
            "token_usage": self.token_usage,
            "quality_score": self.quality_score,
            "timestamp": self.timestamp.isoformat()
        }


class TaskAnalyzer:
    """Analyzes task characteristics"""
    
    # Keywords for different task types
    SENSITIVE_KEYWORDS = [
        "密码", "password", "secret", "key", "token", "credential",
        "私人", "隐私", "敏感", "加密", "解密", "证书", "私钥",
        ".env", "config", "配置文件", "api_key", "apikey"
    ]
    
    KNOWLEDGE_KEYWORDS = [
        "什么是", "为什么", "如何", "怎么", "解释", "介绍",
        "区别", "比较", "最新", "最佳实践", "推荐",
        "查询", "搜索", "查找", "联网", "上网", "网上",
        "股票", "天气", "新闻", "价格", "汇率", "翻译",
        "百度", "谷歌", "google", "搜一下", "帮我查",
        "what is", "why", "how to", "explain", "compare",
        "search", "query", "look up", "find out",
    ]
    
    COMPLEX_KEYWORDS = [
        "分析", "设计", "架构", "优化", "重构", "调试",
        "算法", "策略", "规划", "评估", "综合",
        "analyze", "design", "architecture", "optimize", "debug"
    ]
    
    SIMPLE_KEYWORDS = [
        "移动", "复制", "删除", "重命名", "创建", "打开", "关闭",
        "列出", "查看", "显示", "运行", "执行",
        "move", "copy", "delete", "rename", "create", "open", "close",
        "list", "show", "run", "execute"
    ]
    
    CODE_KEYWORDS = [
        "代码", "脚本", "程序", "函数", "类", "模块",
        "python", "bash", "javascript", "shell", "编写", "实现",
        "code", "script", "function", "class", "implement"
    ]
    
    def analyze(self, task: str) -> TaskAnalysis:
        """Analyze a task and return its characteristics"""
        task_lower = task.lower()
        
        # Check for sensitive data
        is_sensitive = any(kw in task_lower for kw in self.SENSITIVE_KEYWORDS)
        
        # Check for knowledge requirements
        requires_knowledge = any(kw in task_lower for kw in self.KNOWLEDGE_KEYWORDS)
        
        # Check for complexity indicators
        has_complex = any(kw in task_lower for kw in self.COMPLEX_KEYWORDS)
        has_simple = any(kw in task_lower for kw in self.SIMPLE_KEYWORDS)
        has_code = any(kw in task_lower for kw in self.CODE_KEYWORDS)
        
        # Determine task type
        if is_sensitive:
            task_type = TaskType.SENSITIVE_DATA
        elif has_complex and not has_simple:
            task_type = TaskType.COMPLEX_REASONING
        elif requires_knowledge:
            task_type = TaskType.KNOWLEDGE_QUERY
        elif has_code:
            task_type = TaskType.CODE_GENERATION
        else:
            task_type = TaskType.SIMPLE_OPERATION
        
        # Calculate complexity score
        complexity_score = 3  # Base score
        
        if has_complex:
            complexity_score += 3
        if requires_knowledge:
            complexity_score += 2
        if len(task) > 200:
            complexity_score += 1
        if "步骤" in task_lower or "step" in task_lower:
            complexity_score += 2
            task_type = TaskType.MULTI_STEP_PLANNING
        
        complexity_score = min(10, max(1, complexity_score))
        
        # Estimate steps
        if task_type == TaskType.SIMPLE_OPERATION:
            estimated_steps = 2
        elif task_type == TaskType.CODE_GENERATION:
            estimated_steps = 4
        elif task_type == TaskType.MULTI_STEP_PLANNING:
            estimated_steps = 8
        else:
            estimated_steps = 5
        
        # Check for long context requirement
        requires_long_context = len(task) > 500 or "所有" in task_lower or "全部" in task_lower
        
        # Extract keywords
        keywords = []
        for kw_list in [self.SIMPLE_KEYWORDS, self.CODE_KEYWORDS, self.COMPLEX_KEYWORDS]:
            for kw in kw_list:
                if kw in task_lower:
                    keywords.append(kw)
        
        return TaskAnalysis(
            task_type=task_type,
            complexity_score=complexity_score,
            is_sensitive=is_sensitive,
            requires_knowledge=requires_knowledge,
            requires_long_context=requires_long_context,
            estimated_steps=estimated_steps,
            keywords=keywords[:5]
        )


class ModelSelector:
    """
    Selects the best model based on task analysis and historical performance
    """
    
    def __init__(self, storage_dir: Optional[str] = None):
        self.analyzer = TaskAnalyzer()
        self.storage_dir = Path(storage_dir or Path(__file__).parent.parent / "data" / "model_selection")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self._strategy_file = self.storage_dir / "strategy.json"
        self._history_file = self.storage_dir / "history.json"
        
        self.strategy: Dict[str, Dict[str, Any]] = self._load_strategy()
        self.history: List[Dict[str, Any]] = self._load_history()
    
    def _load_strategy(self) -> Dict[str, Dict[str, Any]]:
        """Load learned strategy from disk"""
        if self._strategy_file.exists():
            try:
                with open(self._strategy_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        
        # Default strategy
        return {
            TaskType.SIMPLE_OPERATION.value: {"model": "local", "confidence": 0.9},
            TaskType.CODE_GENERATION.value: {"model": "local", "confidence": 0.8},
            TaskType.SENSITIVE_DATA.value: {"model": "local", "confidence": 1.0},
            TaskType.COMPLEX_REASONING.value: {"model": "remote", "confidence": 0.7},
            TaskType.KNOWLEDGE_QUERY.value: {"model": "remote", "confidence": 0.8},
            TaskType.MULTI_STEP_PLANNING.value: {"model": "remote", "confidence": 0.75},
        }
    
    def _save_strategy(self):
        """Save strategy to disk"""
        try:
            with open(self._strategy_file, "w", encoding="utf-8") as f:
                json.dump(self.strategy, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save strategy: {e}")
    
    def _load_history(self) -> List[Dict[str, Any]]:
        """Load selection history from disk"""
        if self._history_file.exists():
            try:
                with open(self._history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def _save_history(self):
        """Save history to disk (keep last 1000 records)"""
        try:
            self.history = self.history[-1000:]
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save history: {e}")
    
    def select(
        self,
        task: str,
        local_available: bool = True,
        remote_available: bool = True,
        prefer_local: bool = False
    ) -> ModelSelection:
        """
        Select the best model for a task
        
        Args:
            task: Task description
            local_available: Whether local model is available
            remote_available: Whether remote model is available
            prefer_local: User preference for local model
        
        Returns:
            ModelSelection with model type and reasoning
        """
        analysis = self.analyzer.analyze(task)
        
        # Get strategy for this task type
        task_strategy = self.strategy.get(
            analysis.task_type.value,
            {"model": "remote", "confidence": 0.5}
        )
        
        recommended = task_strategy["model"]
        confidence = task_strategy["confidence"]
        
        # Decision logic
        reasons = []
        
        # Rule 1: Sensitive data always uses local
        if analysis.is_sensitive:
            model_type = ModelType.LOCAL
            confidence = 1.0
            reasons.append("涉及敏感数据，使用本地模型保护隐私")
        
        # Rule 2: User preference
        elif prefer_local:
            model_type = ModelType.LOCAL
            reasons.append("用户偏好使用本地模型")
        
        # Rule 3: Complex tasks use remote
        elif analysis.complexity_score >= 7 and not analysis.is_sensitive:
            model_type = ModelType.REMOTE
            reasons.append(f"任务复杂度高 ({analysis.complexity_score}/10)，使用远程模型")
        
        # Rule 4: Knowledge queries use remote
        elif analysis.requires_knowledge:
            model_type = ModelType.REMOTE
            reasons.append("需要知识查询，使用远程模型")
        
        # Rule 5: Simple operations use local
        elif analysis.task_type in [TaskType.SIMPLE_OPERATION, TaskType.CODE_GENERATION]:
            model_type = ModelType.LOCAL
            reasons.append(f"简单{analysis.task_type.value}任务，使用本地模型节省成本")
        
        # Rule 6: Follow learned strategy
        else:
            model_type = ModelType.LOCAL if recommended == "local" else ModelType.REMOTE
            reasons.append(f"基于历史策略选择 ({confidence*100:.0f}% 置信度)")
        
        # Fallback if selected model not available
        if model_type == ModelType.LOCAL and not local_available:
            if remote_available:
                model_type = ModelType.REMOTE
                reasons.append("本地模型不可用，切换到远程模型")
            else:
                reasons.append("警告: 无可用模型")
        elif model_type == ModelType.REMOTE and not remote_available:
            if local_available:
                model_type = ModelType.LOCAL
                reasons.append("远程模型不可用，切换到本地模型")
            else:
                reasons.append("警告: 无可用模型")
        
        selection = ModelSelection(
            model_type=model_type,
            reason="; ".join(reasons),
            confidence=confidence,
            task_analysis=analysis,
            tier=get_tier_for_task(analysis),  # v3.4 三级路由
        )
        
        logger.info(f"Model selected: {model_type.value} (tier={selection.tier.value}) for task type {analysis.task_type.value}")
        logger.debug(f"Selection details: {selection.to_dict()}")
        
        return selection
    
    def record_result(
        self,
        task: str,
        selection: ModelSelection,
        success: bool,
        execution_time_ms: int = 0,
        token_usage: int = 0,
        quality_score: float = 0.0
    ):
        """
        Record the result of a model selection for learning
        """
        task_hash = hashlib.md5(task.encode()).hexdigest()[:12]
        
        record = SelectionRecord(
            task_hash=task_hash,
            task_description=task,
            model_type=selection.model_type,
            task_type=selection.task_analysis.task_type,
            success=success,
            execution_time_ms=execution_time_ms,
            token_usage=token_usage,
            quality_score=quality_score
        )
        
        self.history.append(record.to_dict())
        self._save_history()
        
        # Update strategy based on result
        self._update_strategy(record)
    
    def _update_strategy(self, record: SelectionRecord):
        """Update strategy based on execution result"""
        task_type = record.task_type.value
        
        if task_type not in self.strategy:
            self.strategy[task_type] = {"model": "remote", "confidence": 0.5, "stats": {}}
        
        strategy = self.strategy[task_type]
        
        if "stats" not in strategy:
            strategy["stats"] = {"local_success": 0, "local_total": 0, "remote_success": 0, "remote_total": 0}
        
        stats = strategy["stats"]
        
        # Update stats
        if record.model_type == ModelType.LOCAL:
            stats["local_total"] += 1
            if record.success:
                stats["local_success"] += 1
        else:
            stats["remote_total"] += 1
            if record.success:
                stats["remote_success"] += 1
        
        # Calculate success rates
        local_rate = stats["local_success"] / max(1, stats["local_total"])
        remote_rate = stats["remote_success"] / max(1, stats["remote_total"])
        
        # Update recommended model if we have enough data
        total_samples = stats["local_total"] + stats["remote_total"]
        if total_samples >= 5:
            # Consider both success rate and cost (local is cheaper)
            local_score = local_rate * 1.2  # 20% bonus for local (cheaper)
            remote_score = remote_rate
            
            if local_score > remote_score + 0.1:  # Significant advantage
                strategy["model"] = "local"
                strategy["confidence"] = min(0.95, local_rate + 0.1)
            elif remote_score > local_score + 0.1:
                strategy["model"] = "remote"
                strategy["confidence"] = min(0.95, remote_rate + 0.1)
        
        self._save_strategy()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get model selection statistics"""
        if not self.history:
            return {"total": 0, "by_model": {}, "by_task_type": {}}
        
        stats = {
            "total": len(self.history),
            "by_model": {"local": 0, "remote": 0},
            "by_task_type": {},
            "success_rate": 0,
            "avg_execution_time_ms": 0
        }
        
        total_time = 0
        success_count = 0
        
        for record in self.history:
            model = record.get("model_type", "unknown")
            task_type = record.get("task_type", "unknown")
            
            stats["by_model"][model] = stats["by_model"].get(model, 0) + 1
            stats["by_task_type"][task_type] = stats["by_task_type"].get(task_type, 0) + 1
            
            if record.get("success"):
                success_count += 1
            
            total_time += record.get("execution_time_ms", 0)
        
        stats["success_rate"] = success_count / max(1, len(self.history))
        stats["avg_execution_time_ms"] = total_time // max(1, len(self.history))
        stats["strategy"] = self.strategy
        
        return stats

    # ------------------------------------------------------------------
    # v3.4 Tier model config helpers
    # ------------------------------------------------------------------

    def get_tier_config(self, tier: "ModelTier") -> Dict[str, str]:
        """Return the model config dict for a given tier (merged with user overrides)."""
        base = dict(_DEFAULT_TIER_MODELS.get(tier.value, {}))
        try:
            from config.llm_config import load_llm_config
            cfg = load_llm_config() or {}
            user_tiers = cfg.get("tier_models", {})
            if tier.value in user_tiers:
                base.update(user_tiers[tier.value])
        except Exception:
            pass
        return base

    def get_all_tier_configs(self) -> Dict[str, Dict[str, str]]:
        """Return tier configs for all three tiers."""
        return {t.value: self.get_tier_config(t) for t in ModelTier}


# Global instance
_model_selector: Optional[ModelSelector] = None


def get_model_selector() -> ModelSelector:
    """Get or create the global model selector"""
    global _model_selector
    if _model_selector is None:
        _model_selector = ModelSelector()
    return _model_selector
