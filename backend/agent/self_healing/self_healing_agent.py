"""
自愈 Agent - 整合所有自我修复能力

这是自我修复系统的核心组件，负责：
1. 监控系统运行状态
2. 检测问题并触发修复流程
3. 协调诊断、计划、执行、验证
4. 学习并优化修复策略
5. 维护修复历史和统计
"""

import asyncio
import logging
import json
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, AsyncGenerator
from datetime import datetime
from pathlib import Path

from .diagnostic_engine import (
    DiagnosticEngine, DiagnosticResult, ProblemType, Severity,
    get_diagnostic_engine
)
from .repair_planner import (
    RepairPlanner, RepairPlan, RepairStrategy,
    get_repair_planner
)
from .repair_executor import (
    RepairExecutor, ExecutionResult, ExecutionStatus,
    get_repair_executor
)
from .repair_validator import (
    RepairValidator, ValidationResult, ValidationStatus,
    get_repair_validator
)

logger = logging.getLogger(__name__)


class HealingStatus(Enum):
    """修复状态"""
    IDLE = "idle"
    DIAGNOSING = "diagnosing"
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    LEARNING = "learning"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class HealingResult:
    """修复结果"""
    status: HealingStatus
    diagnostic: Optional[DiagnosticResult] = None
    plan: Optional[RepairPlan] = None
    execution: Optional[ExecutionResult] = None
    validation: Optional[ValidationResult] = None
    success: bool = False
    iterations: int = 1
    total_duration_ms: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    lessons_learned: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "diagnostic": self.diagnostic.to_dict() if self.diagnostic else None,
            "plan": self.plan.to_dict() if self.plan else None,
            "execution": self.execution.to_dict() if self.execution else None,
            "validation": self.validation.to_dict() if self.validation else None,
            "success": self.success,
            "iterations": self.iterations,
            "total_duration_ms": self.total_duration_ms,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "lessons_learned": self.lessons_learned
        }


class SelfHealingAgent:
    """
    自愈 Agent
    
    实现自动问题检测和修复的完整流程：
    发现问题 -> 分析任务类型 -> 生成修复计划 -> 执行修复 -> 验证结果 -> 更新策略
    """
    
    def __init__(
        self,
        diagnostic_engine: Optional[DiagnosticEngine] = None,
        repair_planner: Optional[RepairPlanner] = None,
        repair_executor: Optional[RepairExecutor] = None,
        repair_validator: Optional[RepairValidator] = None,
        max_iterations: int = 3,
        auto_heal: bool = True,
        strategy_db_path: Optional[str] = None
    ):
        """
        初始化自愈 Agent
        
        Args:
            diagnostic_engine: 诊断引擎
            repair_planner: 修复计划器
            repair_executor: 修复执行器
            repair_validator: 修复验证器
            max_iterations: 最大修复迭代次数
            auto_heal: 是否自动修复
            strategy_db_path: 策略数据库路径
        """
        self.diagnostic = diagnostic_engine or get_diagnostic_engine()
        self.planner = repair_planner or get_repair_planner()
        self.executor = repair_executor or get_repair_executor()
        self.validator = repair_validator or get_repair_validator()
        
        self.max_iterations = max_iterations
        self.auto_heal = auto_heal
        self.strategy_db_path = strategy_db_path or "data/strategy_db.json"
        
        self.current_status = HealingStatus.IDLE
        self.healing_history: List[HealingResult] = []
        
        # 加载策略数据库
        self._load_strategy_db()
    
    async def heal(
        self,
        error_message: str,
        stack_trace: str = "",
        context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行自愈流程（流式输出）
        
        Args:
            error_message: 错误消息
            stack_trace: 堆栈跟踪
            context: 额外上下文
        
        Yields:
            流式输出修复进度
        """
        context = context or {}
        result = HealingResult(status=HealingStatus.IDLE)
        iteration = 0
        
        logger.info(f"Self-healing started for error: {error_message[:100]}...")
        
        try:
            while iteration < self.max_iterations:
                iteration += 1
                result.iterations = iteration
                
                # 阶段 1: 诊断
                self.current_status = HealingStatus.DIAGNOSING
                yield {
                    "type": "status",
                    "status": "diagnosing",
                    "iteration": iteration,
                    "message": "正在诊断问题..."
                }
                
                diagnostic = self.diagnostic.diagnose(
                    error_message, stack_trace, context
                )
                result.diagnostic = diagnostic
                
                yield {
                    "type": "diagnostic",
                    "problem_type": diagnostic.problem_type.value,
                    "severity": diagnostic.severity.name,
                    "description": diagnostic.description,
                    "suggestions": diagnostic.suggestions
                }
                
                # 阶段 2: 计划
                self.current_status = HealingStatus.PLANNING
                yield {
                    "type": "status",
                    "status": "planning",
                    "message": "正在生成修复计划..."
                }
                
                context["retry_count"] = iteration - 1
                plan = self.planner.create_plan(diagnostic, context)
                result.plan = plan
                
                yield {
                    "type": "plan",
                    "strategy": plan.strategy.value,
                    "description": plan.description,
                    "actions": [a.to_dict() for a in plan.actions],
                    "estimated_success_rate": plan.estimated_success_rate,
                    "risk_level": plan.risk_level,
                    "requires_confirmation": plan.requires_confirmation
                }
                
                # 如果需要确认，等待用户确认
                if plan.requires_confirmation and not context.get("auto_confirm"):
                    yield {
                        "type": "confirmation_required",
                        "message": f"修复计划风险等级为 {plan.risk_level}，需要确认是否执行"
                    }
                    # 等待确认（实际实现中需要等待用户输入）
                    if not context.get("confirmed"):
                        yield {
                            "type": "status",
                            "status": "waiting_confirmation",
                            "message": "等待用户确认..."
                        }
                        # 这里可以添加超时逻辑
                
                # 阶段 3: 执行
                self.current_status = HealingStatus.EXECUTING
                yield {
                    "type": "status",
                    "status": "executing",
                    "message": f"正在执行修复计划 ({len(plan.actions)} 个动作)..."
                }
                
                execution = await self.executor.execute(plan)
                result.execution = execution
                
                yield {
                    "type": "execution",
                    "status": execution.status.value,
                    "total_duration_ms": execution.total_duration_ms,
                    "action_results": [r.to_dict() for r in execution.action_results]
                }
                
                # 阶段 4: 验证
                self.current_status = HealingStatus.VALIDATING
                yield {
                    "type": "status",
                    "status": "validating",
                    "message": "正在验证修复结果..."
                }
                
                validation = await self.validator.validate(plan, execution, context)
                result.validation = validation
                
                yield {
                    "type": "validation",
                    "status": validation.status.value,
                    "overall_score": validation.overall_score,
                    "checks": [c.to_dict() for c in validation.checks],
                    "recommendations": validation.recommendations
                }
                
                # 阶段 5: 学习
                self.current_status = HealingStatus.LEARNING
                
                success = validation.status == ValidationStatus.PASSED
                self.planner.update_strategy_effectiveness(
                    diagnostic.problem_type,
                    plan.strategy,
                    success
                )
                
                lessons = self._extract_lessons(result)
                result.lessons_learned = lessons
                
                yield {
                    "type": "learning",
                    "success": success,
                    "lessons_learned": lessons
                }
                
                # 保存策略数据库
                self._save_strategy_db()
                
                # 判断是否成功
                if success:
                    result.status = HealingStatus.COMPLETED
                    result.success = True
                    break
                
                # 如果失败，准备下一次迭代
                if iteration < self.max_iterations:
                    yield {
                        "type": "retry",
                        "iteration": iteration + 1,
                        "message": f"修复未完全成功，尝试第 {iteration + 1} 次修复..."
                    }
                    # 更新上下文，避免重复相同策略
                    context["previous_strategy"] = plan.strategy.value
                    context["previous_score"] = validation.overall_score
        
        except Exception as e:
            logger.error(f"Self-healing failed with exception: {e}")
            result.status = HealingStatus.FAILED
            yield {
                "type": "error",
                "message": f"自愈过程出错: {str(e)}"
            }
        
        finally:
            result.completed_at = datetime.now()
            result.total_duration_ms = int(
                (result.completed_at - result.started_at).total_seconds() * 1000
            )
            
            if result.status != HealingStatus.COMPLETED:
                result.status = HealingStatus.FAILED
            
            self.healing_history.append(result)
            self.current_status = HealingStatus.IDLE
            
            yield {
                "type": "completed",
                "success": result.success,
                "total_duration_ms": result.total_duration_ms,
                "iterations": result.iterations,
                "final_status": result.status.value
            }
    
    async def heal_sync(
        self,
        error_message: str,
        stack_trace: str = "",
        context: Optional[Dict[str, Any]] = None
    ) -> HealingResult:
        """
        同步执行自愈流程
        
        Args:
            error_message: 错误消息
            stack_trace: 堆栈跟踪
            context: 额外上下文
        
        Returns:
            HealingResult: 修复结果
        """
        result = None
        async for update in self.heal(error_message, stack_trace, context):
            if update["type"] == "completed":
                # 从历史中获取最后一个结果
                result = self.healing_history[-1] if self.healing_history else None
        return result
    
    def diagnose_only(
        self,
        error_message: str,
        stack_trace: str = "",
        context: Optional[Dict[str, Any]] = None
    ) -> DiagnosticResult:
        """仅执行诊断，不修复"""
        return self.diagnostic.diagnose(error_message, stack_trace, context)
    
    def plan_only(
        self,
        diagnostic: DiagnosticResult,
        context: Optional[Dict[str, Any]] = None
    ) -> RepairPlan:
        """仅生成修复计划，不执行"""
        return self.planner.create_plan(diagnostic, context)
    
    def _extract_lessons(self, result: HealingResult) -> List[str]:
        """从修复结果中提取经验教训"""
        lessons = []
        
        if result.diagnostic:
            lessons.append(
                f"问题类型 [{result.diagnostic.problem_type.value}] "
                f"严重性 [{result.diagnostic.severity.name}]"
            )
        
        if result.plan:
            lessons.append(
                f"采用策略 [{result.plan.strategy.value}] "
                f"预估成功率 [{result.plan.estimated_success_rate:.2f}]"
            )
        
        if result.validation:
            actual_success = result.validation.overall_score
            if result.plan:
                predicted = result.plan.estimated_success_rate
                if abs(actual_success - predicted) > 0.2:
                    lessons.append(
                        f"预估与实际差异较大: 预估 {predicted:.2f}, 实际 {actual_success:.2f}"
                    )
            
            for check in result.validation.failed_checks:
                lessons.append(f"检查失败: {check.name} - {check.error_message or check.description}")
        
        if result.success:
            lessons.append("修复成功，策略有效")
        else:
            lessons.append("修复失败，需要尝试其他策略或人工干预")
        
        return lessons
    
    def _load_strategy_db(self):
        """加载策略数据库"""
        try:
            db_path = Path(self.strategy_db_path)
            if db_path.exists():
                with open(db_path, 'r') as f:
                    data = json.load(f)
                    self.planner.strategy_db = data
                    logger.info(f"Loaded strategy DB with {len(data)} entries")
        except Exception as e:
            logger.warning(f"Failed to load strategy DB: {e}")
    
    def _save_strategy_db(self):
        """保存策略数据库"""
        try:
            db_path = Path(self.strategy_db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(db_path, 'w') as f:
                json.dump(self.planner.strategy_db, f, indent=2)
            
            logger.info(f"Saved strategy DB to {db_path}")
        except Exception as e:
            logger.warning(f"Failed to save strategy DB: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取自愈统计"""
        total = len(self.healing_history)
        if total == 0:
            return {"total": 0}
        
        successful = len([h for h in self.healing_history if h.success])
        avg_iterations = sum(h.iterations for h in self.healing_history) / total
        avg_duration = sum(h.total_duration_ms for h in self.healing_history) / total
        
        # 按问题类型统计
        by_problem_type: Dict[str, Dict[str, int]] = {}
        for h in self.healing_history:
            if h.diagnostic:
                pt = h.diagnostic.problem_type.value
                if pt not in by_problem_type:
                    by_problem_type[pt] = {"total": 0, "success": 0}
                by_problem_type[pt]["total"] += 1
                if h.success:
                    by_problem_type[pt]["success"] += 1
        
        return {
            "total": total,
            "successful": successful,
            "failed": total - successful,
            "success_rate": successful / total,
            "average_iterations": avg_iterations,
            "average_duration_ms": avg_duration,
            "by_problem_type": by_problem_type,
            "strategy_db_size": len(self.planner.strategy_db)
        }
    
    def get_recent_healings(self, count: int = 10) -> List[Dict[str, Any]]:
        """获取最近的修复记录"""
        return [h.to_dict() for h in self.healing_history[-count:]]


# 全局实例
_self_healing_agent: Optional[SelfHealingAgent] = None


def get_self_healing_agent() -> SelfHealingAgent:
    """获取自愈 Agent 单例"""
    global _self_healing_agent
    if _self_healing_agent is None:
        _self_healing_agent = SelfHealingAgent()
    return _self_healing_agent
