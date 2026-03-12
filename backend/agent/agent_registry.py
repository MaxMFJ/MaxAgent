"""
Agent Registry + Factory Pattern — 子代理注册表与工厂模式

借鉴 DeerFlow SubagentExecutor + MacAgent 现有 Duck 系统:
  - AgentSpec: 子代理规格（prompt、技能、工具、资源限制）
  - AgentFactory: 从 AgentSpec 创建独立 AutonomousAgent 实例
  - AgentRegistry: 管理所有可用的 AgentSpec（内置 + 自定义）

设计:
  ┌───────────────────┐     ┌──────────────────┐
  │  AgentRegistry    │────▶│  AgentSpec (N)    │
  │  (singleton)      │     │  (type blueprint) │
  └───────┬───────────┘     └──────────────────┘
          │ create_agent(spec, llm)
  ┌───────▼───────────┐
  │  AgentFactory     │────▶ 独立 AutonomousAgent 实例
  │  (stateless)      │     （隔离 context、独立 LLM）
  └───────────────────┘

与既有 DuckTemplate 关系:
  DuckTemplate 是 UI 层模板（名称、图标、描述）
  AgentSpec 是执行层规格（prompt、技能、工具限制、资源限额）
  一个 DuckType → 对应一个 AgentSpec
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent.autonomous_agent import AutonomousAgent
    from agent.llm_client import LLMClient

logger = logging.getLogger(__name__)


# ─── Agent 规格定义 ──────────────────────────────────────────────

@dataclass
class AgentSpec:
    """
    子代理规格 — 描述如何创建和配置一个专项子代理

    这是执行层蓝图，包含 prompt 模板、技能绑定、工具白名单、
    资源限制等所有创建独立 agent 实例所需的信息。
    """
    # 基本标识
    agent_type: str                            # 唯一类型标识 (e.g. "coder", "crawler")
    name: str                                  # 显示名称
    description: str = ""                      # 功能描述

    # Prompt 配置
    system_prompt: str = ""                    # 基础 system prompt
    role_instruction: str = ""                 # 角色定义（注入 Duck identity block）
    execution_rules: str = ""                  # 额外执行规则

    # 技能与工具
    skills: List[str] = field(default_factory=list)       # 技能标签
    allowed_tools: List[str] = field(default_factory=list) # 工具白名单（空=全部可用）
    blocked_tools: List[str] = field(default_factory=list) # 工具黑名单

    # 资源限制（对齐 DeerFlow 的 per-subagent 限制）
    max_iterations: int = 30                   # 最大迭代次数
    max_time_seconds: int = 900                # 最大执行时长（秒）
    max_tokens: int = 80000                    # token 预算

    # 行为配置
    enable_reflection: bool = True             # 是否启用反思
    enable_plan: bool = False                  # 是否生成子计划
    enable_model_selection: bool = False        # 是否启用模型选择

    # 扩展元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_type": self.agent_type,
            "name": self.name,
            "description": self.description,
            "skills": self.skills,
            "allowed_tools": self.allowed_tools,
            "max_iterations": self.max_iterations,
            "max_time_seconds": self.max_time_seconds,
        }


# ─── Agent 工厂 ──────────────────────────────────────────────────

class AgentFactory:
    """
    从 AgentSpec 创建独立的 AutonomousAgent 实例。
    每次调用返回全新实例，不共享状态。
    """

    @staticmethod
    def create(
        spec: AgentSpec,
        llm_client: "LLMClient",
        *,
        reflect_llm: Optional["LLMClient"] = None,
        local_llm: Optional["LLMClient"] = None,
        runtime_adapter: Optional[Any] = None,
        isolated_context: bool = False,
    ) -> "AutonomousAgent":
        """
        根据 AgentSpec 创建独立 Agent 实例

        Args:
            spec: 子代理规格
            llm_client: 主 LLM 客户端
            reflect_llm: 反思用 LLM（可选）
            local_llm: 本地 LLM（可选）
            runtime_adapter: 运行时适配器
            isolated_context: 是否隔离会话上下文（Duck 子代理应为 True）
        """
        from agent.autonomous_agent import AutonomousAgent

        agent = AutonomousAgent(
            llm_client=llm_client,
            local_llm_client=local_llm,
            reflect_llm=reflect_llm,
            runtime_adapter=runtime_adapter,
            max_iterations=spec.max_iterations,
            max_time_seconds=spec.max_time_seconds,
            max_tokens=spec.max_tokens,
            enable_reflection=spec.enable_reflection,
            enable_model_selection=spec.enable_model_selection,
            isolated_context=isolated_context,
        )

        logger.debug(f"AgentFactory: created {spec.agent_type} agent "
                      f"(max_iter={spec.max_iterations}, isolated={isolated_context}, skills={spec.skills})")
        return agent

    @staticmethod
    def create_from_main(
        spec: AgentSpec,
        llm_client: "LLMClient",
    ) -> "AutonomousAgent":
        """
        从主 Agent 继承环境信息创建子代理。
        主 Agent 的 reflect_llm / local_llm / runtime_adapter 会被继承。
        """
        try:
            from app_state import get_autonomous_agent
            main_agent = get_autonomous_agent()
            return AgentFactory.create(
                spec=spec,
                llm_client=llm_client,
                reflect_llm=getattr(main_agent, 'reflect_llm', None),
                local_llm=getattr(main_agent, 'local_llm', None),
                runtime_adapter=getattr(main_agent, 'runtime_adapter', None),
            )
        except Exception as e:
            logger.warning(f"Failed to inherit from main agent: {e}")
            return AgentFactory.create(spec=spec, llm_client=llm_client)


# ─── Agent 注册表 ────────────────────────────────────────────────

class AgentRegistry:
    """
    子代理类型注册表 — 管理所有可用的 AgentSpec。
    启动时注册内置类型，支持运行时动态注册自定义类型。
    """

    _instance: Optional["AgentRegistry"] = None

    def __init__(self):
        self._specs: Dict[str, AgentSpec] = {}
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "AgentRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize(self):
        """初始化内置 Agent 类型（从 DuckTemplate 桥接）"""
        if self._initialized:
            return
        self._register_builtins()
        self._initialized = True
        logger.info(f"AgentRegistry initialized: {len(self._specs)} agent types")

    def _register_builtins(self):
        """从 DuckTemplate 桥接内置类型到 AgentSpec"""
        try:
            from services.duck_template import BUILTIN_TEMPLATES
            for duck_type, template in BUILTIN_TEMPLATES.items():
                spec = AgentSpec(
                    agent_type=duck_type.value,
                    name=template.name,
                    description=template.description,
                    system_prompt=template.system_prompt,
                    skills=template.skills,
                    allowed_tools=template.required_tools,
                    role_instruction=f"你是 {template.name}，{template.description}。",
                )
                self._specs[spec.agent_type] = spec
        except Exception as e:
            logger.warning(f"Failed to load builtin templates: {e}")

    # ─── CRUD ────────────────────────────────────────

    def register(self, spec: AgentSpec) -> bool:
        """注册一个 Agent 类型规格"""
        if spec.agent_type in self._specs:
            logger.info(f"AgentRegistry: updating existing spec: {spec.agent_type}")
        self._specs[spec.agent_type] = spec
        return True

    def unregister(self, agent_type: str) -> bool:
        """移除一个 Agent 类型"""
        if agent_type in self._specs:
            del self._specs[agent_type]
            return True
        return False

    def get(self, agent_type: str) -> Optional[AgentSpec]:
        """获取指定类型的 AgentSpec"""
        return self._specs.get(agent_type)

    def list_all(self) -> List[AgentSpec]:
        """列出所有注册的 Agent 类型"""
        return list(self._specs.values())

    def find_by_skill(self, skill: str) -> List[AgentSpec]:
        """按技能查找 Agent 类型"""
        return [s for s in self._specs.values() if skill in s.skills]

    def find_best_for_task(self, task_description: str) -> Optional[AgentSpec]:
        """根据任务描述找到最匹配的 Agent 类型（简单关键词匹配）"""
        task_lower = task_description.lower()
        best_score = 0.0
        best_spec = None

        for spec in self._specs.values():
            score = 0.0
            # 技能关键词匹配
            for skill in spec.skills:
                if skill.lower() in task_lower:
                    score += 2.0
            # 描述词匹配
            desc_words = set(spec.description.lower().split())
            task_words = set(task_lower.split())
            overlap = len(desc_words & task_words)
            score += overlap * 0.5

            if score > best_score:
                best_score = score
                best_spec = spec

        return best_spec if best_score > 0 else None


# ─── 便捷函数 ────────────────────────────────────────────────────

def get_agent_registry() -> AgentRegistry:
    """获取全局 AgentRegistry 单例"""
    registry = AgentRegistry.get_instance()
    if not registry._initialized:
        registry.initialize()
    return registry
