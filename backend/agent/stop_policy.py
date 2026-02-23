"""
Adaptive Stop Policy for Autonomous Agent
Implements intelligent stopping conditions with multiple criteria

StopPolicy = MaxIterations | MaxCost | NoProgress | LoopDetected | TaskComplete | Error
"""

import time
import hashlib
import logging
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class StopReason(Enum):
    """Reasons for stopping execution"""
    TASK_COMPLETE = "task_complete"
    MAX_ITERATIONS = "max_iterations"
    MAX_COST = "max_cost"
    NO_PROGRESS = "no_progress"
    LOOP_DETECTED = "loop_detected"
    CONSECUTIVE_FAILURES = "consecutive_failures"
    TIMEOUT = "timeout"
    USER_ABORT = "user_abort"
    CONVERGENCE = "convergence"
    ERROR = "error"


class TaskComplexity(Enum):
    """Task complexity levels for adaptive iteration limits"""
    TRIVIAL = "trivial"       # 1-3 steps (e.g., open app)
    SIMPLE = "simple"         # 3-10 steps (e.g., list files)
    MODERATE = "moderate"     # 10-25 steps (e.g., organize folder)
    COMPLEX = "complex"       # 25-50 steps (e.g., create project)
    VERY_COMPLEX = "very_complex"  # 50+ steps (e.g., full app development)


@dataclass
class IterationSnapshot:
    """Snapshot of state at each iteration"""
    iteration: int
    action_type: str
    action_hash: str
    output_hash: str
    success: bool
    execution_time_ms: int
    timestamp: float = field(default_factory=time.time)
    token_cost: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "action_type": self.action_type,
            "action_hash": self.action_hash,
            "success": self.success,
            "execution_time_ms": self.execution_time_ms,
            "token_cost": self.token_cost
        }


@dataclass
class StopDecision:
    """Decision about whether to stop execution"""
    should_stop: bool
    reason: Optional[StopReason]
    message: str
    confidence: float = 1.0  # 0-1 confidence in the decision
    recommendation: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_stop": self.should_stop,
            "reason": self.reason.value if self.reason else None,
            "message": self.message,
            "confidence": self.confidence,
            "recommendation": self.recommendation
        }


class ProgressTracker:
    """
    Tracks task progress to detect stagnation
    """
    
    def __init__(self, window_size: int = 5, progress_threshold: float = 0.2):
        self.window_size = window_size
        self.progress_threshold = progress_threshold
        self.snapshots: deque = deque(maxlen=50)
        self.unique_outputs: Set[str] = set()
        self.successful_actions: int = 0
        self.failed_actions: int = 0
        self.action_types_used: Set[str] = set()
        self.files_modified: Set[str] = set()
        
    def record(self, snapshot: IterationSnapshot, output: Any = None):
        """Record an iteration snapshot"""
        self.snapshots.append(snapshot)
        
        if snapshot.success:
            self.successful_actions += 1
        else:
            self.failed_actions += 1
        
        self.action_types_used.add(snapshot.action_type)
        
        if output:
            output_str = str(output)[:500]
            self.unique_outputs.add(hashlib.md5(output_str.encode()).hexdigest()[:8])
    
    def has_progress(self) -> Tuple[bool, float, str]:
        """
        Check if there's been progress in recent iterations
        
        Returns:
            (has_progress, progress_score, explanation)
        """
        if len(self.snapshots) < 3:
            return True, 1.0, "Not enough data"
        
        recent = list(self.snapshots)[-self.window_size:]
        
        # Progress indicators
        unique_actions = len(set(s.action_type for s in recent))
        success_rate = sum(1 for s in recent if s.success) / len(recent)
        unique_outputs = len(set(s.output_hash for s in recent))
        
        # Score calculation
        action_diversity_score = min(unique_actions / 3, 1.0)  # Diverse actions = progress
        success_score = success_rate
        output_diversity_score = min(unique_outputs / len(recent), 1.0)
        
        # Check for "think" spam (common stagnation pattern)
        think_count = sum(1 for s in recent if s.action_type == "think")
        think_penalty = 1.0 - (think_count / len(recent)) * 0.5
        
        progress_score = (
            action_diversity_score * 0.3 +
            success_score * 0.4 +
            output_diversity_score * 0.2 +
            think_penalty * 0.1
        )
        
        has_progress = progress_score >= self.progress_threshold
        
        explanation = (
            f"Progress score: {progress_score:.2f} "
            f"(actions: {action_diversity_score:.2f}, "
            f"success: {success_score:.2f}, "
            f"outputs: {output_diversity_score:.2f})"
        )
        
        return has_progress, progress_score, explanation
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get progress statistics"""
        if not self.snapshots:
            return {}
        
        recent = list(self.snapshots)[-10:]
        
        return {
            "total_iterations": len(self.snapshots),
            "successful_actions": self.successful_actions,
            "failed_actions": self.failed_actions,
            "success_rate": self.successful_actions / max(len(self.snapshots), 1),
            "unique_outputs": len(self.unique_outputs),
            "action_types_used": list(self.action_types_used),
            "recent_success_rate": sum(1 for s in recent if s.success) / max(len(recent), 1),
            "avg_execution_time_ms": sum(s.execution_time_ms for s in recent) / max(len(recent), 1)
        }


class LoopDetector:
    """
    Detects repetitive patterns that indicate the agent is stuck
    """
    
    def __init__(self, pattern_length: int = 3, min_repetitions: int = 2):
        self.pattern_length = pattern_length
        self.min_repetitions = min_repetitions
        self.action_sequence: List[str] = []
        self.detected_loops: List[Dict[str, Any]] = []
        
    def record(self, action_type: str, action_hash: str):
        """Record an action for loop detection"""
        self.action_sequence.append(f"{action_type}:{action_hash[:8]}")
    
    def detect_loop(self) -> Tuple[bool, Optional[str], int]:
        """
        Detect if agent is stuck in a loop
        
        Returns:
            (is_looping, pattern, repetition_count)
        """
        if len(self.action_sequence) < self.pattern_length * self.min_repetitions:
            return False, None, 0
        
        # Check for various pattern lengths
        for pattern_len in range(2, min(self.pattern_length + 1, len(self.action_sequence) // 2)):
            recent = self.action_sequence[-(pattern_len * (self.min_repetitions + 1)):]
            
            # Extract potential pattern
            pattern = recent[-pattern_len:]
            
            # Count repetitions
            repetitions = 0
            for i in range(len(recent) - pattern_len, -1, -pattern_len):
                segment = recent[i:i + pattern_len]
                if segment == pattern:
                    repetitions += 1
                else:
                    break
            
            if repetitions >= self.min_repetitions:
                pattern_str = " -> ".join(pattern)
                self.detected_loops.append({
                    "pattern": pattern_str,
                    "repetitions": repetitions,
                    "timestamp": time.time()
                })
                return True, pattern_str, repetitions
        
        # Check for same action repeated
        if len(self.action_sequence) >= 3:
            last_three = self.action_sequence[-3:]
            if last_three[0] == last_three[1] == last_three[2]:
                return True, last_three[0], 3
        
        return False, None, 0
    
    def get_detected_loops(self) -> List[Dict[str, Any]]:
        """Get all detected loops"""
        return self.detected_loops


class CostTracker:
    """
    Tracks token and time costs
    """
    
    def __init__(self, max_tokens: int = 100000, max_time_seconds: int = 600):
        self.max_tokens = max_tokens
        self.max_time_seconds = max_time_seconds
        self.total_tokens = 0
        self.total_time_ms = 0
        self.start_time = time.time()
        self.token_history: List[int] = []
        
    def record(self, tokens: int = 0, execution_time_ms: int = 0):
        """Record token usage and execution time"""
        self.total_tokens += tokens
        self.total_time_ms += execution_time_ms
        self.token_history.append(tokens)
    
    def check_limits(self) -> Tuple[bool, Optional[str]]:
        """Check if any cost limits are exceeded"""
        if self.total_tokens >= self.max_tokens:
            return True, f"Token limit exceeded: {self.total_tokens}/{self.max_tokens}"
        
        elapsed = time.time() - self.start_time
        if elapsed >= self.max_time_seconds:
            return True, f"Time limit exceeded: {elapsed:.0f}s/{self.max_time_seconds}s"
        
        return False, None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get cost statistics"""
        elapsed = time.time() - self.start_time
        return {
            "total_tokens": self.total_tokens,
            "max_tokens": self.max_tokens,
            "token_usage_percent": (self.total_tokens / self.max_tokens) * 100,
            "elapsed_seconds": elapsed,
            "max_time_seconds": self.max_time_seconds,
            "time_usage_percent": (elapsed / self.max_time_seconds) * 100,
            "avg_tokens_per_iteration": sum(self.token_history) / max(len(self.token_history), 1)
        }


class TaskComplexityAnalyzer:
    """
    Analyzes task complexity to determine adaptive iteration limits
    """
    
    COMPLEXITY_KEYWORDS = {
        TaskComplexity.TRIVIAL: [
            "打开", "关闭", "启动", "显示", "查看时间", "查看日期"
        ],
        TaskComplexity.SIMPLE: [
            "列出", "读取", "获取", "查看", "复制", "移动", "删除", "重命名"
        ],
        TaskComplexity.MODERATE: [
            "整理", "清理", "归类", "搜索并", "批量", "分析", "统计"
        ],
        TaskComplexity.COMPLEX: [
            "创建项目", "开发", "设计", "实现", "部署", "配置环境", "安装并配置"
        ],
        TaskComplexity.VERY_COMPLEX: [
            "完整应用", "全栈", "自动化流程", "系统迁移", "大规模"
        ]
    }
    
    COMPLEXITY_LIMITS = {
        TaskComplexity.TRIVIAL: (3, 5),      # min, max iterations
        TaskComplexity.SIMPLE: (5, 15),
        TaskComplexity.MODERATE: (10, 30),
        TaskComplexity.COMPLEX: (20, 50),
        TaskComplexity.VERY_COMPLEX: (30, 100)
    }
    
    @classmethod
    def analyze(cls, task: str) -> Tuple[TaskComplexity, int, int]:
        """
        Analyze task complexity and return adaptive limits
        
        Returns:
            (complexity, min_iterations, max_iterations)
        """
        task_lower = task.lower()
        
        # Check keywords in reverse order (most complex first)
        for complexity in reversed(list(TaskComplexity)):
            keywords = cls.COMPLEXITY_KEYWORDS.get(complexity, [])
            if any(kw in task_lower for kw in keywords):
                min_iter, max_iter = cls.COMPLEXITY_LIMITS[complexity]
                return complexity, min_iter, max_iter
        
        # Default to moderate
        return TaskComplexity.MODERATE, 10, 30
    
    @classmethod
    def adjust_based_on_progress(
        cls,
        current_iteration: int,
        current_max: int,
        progress_score: float,
        success_rate: float
    ) -> int:
        """
        Dynamically adjust max iterations based on progress
        """
        # If making good progress with high success, allow more iterations
        if progress_score > 0.7 and success_rate > 0.8:
            return min(current_max + 10, 100)
        
        # If struggling but still making some progress, maintain
        if progress_score > 0.4:
            return current_max
        
        # If not making progress, reduce to finish sooner
        if current_iteration > 10 and progress_score < 0.3:
            return max(current_iteration + 5, 15)
        
        return current_max


class AdaptiveStopPolicy:
    """
    Intelligent stop policy that combines multiple stopping criteria
    """
    
    def __init__(
        self,
        initial_max_iterations: int = 50,
        max_tokens: int = 100000,
        max_time_seconds: int = 600,
        max_consecutive_failures: int = 5,
        no_progress_window: int = 5,
        enable_loop_detection: bool = True,
        enable_adaptive_limits: bool = True
    ):
        self.initial_max_iterations = initial_max_iterations
        self.current_max_iterations = initial_max_iterations
        self.max_consecutive_failures = max_consecutive_failures
        self.enable_loop_detection = enable_loop_detection
        self.enable_adaptive_limits = enable_adaptive_limits
        
        self.progress_tracker = ProgressTracker(window_size=no_progress_window)
        self.loop_detector = LoopDetector()
        self.cost_tracker = CostTracker(max_tokens=max_tokens, max_time_seconds=max_time_seconds)
        
        self.consecutive_failures = 0
        self.current_iteration = 0
        self.task_complexity: Optional[TaskComplexity] = None
        self.stop_history: List[StopDecision] = []
        
    def initialize_for_task(self, task: str):
        """Initialize policy for a new task"""
        complexity, min_iter, max_iter = TaskComplexityAnalyzer.analyze(task)
        self.task_complexity = complexity
        
        if self.enable_adaptive_limits:
            # Start with min iterations, will expand if needed
            self.current_max_iterations = min_iter
            self._adaptive_ceiling = max_iter
        else:
            self.current_max_iterations = self.initial_max_iterations
            self._adaptive_ceiling = self.initial_max_iterations
        
        logger.info(
            f"Task complexity: {complexity.value}, "
            f"initial max: {self.current_max_iterations}, "
            f"ceiling: {self._adaptive_ceiling}"
        )
    
    def record_iteration(
        self,
        iteration: int,
        action_type: str,
        action_params: Dict[str, Any],
        output: Any,
        success: bool,
        execution_time_ms: int,
        token_cost: int = 0
    ):
        """Record an iteration for analysis"""
        self.current_iteration = iteration
        
        # Create snapshot
        action_hash = hashlib.md5(
            str(action_params).encode()
        ).hexdigest()[:8]
        output_hash = hashlib.md5(
            str(output)[:500].encode() if output else b""
        ).hexdigest()[:8]
        
        snapshot = IterationSnapshot(
            iteration=iteration,
            action_type=action_type,
            action_hash=action_hash,
            output_hash=output_hash,
            success=success,
            execution_time_ms=execution_time_ms,
            token_cost=token_cost
        )
        
        # Update trackers
        self.progress_tracker.record(snapshot, output)
        self.loop_detector.record(action_type, action_hash)
        self.cost_tracker.record(token_cost, execution_time_ms)
        
        # Track consecutive failures
        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
        
        # Adaptive iteration adjustment
        if self.enable_adaptive_limits and iteration > 0 and iteration % 5 == 0:
            self._adjust_max_iterations()
    
    def _adjust_max_iterations(self):
        """Dynamically adjust max iterations"""
        has_progress, progress_score, _ = self.progress_tracker.has_progress()
        stats = self.progress_tracker.get_statistics()
        success_rate = stats.get("recent_success_rate", 0.5)
        
        new_max = TaskComplexityAnalyzer.adjust_based_on_progress(
            self.current_iteration,
            self.current_max_iterations,
            progress_score,
            success_rate
        )
        
        # Don't exceed ceiling
        new_max = min(new_max, self._adaptive_ceiling)
        
        if new_max != self.current_max_iterations:
            logger.info(
                f"Adjusting max iterations: {self.current_max_iterations} -> {new_max} "
                f"(progress: {progress_score:.2f}, success: {success_rate:.2f})"
            )
            self.current_max_iterations = new_max
    
    def should_continue(self) -> StopDecision:
        """
        Evaluate all stopping criteria and decide whether to continue
        """
        # 1. Check iteration limit
        if self.current_iteration >= self.current_max_iterations:
            # Before stopping, check if we should expand
            if self.enable_adaptive_limits:
                has_progress, score, _ = self.progress_tracker.has_progress()
                if has_progress and score > 0.6 and self.current_max_iterations < self._adaptive_ceiling:
                    self.current_max_iterations = min(
                        self.current_max_iterations + 10,
                        self._adaptive_ceiling
                    )
                    logger.info(f"Extending max iterations to {self.current_max_iterations}")
                else:
                    return self._make_decision(
                        True, StopReason.MAX_ITERATIONS,
                        f"达到最大迭代次数 ({self.current_max_iterations})",
                        recommendation="考虑分解任务或提高复杂度估计"
                    )
            else:
                return self._make_decision(
                    True, StopReason.MAX_ITERATIONS,
                    f"达到最大迭代次数 ({self.current_max_iterations})"
                )
        
        # 2. Check cost limits
        exceeded, cost_msg = self.cost_tracker.check_limits()
        if exceeded:
            return self._make_decision(
                True, StopReason.MAX_COST,
                cost_msg,
                recommendation="任务可能过于复杂，考虑分步执行"
            )
        
        # 3. Check consecutive failures
        if self.consecutive_failures >= self.max_consecutive_failures:
            return self._make_decision(
                True, StopReason.CONSECUTIVE_FAILURES,
                f"连续失败 {self.consecutive_failures} 次",
                recommendation="检查任务描述或环境配置"
            )
        
        # 4. Check loop detection
        if self.enable_loop_detection:
            is_looping, pattern, count = self.loop_detector.detect_loop()
            if is_looping:
                return self._make_decision(
                    True, StopReason.LOOP_DETECTED,
                    f"检测到循环模式: {pattern} (重复 {count} 次)",
                    recommendation="Agent 陷入循环，需要不同的方法"
                )
        
        # 5. Check progress (after enough iterations)
        if self.current_iteration >= 5:
            has_progress, score, explanation = self.progress_tracker.has_progress()
            if not has_progress:
                return self._make_decision(
                    True, StopReason.NO_PROGRESS,
                    f"未检测到进展: {explanation}",
                    confidence=0.8,
                    recommendation="任务可能需要重新描述或手动干预"
                )
        
        # 6. Check convergence (diminishing returns)
        if self.current_iteration >= 10:
            stats = self.progress_tracker.get_statistics()
            recent_success = stats.get("recent_success_rate", 1.0)
            if recent_success < 0.2:
                return self._make_decision(
                    True, StopReason.CONVERGENCE,
                    "任务收敛：最近成功率过低",
                    confidence=0.7,
                    recommendation="考虑更换策略或模型"
                )
        
        # Continue execution
        return self._make_decision(
            False, None,
            f"继续执行 (迭代 {self.current_iteration}/{self.current_max_iterations})"
        )
    
    def _make_decision(
        self,
        should_stop: bool,
        reason: Optional[StopReason],
        message: str,
        confidence: float = 1.0,
        recommendation: Optional[str] = None
    ) -> StopDecision:
        """Create and record a stop decision"""
        decision = StopDecision(
            should_stop=should_stop,
            reason=reason,
            message=message,
            confidence=confidence,
            recommendation=recommendation
        )
        self.stop_history.append(decision)
        return decision
    
    def force_stop(self, reason: StopReason, message: str) -> StopDecision:
        """Force a stop (e.g., user abort, error)"""
        return self._make_decision(True, reason, message)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        return {
            "current_iteration": self.current_iteration,
            "max_iterations": self.current_max_iterations,
            "adaptive_ceiling": self._adaptive_ceiling if hasattr(self, '_adaptive_ceiling') else None,
            "task_complexity": self.task_complexity.value if self.task_complexity else None,
            "consecutive_failures": self.consecutive_failures,
            "progress": self.progress_tracker.get_statistics(),
            "cost": self.cost_tracker.get_statistics(),
            "detected_loops": self.loop_detector.get_detected_loops(),
            "stop_decisions": [d.to_dict() for d in self.stop_history[-5:]]
        }
    
    def get_summary(self) -> str:
        """Get a human-readable summary"""
        stats = self.get_statistics()
        lines = [
            f"迭代: {stats['current_iteration']}/{stats['max_iterations']}",
            f"任务复杂度: {stats['task_complexity']}",
            f"连续失败: {stats['consecutive_failures']}",
            f"成功率: {stats['progress'].get('success_rate', 0):.1%}",
        ]
        
        cost = stats['cost']
        lines.append(f"Token 使用: {cost['total_tokens']}/{cost['max_tokens']}")
        lines.append(f"时间: {cost['elapsed_seconds']:.0f}s/{cost['max_time_seconds']}s")
        
        if stats['detected_loops']:
            lines.append(f"检测到循环: {len(stats['detected_loops'])} 个")
        
        return "\n".join(lines)


def create_stop_policy(
    task: str,
    max_iterations: Optional[int] = None,
    max_tokens: int = 100000,
    max_time_seconds: int = 600,
    enable_adaptive: bool = True
) -> AdaptiveStopPolicy:
    """
    Factory function to create a properly configured stop policy
    """
    policy = AdaptiveStopPolicy(
        initial_max_iterations=max_iterations or 50,
        max_tokens=max_tokens,
        max_time_seconds=max_time_seconds,
        enable_adaptive_limits=enable_adaptive
    )
    policy.initialize_for_task(task)
    return policy
