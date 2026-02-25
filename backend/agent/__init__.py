from .core import AgentCore
from .llm_client import LLMClient, LLMConfig
from .autonomous_agent import AutonomousAgent
from .action_schema import (
    AgentAction, ActionType, ActionStatus, ActionResult,
    ActionLog, TaskContext
)
from .reflect_engine import ReflectEngine, get_reflect_engine
from .episodic_memory import (
    EpisodicMemory, Episode, StrategyDB,
    get_episodic_memory, get_strategy_db
)
from .local_llm_manager import (
    LocalLLMManager, LocalLLMProvider, LocalLLMConfig,
    get_local_llm_manager, get_best_local_llm_client
)
from .model_selector import (
    ModelSelector, ModelType, TaskType, TaskAnalysis,
    ModelSelection, get_model_selector
)
from .local_tool_parser import (
    LocalToolParser, is_local_model, get_system_prompt_for_provider,
    LOCAL_MODEL_SYSTEM_PROMPT_V2,
)
from .runtime_v2 import AgentRuntimeV2
from .context_enhancer import ContextEnhancer, get_context_enhancer
from .task_context_manager import (
    TaskContext as AppTaskContext,  # Chat 任务上下文，与 action_schema.TaskContext 区分
    TaskStatus,
    extract_explicit_target,
    resolve_task,
    bind_target_to_tool_args,
)
from .agent_state import get_current_task, set_current_task, clear_current_task
from .self_healing import (
    SelfHealingAgent, get_self_healing_agent,
    DiagnosticEngine, get_diagnostic_engine,
    RepairPlanner, get_repair_planner,
    RepairExecutor, get_repair_executor,
    RepairValidator, get_repair_validator,
    ProblemType, HealingResult
)
from .stop_policy import (
    AdaptiveStopPolicy, StopReason, StopDecision,
    TaskComplexity, ProgressTracker, LoopDetector,
    CostTracker, create_stop_policy
)
from .web_augmented_thinking import (
    ThinkingAugmenter, WebAugmentedAgent,
    AugmentationType, AugmentationContext
)
from .self_upgrade import (
    ImplementationStrategy,
    UpgradeStage,
    UpgradePlan,
    UpgradeTask,
    SelfUpgradeOrchestrator,
    upgrade,
    get_orchestrator as get_self_upgrade_orchestrator,
)

__all__ = [
    "AgentCore",
    "LLMClient",
    "LLMConfig",
    "AutonomousAgent",
    "AgentAction",
    "ActionType",
    "ActionStatus",
    "ActionResult",
    "ActionLog",
    "TaskContext",
    "ReflectEngine",
    "get_reflect_engine",
    "EpisodicMemory",
    "Episode",
    "StrategyDB",
    "get_episodic_memory",
    "get_strategy_db",
    "LocalLLMManager",
    "LocalLLMProvider",
    "LocalLLMConfig",
    "get_local_llm_manager",
    "get_best_local_llm_client",
    # Model Selector
    "ModelSelector",
    "ModelType",
    "TaskType",
    "TaskAnalysis",
    "ModelSelection",
    "get_model_selector",
    # Local Tool Parser
    "LocalToolParser",
    "is_local_model",
    "get_system_prompt_for_provider",
    "LOCAL_MODEL_SYSTEM_PROMPT_V2",
    "AgentRuntimeV2",
    # Context Enhancer
    "ContextEnhancer",
    "get_context_enhancer",
    # Task Context (target isolation, Chat 模式)
    "AppTaskContext",
    "TaskStatus",
    "extract_explicit_target",
    "resolve_task",
    "bind_target_to_tool_args",
    "get_current_task",
    "set_current_task",
    "clear_current_task",
    # Self-Healing System
    "SelfHealingAgent",
    "get_self_healing_agent",
    "DiagnosticEngine",
    "get_diagnostic_engine",
    "RepairPlanner",
    "get_repair_planner",
    "RepairExecutor",
    "get_repair_executor",
    "RepairValidator",
    "get_repair_validator",
    "ProblemType",
    "HealingResult",
    # Adaptive Stop Policy
    "AdaptiveStopPolicy",
    "StopReason",
    "StopDecision",
    "TaskComplexity",
    "ProgressTracker",
    "LoopDetector",
    "CostTracker",
    "create_stop_policy",
    # Web Augmented Thinking
    "ThinkingAugmenter",
    "WebAugmentedAgent",
    "AugmentationType",
    "AugmentationContext",
    # Self-Upgrade
    "ImplementationStrategy",
    "UpgradeStage",
    "UpgradePlan",
    "UpgradeTask",
    "SelfUpgradeOrchestrator",
    "upgrade",
    "get_self_upgrade_orchestrator",
]
