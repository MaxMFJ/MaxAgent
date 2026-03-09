"""
RPA (Robotic Process Automation) 数据模型

用户可导入 YAML/JSON 格式的标准化执行流程，LLM 会在决策时感知可用的 Runbook
并优先推荐/调用对应流程，实现「一句话触发标准化自动化」的效果。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RunbookStep:
    """Runbook 中的单个执行步骤"""
    id: str
    description: str
    tool: str                           # e.g. "terminal", "file", "browser"
    args: Dict[str, Any] = field(default_factory=dict)
    condition: str = ""                 # Jinja2-like: "{{output.step_1.success}}"
    retry: int = 0                      # 失败重试次数
    timeout: int = 60                   # 单步超时（秒）
    fallback_step: str = ""             # 失败时跳转的步骤 id
    on_error: str = "abort"             # abort | continue | fallback

    @classmethod
    def from_dict(cls, d: dict) -> "RunbookStep":
        return cls(
            id=d.get("id", ""),
            description=d.get("description", ""),
            tool=d.get("tool", ""),
            args=d.get("args", {}),
            condition=d.get("condition", ""),
            retry=d.get("retry", 0),
            timeout=d.get("timeout", 60),
            fallback_step=d.get("fallback_step", ""),
            on_error=d.get("on_error", "abort"),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "tool": self.tool,
            "args": self.args,
            "condition": self.condition,
            "retry": self.retry,
            "timeout": self.timeout,
            "fallback_step": self.fallback_step,
            "on_error": self.on_error,
        }


@dataclass
class Runbook:
    """
    标准化自动化流程（Runbook Automation Procedure）

    支持 YAML/JSON 格式导入，存储在 backend/runbooks/ 目录。
    LLM 可通过 prompt 注入感知可用 Runbook，
    执行时逐步调用对应工具完成整个流程。
    """
    id: str
    name: str
    description: str
    category: str = "general"           # development / deployment / maintenance / …
    tags: List[str] = field(default_factory=list)
    steps: List[RunbookStep] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)    # 用户可自定义的参数
    outputs: Dict[str, Any] = field(default_factory=dict)   # 期望输出的描述
    prerequisites: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    author: str = ""
    source: str = "local"               # local | imported | github
    source_url: str = ""
    trusted: bool = True
    prefer_duck: bool = False          # True 时优先委派给 Duck 分身执行，实现「主 Agent 选 Runbook → Duck 执行」
    created_at: float = field(default_factory=time.time)

    # 运行时统计（内存中维护，不持久）
    execute_count: int = 0
    last_used: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Runbook":
        steps = [RunbookStep.from_dict(s) for s in d.get("steps", [])]
        return cls(
            id=d["id"],
            name=d.get("name", d["id"]),
            description=d.get("description", ""),
            category=d.get("category", "general"),
            tags=d.get("tags", []),
            steps=steps,
            inputs=d.get("inputs", {}),
            outputs=d.get("outputs", {}),
            prerequisites=d.get("prerequisites", {}),
            version=d.get("version", "1.0.0"),
            author=d.get("author", ""),
            source=d.get("source", "local"),
            source_url=d.get("source_url", ""),
            trusted=d.get("trusted", True),
            prefer_duck=d.get("prefer_duck", False),
        )

    def to_dict(self, include_steps: bool = True) -> dict:
        d: dict = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tags": self.tags,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "prerequisites": self.prerequisites,
            "version": self.version,
            "author": self.author,
            "source": self.source,
            "source_url": self.source_url,
            "trusted": self.trusted,
            "prefer_duck": self.prefer_duck,
            "created_at": self.created_at,
            "execute_count": self.execute_count,
            "last_used": self.last_used,
            "step_count": len(self.steps),
        }
        if include_steps:
            d["steps"] = [s.to_dict() for s in self.steps]
        return d
