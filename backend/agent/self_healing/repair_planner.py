"""
修复计划器 - 生成修复方案

负责：
1. 根据诊断结果生成修复计划
2. 选择修复策略
3. 生成具体修复动作
4. 评估修复风险
"""

import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

from .diagnostic_engine import DiagnosticResult, ProblemType, Severity

logger = logging.getLogger(__name__)


class RepairStrategy(Enum):
    """修复策略"""
    RETRY = "retry"                          # 简单重试
    SWITCH_MODEL = "switch_model"            # 切换模型
    SWITCH_MODE = "switch_mode"              # 切换模式（本地/远程）
    MODIFY_PROMPT = "modify_prompt"          # 修改提示词
    MODIFY_CODE = "modify_code"              # 修改代码
    ADD_FALLBACK = "add_fallback"            # 添加回退机制
    RESTART_SERVICE = "restart_service"      # 重启服务
    CLEAR_CONTEXT = "clear_context"          # 清理上下文
    ESCALATE = "escalate"                    # 升级到人工处理


class ActionType(Enum):
    """修复动作类型"""
    EXECUTE_SCRIPT = "execute_script"        # 执行脚本
    MODIFY_FILE = "modify_file"              # 修改文件
    CALL_API = "call_api"                    # 调用 API
    CHANGE_CONFIG = "change_config"          # 修改配置
    RESTART_PROCESS = "restart_process"      # 重启进程
    SEND_NOTIFICATION = "send_notification"  # 发送通知
    LLM_FIX = "llm_fix"                     # 调用 LLM 分析并修复


@dataclass
class RepairAction:
    """修复动作"""
    action_type: ActionType
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 30
    retry_count: int = 1
    rollback_action: Optional['RepairAction'] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "description": self.description,
            "parameters": self.parameters,
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "has_rollback": self.rollback_action is not None
        }


@dataclass
class RepairPlan:
    """修复计划"""
    problem: DiagnosticResult
    strategy: RepairStrategy
    actions: List[RepairAction]
    description: str
    estimated_success_rate: float = 0.5
    risk_level: str = "medium"  # low, medium, high
    requires_confirmation: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "problem_type": self.problem.problem_type.value,
            "strategy": self.strategy.value,
            "actions": [a.to_dict() for a in self.actions],
            "description": self.description,
            "estimated_success_rate": self.estimated_success_rate,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }


class RepairPlanner:
    """修复计划器"""
    
    # 问题类型 -> 修复策略映射
    STRATEGY_MAP: Dict[ProblemType, List[RepairStrategy]] = {
        ProblemType.TOOL_PARSE_FAILURE: [
            RepairStrategy.SWITCH_MODE,
            RepairStrategy.MODIFY_PROMPT,
            RepairStrategy.RETRY
        ],
        ProblemType.LLM_EMPTY_RESPONSE: [
            RepairStrategy.SWITCH_MODEL,
            RepairStrategy.MODIFY_PROMPT,
            RepairStrategy.RETRY
        ],
        ProblemType.FUNCTION_CALLING_FAILED: [
            RepairStrategy.SWITCH_MODE,
            RepairStrategy.MODIFY_CODE,
            RepairStrategy.ADD_FALLBACK
        ],
        ProblemType.LLM_CONNECTION_ERROR: [
            RepairStrategy.SWITCH_MODEL,
            RepairStrategy.RESTART_SERVICE,
            RepairStrategy.ESCALATE
        ],
        ProblemType.CONTEXT_LOST: [
            RepairStrategy.CLEAR_CONTEXT,
            RepairStrategy.RETRY
        ],
        ProblemType.LLM_TIMEOUT: [
            RepairStrategy.RETRY,
            RepairStrategy.SWITCH_MODEL
        ],
        ProblemType.SCRIPT_SYNTAX_ERROR: [
            RepairStrategy.MODIFY_CODE,
            RepairStrategy.RETRY
        ],
        ProblemType.SCRIPT_RUNTIME_ERROR: [
            RepairStrategy.MODIFY_CODE,
            RepairStrategy.ADD_FALLBACK
        ],
        ProblemType.PERMISSION_DENIED: [
            RepairStrategy.ESCALATE
        ],
    }
    
    def __init__(self, strategy_db: Optional[Dict[str, Any]] = None):
        """
        初始化修复计划器
        
        Args:
            strategy_db: 策略数据库，用于学习历史修复效果
        """
        self.strategy_db = strategy_db or {}
        self.plan_history: List[RepairPlan] = []
    
    def create_plan(
        self,
        diagnostic: DiagnosticResult,
        context: Optional[Dict[str, Any]] = None
    ) -> RepairPlan:
        """
        创建修复计划
        
        Args:
            diagnostic: 诊断结果
            context: 额外上下文
        
        Returns:
            RepairPlan: 修复计划
        """
        context = context or {}
        
        # 1. 选择修复策略
        strategy = self._select_strategy(diagnostic, context)
        
        # 2. 生成修复动作
        actions = self._generate_actions(diagnostic, strategy, context)
        
        # 3. 评估成功率和风险
        success_rate = self._estimate_success_rate(diagnostic, strategy)
        risk_level = self._assess_risk(actions)
        
        # 4. 生成计划描述
        description = self._generate_description(diagnostic, strategy, actions)
        
        # 5. 判断是否需要人工确认
        requires_confirmation = (
            risk_level == "high" or
            diagnostic.severity == Severity.CRITICAL or
            strategy == RepairStrategy.MODIFY_CODE
        )
        
        plan = RepairPlan(
            problem=diagnostic,
            strategy=strategy,
            actions=actions,
            description=description,
            estimated_success_rate=success_rate,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            metadata=context
        )
        
        self.plan_history.append(plan)
        logger.info(f"Created repair plan: {strategy.value} with {len(actions)} actions")
        
        return plan
    
    def _select_strategy(
        self,
        diagnostic: DiagnosticResult,
        context: Dict[str, Any]
    ) -> RepairStrategy:
        """选择修复策略"""
        problem_type = diagnostic.problem_type
        
        # 获取该问题类型的可选策略
        strategies = self.STRATEGY_MAP.get(problem_type, [RepairStrategy.RETRY])
        
        if not strategies:
            return RepairStrategy.ESCALATE
        
        # 检查策略历史效果
        best_strategy = strategies[0]
        best_score = 0.0
        
        for strategy in strategies:
            key = f"{problem_type.value}:{strategy.value}"
            if key in self.strategy_db:
                record = self.strategy_db[key]
                score = record.get("success_rate", 0.5)
                if score > best_score:
                    best_score = score
                    best_strategy = strategy
        
        # 考虑上下文因素
        if context.get("local_model_active"):
            # 本地模型激活时，优先切换模式
            if RepairStrategy.SWITCH_MODE in strategies:
                return RepairStrategy.SWITCH_MODE
        
        if context.get("retry_count", 0) >= 2:
            # 已重试多次，避免继续重试
            if best_strategy == RepairStrategy.RETRY and len(strategies) > 1:
                return strategies[1]
        
        return best_strategy
    
    def _generate_actions(
        self,
        diagnostic: DiagnosticResult,
        strategy: RepairStrategy,
        context: Dict[str, Any]
    ) -> List[RepairAction]:
        """生成修复动作"""
        actions = []
        
        if strategy == RepairStrategy.RETRY:
            actions.append(RepairAction(
                action_type=ActionType.CALL_API,
                description="重新发送请求",
                parameters={
                    "endpoint": "chat",
                    "retry_with_backoff": True
                },
                retry_count=3
            ))
        
        elif strategy == RepairStrategy.SWITCH_MODE:
            # 切换本地/远程模式
            current_mode = context.get("current_mode", "remote")
            new_mode = "local" if current_mode == "remote" else "remote"
            
            actions.append(RepairAction(
                action_type=ActionType.CHANGE_CONFIG,
                description=f"切换到{new_mode}模式",
                parameters={
                    "config_key": "use_local_mode",
                    "new_value": new_mode == "local"
                }
            ))
            
            if new_mode == "local":
                # 如果切换到本地模式，确保使用 LocalToolParser
                actions.append(RepairAction(
                    action_type=ActionType.CHANGE_CONFIG,
                    description="启用本地工具解析器",
                    parameters={
                        "config_key": "use_local_tool_parser",
                        "new_value": True
                    }
                ))
        
        elif strategy == RepairStrategy.SWITCH_MODEL:
            actions.append(RepairAction(
                action_type=ActionType.CALL_API,
                description="检查可用模型",
                parameters={
                    "endpoint": "/local-llm/status"
                }
            ))
            
            actions.append(RepairAction(
                action_type=ActionType.CHANGE_CONFIG,
                description="切换到备用模型",
                parameters={
                    "config_key": "model",
                    "fallback_providers": ["ollama", "lmstudio", "deepseek"]
                }
            ))
        
        elif strategy == RepairStrategy.MODIFY_PROMPT:
            actions.append(RepairAction(
                action_type=ActionType.LLM_FIX,
                description="调用 LLM 优化系统提示词",
                parameters={
                    "fix_type": "prompt_optimization",
                    "error_message": diagnostic.description,
                    "problem_type": diagnostic.problem_type.value,
                    "suggestions": diagnostic.suggestions,
                },
                timeout_seconds=60,
            ))
        
        elif strategy == RepairStrategy.MODIFY_CODE:
            actions.append(RepairAction(
                action_type=ActionType.LLM_FIX,
                description="调用 LLM 分析错误并生成代码修复",
                parameters={
                    "fix_type": "code_fix",
                    "error_message": diagnostic.description,
                    "problem_type": diagnostic.problem_type.value,
                    "source_file": diagnostic.source_file,
                    "source_line": diagnostic.source_line,
                    "suggestions": diagnostic.suggestions,
                },
                timeout_seconds=120,
                requires_confirmation=True,
            ))
        
        elif strategy == RepairStrategy.ADD_FALLBACK:
            actions.append(RepairAction(
                action_type=ActionType.LLM_FIX,
                description="调用 LLM 生成回退机制",
                parameters={
                    "fix_type": "add_fallback",
                    "error_message": diagnostic.description,
                    "problem_type": diagnostic.problem_type.value,
                    "suggestions": diagnostic.suggestions,
                },
                timeout_seconds=60,
            ))
        
        elif strategy == RepairStrategy.RESTART_SERVICE:
            service_name = context.get("service_name", "backend")
            
            actions.append(RepairAction(
                action_type=ActionType.RESTART_PROCESS,
                description=f"重启 {service_name} 服务",
                parameters={
                    "service": service_name,
                    "wait_seconds": 5
                }
            ))
        
        elif strategy == RepairStrategy.CLEAR_CONTEXT:
            actions.append(RepairAction(
                action_type=ActionType.CALL_API,
                description="清理并重建上下文",
                parameters={
                    "endpoint": "/context/rebuild",
                    "session_id": context.get("session_id")
                }
            ))
        
        elif strategy == RepairStrategy.ESCALATE:
            actions.append(RepairAction(
                action_type=ActionType.SEND_NOTIFICATION,
                description="问题需要人工处理",
                parameters={
                    "message": f"自动修复失败: {diagnostic.description}",
                    "severity": diagnostic.severity.name
                }
            ))
        
        return actions
    
    def _estimate_success_rate(
        self,
        diagnostic: DiagnosticResult,
        strategy: RepairStrategy
    ) -> float:
        """估计修复成功率"""
        # 基于历史数据估计
        key = f"{diagnostic.problem_type.value}:{strategy.value}"
        
        if key in self.strategy_db:
            return self.strategy_db[key].get("success_rate", 0.5)
        
        # 默认估计
        default_rates = {
            RepairStrategy.RETRY: 0.3,
            RepairStrategy.SWITCH_MODE: 0.7,
            RepairStrategy.SWITCH_MODEL: 0.6,
            RepairStrategy.MODIFY_PROMPT: 0.5,
            RepairStrategy.MODIFY_CODE: 0.4,
            RepairStrategy.ADD_FALLBACK: 0.6,
            RepairStrategy.RESTART_SERVICE: 0.8,
            RepairStrategy.CLEAR_CONTEXT: 0.7,
            RepairStrategy.ESCALATE: 0.0,
        }
        
        return default_rates.get(strategy, 0.5)
    
    def _assess_risk(self, actions: List[RepairAction]) -> str:
        """评估修复风险"""
        high_risk_actions = {
            ActionType.MODIFY_FILE,
            ActionType.RESTART_PROCESS,
        }
        
        medium_risk_actions = {
            ActionType.EXECUTE_SCRIPT,
            ActionType.CHANGE_CONFIG,
        }
        
        for action in actions:
            if action.action_type in high_risk_actions:
                return "high"
        
        for action in actions:
            if action.action_type in medium_risk_actions:
                return "medium"
        
        return "low"
    
    def _generate_description(
        self,
        diagnostic: DiagnosticResult,
        strategy: RepairStrategy,
        actions: List[RepairAction]
    ) -> str:
        """生成计划描述"""
        strategy_descriptions = {
            RepairStrategy.RETRY: "重试操作",
            RepairStrategy.SWITCH_MODE: "切换运行模式",
            RepairStrategy.SWITCH_MODEL: "切换 LLM 模型",
            RepairStrategy.MODIFY_PROMPT: "优化提示词",
            RepairStrategy.MODIFY_CODE: "修改代码",
            RepairStrategy.ADD_FALLBACK: "添加回退机制",
            RepairStrategy.RESTART_SERVICE: "重启服务",
            RepairStrategy.CLEAR_CONTEXT: "清理上下文",
            RepairStrategy.ESCALATE: "升级到人工处理",
        }
        
        base_desc = strategy_descriptions.get(strategy, "执行修复")
        action_count = len(actions)
        
        return f"针对 [{diagnostic.problem_type.value}] 问题，采用「{base_desc}」策略，包含 {action_count} 个修复动作"
    
    def update_strategy_effectiveness(
        self,
        problem_type: ProblemType,
        strategy: RepairStrategy,
        success: bool
    ):
        """更新策略有效性"""
        key = f"{problem_type.value}:{strategy.value}"
        
        if key not in self.strategy_db:
            self.strategy_db[key] = {
                "attempts": 0,
                "successes": 0,
                "success_rate": 0.5
            }
        
        record = self.strategy_db[key]
        record["attempts"] += 1
        if success:
            record["successes"] += 1
        
        # 使用指数移动平均更新成功率
        alpha = 0.3  # 学习率
        current_rate = record["success_rate"]
        new_observation = 1.0 if success else 0.0
        record["success_rate"] = current_rate * (1 - alpha) + new_observation * alpha
        
        logger.info(f"Updated strategy effectiveness: {key} -> {record['success_rate']:.2f}")


# 全局实例
_repair_planner: Optional[RepairPlanner] = None


def get_repair_planner() -> RepairPlanner:
    """获取修复计划器单例"""
    global _repair_planner
    if _repair_planner is None:
        _repair_planner = RepairPlanner()
    return _repair_planner
