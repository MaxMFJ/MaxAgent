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
    CALL_TOOL = "call_tool"  # 调用已注册工具（screenshot、capsule、terminal 等）
    DELEGATE_DUCK = "delegate_duck"  # 委派任务给 Duck 分身 Agent
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
    truncated: bool = False  # 标记此动作是从截断的 JSON 修复而来
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "params": self.params,
            "reasoning": self.reasoning,
            "status": self.status.value,
            "created_at": self.created_at.isoformat()
        }
        if self.truncated:
            result["truncated"] = True
        return result
    
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
        # 去除 BOM 与不可见字符，避免 LM Studio 等本地模型输出导致解析失败
        text = response_text.strip().strip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        if not text:
            return None

        # 1. 提取所有 ```json ... ``` 或 ``` ... ``` 块，逐个尝试（DeepSeek 可能先输出总结再输出动作）
        for code_block in re.finditer(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text):
            parsed = cls._parse_json_to_action(code_block.group(1).strip())
            if parsed:
                return parsed

        # 1b. LM Studio 等可能返回未闭合的 ```json 块（流被断开或 max_tokens 截断），按“截断 JSON”尝试修补
        if "```json" in text or "```" in text:
            inner = text
            for prefix in ("```json", "```"):
                if prefix in inner:
                    idx = inner.find(prefix) + len(prefix)
                    inner = inner[idx:].lstrip("\r\n")
                    break
            if inner.strip().startswith("{"):
                parsed = cls._parse_truncated_json_block(inner.strip())
                if parsed:
                    return parsed

        # 2. 提取所有 { ... } 块，逐个尝试（从后往前，模型常把最终动作放在最后）
        blocks = cls._extract_brace_blocks(text)
        for candidate in reversed(blocks):
            parsed = cls._parse_json_to_action(candidate)
            if parsed:
                return parsed

        # 3. 使用 json_repair 从全文提取（可能返回 list 如 [{...}]，取首元素）
        data = repair_json(text)
        if data is not None:
            if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
                data = data[0]
            if isinstance(data, dict):
                parsed = cls._dict_to_action(data)
                if parsed:
                    return parsed

        # 4. 直接解析整段（可能是纯 JSON 或 ``` 包裹；支持单元素数组 [{...}]）
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
            if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
                data = data[0]
            if isinstance(data, dict):
                return cls._dict_to_action(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

        return None

    @classmethod
    def _parse_truncated_json_block(cls, raw: str) -> Optional["AgentAction"]:
        """尝试修补 LM Studio 等返回的截断 JSON（流断开或 max_tokens 导致未闭合），再解析为动作。
        
        返回的动作会被标记为 truncated=True，让上层逻辑知道这是修复后的结果。
        """
        if not raw.strip().startswith("{"):
            return None
        depth = 0
        for c in raw:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
        if depth <= 0:
            return None
        repaired = raw.rstrip()
        if repaired.endswith(","):
            repaired = repaired[:-1]
        repaired += ', "action_type": "think", "params": {"thought": "输出被截断，继续下一步。"}' + "}" * depth
        data = repair_json(repaired)
        if data is None:
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError:
                return None
        if not isinstance(data, dict):
            return None
        action_type_str = (data.get("action_type") or data.get("action") or "").strip()
        if not action_type_str:
            data["action_type"] = "think"
            data["params"] = data.get("params") or {"thought": (data.get("reasoning") or "输出被截断，继续思考下一步。")[:200]}
        action = cls._dict_to_action(data)
        if action:
            action.truncated = True  # 标记为截断修复
        return action

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
        """从 dict 构建 AgentAction（兼容 action_type / action / actionType，及空格形式如 run shell）"""
        if not isinstance(data, dict):
            return None
        action_type_str = (
            data.get("action_type") or data.get("action") or data.get("actionType") or ""
        ).lower().strip()
        if not action_type_str:
            return None
        # 本地模型（如 LM Studio）可能输出 "run shell"、"get system info"，统一为下划线形式
        action_type_str = re.sub(r"\s+", "_", action_type_str)
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
    consecutive_action_failures: int = 0  # 连续动作执行失败次数（think 成功不重置）
    max_consecutive_action_failures: int = 3  # 达到此次数即停止并返回未完成任务
    status: str = "running"
    stop_reason: Optional[str] = None
    stop_message: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    final_result: Optional[str] = None
    total_tokens: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    # v3.2 关键产物追踪（文件路径、URL、资源标识符等）
    key_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_action_log(self, action: AgentAction, result: ActionResult):
        self.action_logs.append(ActionLog(
            action=action,
            result=result,
            iteration=self.current_iteration
        ))
        # 自动提取关键产物
        self._extract_artifacts(action, result)
    
    def _extract_artifacts(self, action: AgentAction, result: ActionResult):
        """从动作和结果中提取关键产物（文件路径、URL等）"""
        import re
        
        # 1. 从动作参数中提取
        if action.action_type == ActionType.WRITE_FILE:
            path = action.params.get("path")
            if path:
                self._add_artifact("file_created", path, f"写入文件", action.reasoning)
        
        elif action.action_type == ActionType.CREATE_AND_RUN_SCRIPT:
            filename = action.params.get("filename")
            if filename:
                self._add_artifact("script_created", filename, "创建脚本", action.reasoning)
        
        # 2. 从成功的结果输出中提取
        if result.success and result.output:
            output_str = str(result.output)
            
            # 提取文件路径（Unix 风格）
            file_paths = re.findall(r'(?:创建|生成|写入|保存)[^\n]*?(/[^\s:,\'"<>]+\.\w+)', output_str)
            for fp in file_paths[:3]:  # 最多提取 3 个
                if len(fp) < 200:  # 避免误匹配长字符串
                    self._add_artifact("file_path", fp, "提取的文件路径")
            
            # 提取 URL
            urls = re.findall(r'(https?://[^\s<>"\']+)', output_str)
            for url in urls[:3]:
                if len(url) < 300:
                    # 过滤常见的无意义 URL
                    if not any(x in url for x in ['localhost:8', 'github.com/actions', 'cdn.']):
                        self._add_artifact("url", url, "提取的 URL")
            
            # 提取端口映射信息
            port_mappings = re.findall(r'(?:映射|转发|tunnel)[^\n]*?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+)', output_str)
            for pm in port_mappings[:2]:
                self._add_artifact("port_mapping", pm, "端口映射")
    
    def _add_artifact(self, artifact_type: str, value: str, description: str, context: str = ""):
        """添加关键产物，避免重复"""
        # 检查是否已存在相同的产物
        for artifact in self.key_artifacts:
            if artifact["type"] == artifact_type and artifact["value"] == value:
                return
        
        self.key_artifacts.append({
            "type": artifact_type,
            "value": value,
            "description": description,
            "context": context[:100] if context else "",
            "step": self.current_iteration,
        })
    
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
        
        # 首先输出关键产物（最重要的上下文信息）
        if self.key_artifacts:
            lines.append("【关键产物 - 已生成的文件和资源】")
            for artifact in self.key_artifacts:
                lines.append(f"  • [{artifact['type']}] 步骤{artifact['step']}: {artifact['value']}")
                if artifact.get('description'):
                    lines.append(f"    说明: {artifact['description']}")
            lines.append("")
        
        if self.action_logs:
            lines.append("已执行的动作:")
            for log in self.action_logs[-15:]:  # 增加到最近 15 条
                status = "✓" if log.result.success else "✗"
                lines.append(f"  [{status}] {log.action.action_type.value}: {log.action.reasoning[:80]}")
                if log.result.output:
                    output_str = str(log.result.output)
                    # 包含路径或 URL 的输出保留更多字符
                    if "/Users/" in output_str or "http" in output_str or "/" in output_str:
                        output_str = output_str[:600]
                    else:
                        output_str = output_str[:300]
                    lines.append(f"      输出: {output_str}")
                if log.result.error:
                    lines.append(f"      错误: {log.result.error[:200]}")
            lines.append("")
        
        # Show adaptive iteration info
        lines.append(f"当前迭代: {self.current_iteration}/{self.adaptive_max_iterations}")
        if self.get_success_rate() < 0.5:
            lines.append(f"⚠️ 成功率较低: {self.get_success_rate():.1%}，请仔细分析错误原因")
        
        return "\n".join(lines)

    # ---------- v3.1 结构化 memory：供上下文压缩与防漂移 ----------
    def get_structured_history(self) -> List[Dict[str, Any]]:
        """
        返回结构化步骤列表，便于压缩/摘要而非纯字符串拼接。
        每项: iteration, thought, action_type, observation_summary, success
        """
        out: List[Dict[str, Any]] = []
        for log in self.action_logs:
            obs = ""
            if log.result.output:
                obs = str(log.result.output)[:300]
            if log.result.error:
                obs = (obs + " [错误: " + log.result.error[:150] + "]").strip()
            out.append({
                "iteration": log.iteration,
                "thought": (log.action.reasoning or "")[:200],
                "action_type": log.action.action_type.value,
                "observation_summary": obs,
                "success": log.result.success,
            })
        return out

    def summarize_history_for_llm(
        self,
        max_recent: int = 8,
        max_chars: int = 5000,
    ) -> str:
        """
        在控制 token 的前提下生成给 LLM 的历史上下文。
        最近 max_recent 条完整保留，更早的每 5 步合并为一行摘要；总长度约 max_chars。
        v3.1 增强：包含 key_artifacts，保留更多关键信息。
        """
        structured = self.get_structured_history()
        lines = [f"任务: {self.task_description}", ""]
        
        # 首先输出关键产物（最重要的上下文）
        if self.key_artifacts:
            lines.append("【关键产物 - 已完成的成果，请勿重复执行】")
            for artifact in self.key_artifacts:
                lines.append(f"  • [{artifact['type']}] 步骤{artifact['step']}: {artifact['value']}")
            lines.append("")
        
        if not structured:
            lines.append(f"当前迭代: {self.current_iteration}/{self.adaptive_max_iterations}")
            return "\n".join(lines)

        n = len(structured)
        # 较早部分：每 5 步合并，但保留关键路径/URL信息
        if n > max_recent:
            older = structured[: n - max_recent]
            lines.append("历史步骤摘要:")
            for i in range(0, len(older), 5):
                chunk = older[i : i + 5]
                successes = sum(1 for s in chunk if s["success"])
                types = ", ".join(dict.fromkeys(s["action_type"] for s in chunk))
                lines.append(f"  步骤 {chunk[0]['iteration']}–{chunk[-1]['iteration']}: {types}（成功 {successes}/{len(chunk)}）")
                # 提取关键路径/URL信息
                for s in chunk:
                    obs = s.get("observation_summary", "")
                    if "/Users/" in obs or "http" in obs.lower() or ":" in obs:
                        # 保留包含路径或URL的关键信息
                        key_info = obs[:200] if len(obs) > 200 else obs
                        if key_info.strip():
                            lines.append(f"    → {key_info}")
            lines.append("")
        # 最近 max_recent 条完整保留
        lines.append("最近步骤详情:")
        for s in structured[-max_recent:]:
            status = "✓" if s["success"] else "✗"
            lines.append(f"  [{status}] {s['action_type']}: {s['thought'][:80]}")
            if s["observation_summary"]:
                # 对包含路径/URL的输出保留更多内容
                obs = s["observation_summary"]
                if "/Users/" in obs or "http" in obs.lower():
                    lines.append(f"      结果: {obs[:400]}")
                else:
                    lines.append(f"      结果: {obs[:200]}")
        lines.append("")
        lines.append(f"当前迭代: {self.current_iteration}/{self.adaptive_max_iterations}")
        if self.get_success_rate() < 0.5:
            lines.append(f"⚠️ 成功率较低: {self.get_success_rate():.1%}，请仔细分析错误原因")
        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[: max_chars] + "\n...(已截断)"
        return result


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
    ActionType.CALL_TOOL: {
        "required": ["tool_name", "args"],
        "optional": []
    },
    ActionType.DELEGATE_DUCK: {
        "required": ["description"],
        "optional": ["duck_type", "duck_id", "strategy", "timeout", "task_type", "params", "priority"]
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
