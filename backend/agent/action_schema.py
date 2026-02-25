"""
Action Schema for Autonomous Agent
Defines structured actions that the agent can execute
"""

import json
import logging
import re
import uuid

from llm.json_repair import repair_json

logger = logging.getLogger(__name__)
from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime


class ActionType(Enum):
    """Types of actions the agent can execute"""
    RUN_SHELL = "run_shell"
    CREATE_AND_RUN_SCRIPT = "create_and_run_script"
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    MOVE_FILE = "move_file"
    COPY_FILE = "copy_file"
    DELETE_FILE = "delete_file"
    LIST_DIRECTORY = "list_directory"
    OPEN_APP = "open_app"
    CLOSE_APP = "close_app"
    GET_SYSTEM_INFO = "get_system_info"
    CLIPBOARD_READ = "clipboard_read"
    CLIPBOARD_WRITE = "clipboard_write"
    THINK = "think"
    FINISH = "finish"


class ActionStatus(Enum):
    """Status of action execution"""
    PENDING = "pending"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AgentAction:
    """
    Represents a single action to be executed by the agent
    """
    action_type: ActionType
    params: Dict[str, Any]
    reasoning: str
    action_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: ActionStatus = ActionStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "params": self.params,
            "reasoning": self.reasoning,
            "status": self.status.value,
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentAction":
        return cls(
            action_type=ActionType(data["action_type"]),
            params=data.get("params", {}),
            reasoning=data.get("reasoning", ""),
            action_id=data.get("action_id", str(uuid.uuid4())[:8]),
            status=ActionStatus(data.get("status", "pending"))
        )
    
    @classmethod
    def from_llm_response(cls, response_text: str) -> Optional["AgentAction"]:
        """Parse LLM response to extract action (supports DeepSeek/本地模型多种输出格式)"""
        if not response_text or not isinstance(response_text, str):
            return None
        text = response_text.strip()
        if not text:
            return None

        # 1. 提取所有 ```json ... ``` 或 ``` ... ``` 块，逐个尝试（DeepSeek 可能先输出总结再输出动作）
        for code_block in re.finditer(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text):
            parsed = cls._parse_json_to_action(code_block.group(1).strip())
            if parsed:
                return parsed

        # 2. 提取所有 { ... } 块，逐个尝试（从后往前，模型常把最终动作放在最后）
        blocks = cls._extract_brace_blocks(text)
        for candidate in reversed(blocks):
            parsed = cls._parse_json_to_action(candidate)
            if parsed:
                return parsed

        # 3. 使用 json_repair 从全文提取
        data = repair_json(text)
        if data:
            parsed = cls._dict_to_action(data)
            if parsed:
                return parsed

        # 4. 直接解析整段
        try:
            clean = text
            if clean.startswith("```json"):
                clean = clean[7:]
            if clean.startswith("```"):
                clean = clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()
            data = json.loads(clean)
            return cls._dict_to_action(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

        return None

    @staticmethod
    def _extract_brace_blocks(text: str) -> list[str]:
        """提取文本中所有完整的 { ... } JSON 对象块"""
        out = []
        depth = 0
        start = -1
        for i, c in enumerate(text):
            if c == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    out.append(text[start : i + 1])
                    start = -1
        return out

    @classmethod
    def _dict_to_action(cls, data: dict) -> Optional["AgentAction"]:
        """从 dict 构建 AgentAction"""
        if not isinstance(data, dict):
            return None
        action_type_str = (data.get("action_type") or data.get("action") or "").lower().strip()
        if not action_type_str:
            return None
        try:
            action_type = ActionType(action_type_str)
        except ValueError:
            return None
        params = data.get("params") or data.get("arguments") or {}
        if not isinstance(params, dict):
            params = {}
        reasoning = data.get("reasoning") or data.get("reason") or ""
        return cls(action_type=action_type, params=params, reasoning=reasoning)

    @classmethod
    def _parse_json_to_action(cls, raw: str) -> Optional["AgentAction"]:
        """解析 JSON 字符串为 AgentAction"""
        data = repair_json(raw)
        if data is None:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return None
        return cls._dict_to_action(data)


@dataclass
class ActionResult:
    """Result of executing an action"""
    action_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    execution_time_ms: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "success": self.success,
            "output": self.output if not isinstance(self.output, bytes) else str(self.output),
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class ActionLog:
    """Log entry for an executed action"""
    action: AgentAction
    result: ActionResult
    iteration: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.to_dict(),
            "result": self.result.to_dict(),
            "iteration": self.iteration
        }


@dataclass
class TaskContext:
    """Context for autonomous task execution"""
    task_id: str
    task_description: str
    action_logs: List[ActionLog] = field(default_factory=list)
    current_iteration: int = 0
    max_iterations: int = 50
    adaptive_max_iterations: int = 50  # Dynamic max that can be adjusted
    retry_count: int = 0
    max_retries: int = 3
    status: str = "running"
    stop_reason: Optional[str] = None
    stop_message: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    final_result: Optional[str] = None
    total_tokens: int = 0
    
    def add_action_log(self, action: AgentAction, result: ActionResult):
        self.action_logs.append(ActionLog(
            action=action,
            result=result,
            iteration=self.current_iteration
        ))
    
    def get_recent_logs(self, count: int = 5) -> List[ActionLog]:
        return self.action_logs[-count:]
    
    def get_failed_actions(self) -> List[ActionLog]:
        return [log for log in self.action_logs if not log.result.success]
    
    def get_success_rate(self) -> float:
        """Calculate overall success rate"""
        if not self.action_logs:
            return 1.0
        return sum(1 for log in self.action_logs if log.result.success) / len(self.action_logs)
    
    def get_recent_success_rate(self, window: int = 5) -> float:
        """Calculate recent success rate"""
        recent = self.action_logs[-window:]
        if not recent:
            return 1.0
        return sum(1 for log in recent if log.result.success) / len(recent)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_description": self.task_description,
            "action_logs": [log.to_dict() for log in self.action_logs],
            "current_iteration": self.current_iteration,
            "max_iterations": self.max_iterations,
            "adaptive_max_iterations": self.adaptive_max_iterations,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "stop_message": self.stop_message,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "final_result": self.final_result,
            "success_rate": self.get_success_rate(),
            "total_tokens": self.total_tokens
        }
    
    def get_context_for_llm(self) -> str:
        """Generate context string for LLM"""
        lines = [f"任务: {self.task_description}", ""]
        
        if self.action_logs:
            lines.append("已执行的动作:")
            for log in self.action_logs[-10:]:
                status = "✓" if log.result.success else "✗"
                lines.append(f"  [{status}] {log.action.action_type.value}: {log.action.reasoning[:50]}")
                if log.result.output:
                    output_str = str(log.result.output)[:200]
                    lines.append(f"      输出: {output_str}")
                if log.result.error:
                    lines.append(f"      错误: {log.result.error[:100]}")
            lines.append("")
        
        # Show adaptive iteration info
        lines.append(f"当前迭代: {self.current_iteration}/{self.adaptive_max_iterations}")
        if self.get_success_rate() < 0.5:
            lines.append(f"⚠️ 成功率较低: {self.get_success_rate():.1%}，请仔细分析错误原因")
        
        return "\n".join(lines)


# Action parameter schemas for validation
ACTION_SCHEMAS = {
    ActionType.RUN_SHELL: {
        "required": ["command"],
        "optional": ["working_directory", "timeout"]
    },
    ActionType.CREATE_AND_RUN_SCRIPT: {
        "required": ["language", "code"],
        "optional": ["filename", "run", "working_directory"]
    },
    ActionType.READ_FILE: {
        "required": ["path"],
        "optional": ["encoding"]
    },
    ActionType.WRITE_FILE: {
        "required": ["path", "content"],
        "optional": ["encoding", "append"]
    },
    ActionType.MOVE_FILE: {
        "required": ["source", "destination"],
        "optional": []
    },
    ActionType.COPY_FILE: {
        "required": ["source", "destination"],
        "optional": []
    },
    ActionType.DELETE_FILE: {
        "required": ["path"],
        "optional": ["recursive"]
    },
    ActionType.LIST_DIRECTORY: {
        "required": ["path"],
        "optional": ["recursive", "pattern"]
    },
    ActionType.OPEN_APP: {
        "required": ["app_name"],
        "optional": []
    },
    ActionType.CLOSE_APP: {
        "required": ["app_name"],
        "optional": []
    },
    ActionType.GET_SYSTEM_INFO: {
        "required": [],
        "optional": ["info_type"]
    },
    ActionType.CLIPBOARD_READ: {
        "required": [],
        "optional": []
    },
    ActionType.CLIPBOARD_WRITE: {
        "required": ["content"],
        "optional": []
    },
    ActionType.THINK: {
        "required": ["thought"],
        "optional": []
    },
    ActionType.FINISH: {
        "required": ["summary"],
        "optional": ["success"]
    }
}


def validate_action(action: AgentAction) -> Optional[str]:
    """Validate action parameters, return error message if invalid"""
    schema = ACTION_SCHEMAS.get(action.action_type)
    if not schema:
        return f"Unknown action type: {action.action_type}"
    
    for param in schema["required"]:
        if param not in action.params:
            return f"Missing required parameter: {param}"
    
    return None
