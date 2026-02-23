"""
Self-Healing Agent System

自我修复 Agent 系统，能够：
1. 检测运行时问题
2. 分析问题类型
3. 生成修复计划
4. 执行修复
5. 验证结果
6. 学习并更新策略
"""

from .diagnostic_engine import (
    DiagnosticEngine, 
    ProblemType, 
    DiagnosticResult,
    Severity,
    get_diagnostic_engine
)
from .repair_planner import (
    RepairPlanner, 
    RepairPlan, 
    RepairAction,
    RepairStrategy,
    get_repair_planner
)
from .repair_executor import (
    RepairExecutor, 
    ExecutionResult,
    ExecutionStatus,
    get_repair_executor
)
from .repair_validator import (
    RepairValidator, 
    ValidationResult,
    ValidationStatus,
    get_repair_validator
)
from .self_healing_agent import (
    SelfHealingAgent, 
    HealingResult,
    HealingStatus,
    get_self_healing_agent
)

__all__ = [
    # Diagnostic Engine
    "DiagnosticEngine",
    "ProblemType", 
    "DiagnosticResult",
    "Severity",
    "get_diagnostic_engine",
    # Repair Planner
    "RepairPlanner",
    "RepairPlan",
    "RepairAction",
    "RepairStrategy",
    "get_repair_planner",
    # Repair Executor
    "RepairExecutor",
    "ExecutionResult",
    "ExecutionStatus",
    "get_repair_executor",
    # Repair Validator
    "RepairValidator",
    "ValidationResult",
    "ValidationStatus",
    "get_repair_validator",
    # Self-Healing Agent
    "SelfHealingAgent",
    "HealingResult",
    "HealingStatus",
    "get_self_healing_agent",
]
