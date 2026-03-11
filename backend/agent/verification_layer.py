"""
Verification Layer — 结果验证 + 目标完成检测 + 证据收集
非 LLM 判定的结构化验证系统。

组件：
1. ResultValidator: 动作结果的 schema 验证
2. EvidenceCollector: 收集任务完成证据（文件存在、内容匹配等）
3. GoalCompletionValidator: 规则优先的目标完成检测
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Result Validator
# ──────────────────────────────────────────────

class ResultValidator:
    """验证动作执行结果的正确性"""

    def validate(self, action_type: str, params: Dict[str, Any], result: Any) -> tuple:
        """
        验证结果是否符合预期。
        返回 (valid: bool, notes: List[str])
        """
        notes: List[str] = []
        success = getattr(result, "success", True)
        if isinstance(result, dict):
            success = result.get("success", True)

        validators = {
            "write_file": self._validate_write_file,
            "read_file": self._validate_read_file,
            "run_shell": self._validate_run_shell,
            "move_file": self._validate_move_file,
            "copy_file": self._validate_copy_file,
            "delete_file": self._validate_delete_file,
            "create_and_run_script": self._validate_script,
        }

        validator = validators.get(action_type.lower())
        if validator:
            ok, msgs = validator(params, result, success)
            notes.extend(msgs)
            return ok, notes

        # 无特定验证器：信任结果
        return success, notes

    def _validate_write_file(self, params, result, success):
        notes = []
        path = params.get("path", "")
        if not path:
            return success, ["无文件路径"]
        path = os.path.expanduser(path)
        if os.path.exists(path):
            size = os.path.getsize(path)
            content_len = len(params.get("content", ""))
            notes.append(f"文件已存在 ({size}B)")
            if content_len > 0 and size == 0:
                notes.append("WARNING: 内容非空但文件为空")
                return False, notes
            return True, notes
        if success:
            notes.append("声称成功但文件未找到")
            return False, notes
        return False, notes

    def _validate_read_file(self, params, result, success):
        notes = []
        if success:
            output = getattr(result, "output", None) or (result.get("output") if isinstance(result, dict) else None)
            if output:
                notes.append(f"内容 {len(str(output))} 字符")
            return True, notes
        return False, notes

    def _validate_run_shell(self, params, result, success):
        notes = []
        result_data = getattr(result, "output", None) or (result.get("output") if isinstance(result, dict) else None) or {}
        if isinstance(result_data, dict):
            exit_code = result_data.get("exit_code", 0)
            if exit_code != 0:
                notes.append(f"退出码 {exit_code}")
                return False, notes
        return success, notes

    def _validate_move_file(self, params, result, success):
        notes = []
        dest = params.get("destination", "") or params.get("dest", "")
        if dest:
            dest = os.path.expanduser(dest)
            if os.path.exists(dest):
                return True, [f"目标已存在: {dest}"]
            if success:
                return False, ["声称成功但目标不存在"]
        return success, notes

    def _validate_copy_file(self, params, result, success):
        return self._validate_move_file(params, result, success)

    def _validate_delete_file(self, params, result, success):
        notes = []
        path = params.get("path", "")
        if path:
            path = os.path.expanduser(path)
            if not os.path.exists(path):
                return True, ["文件已删除"]
            if success:
                return False, ["声称成功但文件仍存在"]
        return success, notes

    def _validate_script(self, params, result, success):
        notes = []
        if success:
            notes.append("脚本执行完成")
        return success, notes


# ──────────────────────────────────────────────
# Evidence Collector
# ──────────────────────────────────────────────

@dataclass
class Evidence:
    """任务完成证据"""
    evidence_type: str      # "file_exists", "file_content_match", "command_output", "app_opened", "screenshot"
    target: str
    verified: bool = False
    details: str = ""
    timestamp: float = field(default_factory=lambda: __import__("time").time())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.evidence_type,
            "target": self.target,
            "verified": self.verified,
            "details": self.details[:200],
        }


class EvidenceCollector:
    """收集任务完成的证据"""

    def __init__(self):
        self._evidence: List[Evidence] = []

    def collect_from_action(self, action_type: str, params: Dict[str, Any], result: Any) -> None:
        """从 action 结果中收集证据"""
        success = getattr(result, "success", True)
        if isinstance(result, dict):
            success = result.get("success", True)

        if not success:
            return

        at = action_type.lower()

        if at == "write_file":
            path = params.get("path", "")
            if path and os.path.exists(os.path.expanduser(path)):
                self._evidence.append(Evidence(
                    evidence_type="file_exists",
                    target=path,
                    verified=True,
                    details=f"文件已创建，大小 {os.path.getsize(os.path.expanduser(path))}B",
                ))

        elif at == "run_shell":
            cmd = params.get("command", "")
            output = getattr(result, "output", None)
            if isinstance(result, dict):
                output = result.get("output")
            self._evidence.append(Evidence(
                evidence_type="command_output",
                target=cmd[:100],
                verified=True,
                details=str(output)[:200] if output else "无输出",
            ))

        elif at == "open_app":
            app = params.get("app_name", "")
            self._evidence.append(Evidence(
                evidence_type="app_opened",
                target=app,
                verified=True,
            ))

        elif at == "call_tool":
            tool_name = params.get("tool_name", "")
            if tool_name == "screenshot":
                self._evidence.append(Evidence(
                    evidence_type="screenshot",
                    target="截图完成",
                    verified=True,
                ))

    def get_evidence(self) -> List[Evidence]:
        return list(self._evidence)

    def has_file_evidence(self, path: str) -> bool:
        """检查是否有特定文件的证据"""
        for e in self._evidence:
            if e.evidence_type == "file_exists" and path in e.target:
                return True
        return False

    def summary(self) -> str:
        if not self._evidence:
            return "无证据"
        lines = [f"  {e.evidence_type}: {e.target}" for e in self._evidence[-10:]]
        return f"证据 ({len(self._evidence)} 项):\n" + "\n".join(lines)

    def reset(self) -> None:
        self._evidence.clear()


# ──────────────────────────────────────────────
# Goal Completion Validator
# ──────────────────────────────────────────────

class GoalCompletionValidator:
    """
    规则优先的目标完成检测。
    不依赖 LLM，通过任务描述中的关键词 + 证据匹配判断是否达成。
    """

    def __init__(self, evidence_collector: Optional[EvidenceCollector] = None):
        self.evidence = evidence_collector or EvidenceCollector()

    def check_completion(
        self,
        task_description: str,
        action_logs: List[Dict[str, Any]],
        claimed_success: bool = True,
    ) -> Dict[str, Any]:
        """
        检查任务是否真正完成。

        返回：
        {
            "completed": bool,
            "confidence": float (0.0~1.0),
            "evidence": [...],
            "warnings": [...],
        }
        """
        result: Dict[str, Any] = {
            "completed": False,
            "confidence": 0.0,
            "evidence": [],
            "warnings": [],
        }

        if not action_logs:
            result["warnings"].append("无执行记录")
            return result

        task_lower = task_description.lower()
        evidence_list = self.evidence.get_evidence()
        result["evidence"] = [e.to_dict() for e in evidence_list]

        # 任务类型检测
        task_type = self._detect_task_type(task_lower)

        # 按类型验证
        if task_type == "file_creation":
            return self._check_file_creation(task_lower, evidence_list, action_logs, result)
        elif task_type == "screenshot":
            return self._check_screenshot(evidence_list, result)
        elif task_type == "app_operation":
            return self._check_app_operation(evidence_list, result)
        elif task_type == "command_execution":
            return self._check_command(action_logs, result)
        elif task_type == "search":
            return self._check_search(action_logs, result)

        # 通用检查：有成功的 action + LLM 声称成功
        success_count = sum(1 for log in action_logs if log.get("result", {}).get("success"))
        if success_count > 0 and claimed_success:
            result["completed"] = True
            result["confidence"] = 0.6
        return result

    def _detect_task_type(self, task: str) -> str:
        """检测任务类型"""
        file_kw = ["创建文件", "写入", "生成", "保存", "write", "create", "save", "新建"]
        screenshot_kw = ["截图", "截屏", "screenshot", "屏幕"]
        app_kw = ["打开", "启动", "关闭", "open", "launch", "close"]
        cmd_kw = ["执行", "运行", "安装", "卸载", "run", "execute", "install"]
        search_kw = ["搜索", "查找", "查询", "search", "find", "查天气", "天气"]

        for kw in file_kw:
            if kw in task:
                return "file_creation"
        for kw in screenshot_kw:
            if kw in task:
                return "screenshot"
        for kw in app_kw:
            if kw in task:
                return "app_operation"
        for kw in search_kw:
            if kw in task:
                return "search"
        for kw in cmd_kw:
            if kw in task:
                return "command_execution"
        return "general"

    def _check_file_creation(self, task, evidence_list, action_logs, result):
        file_evidence = [e for e in evidence_list if e.evidence_type == "file_exists" and e.verified]
        if file_evidence:
            result["completed"] = True
            result["confidence"] = 0.9
        else:
            # 检查 action_logs 中是否有 write_file 成功
            writes = [
                log for log in action_logs
                if log.get("action", {}).get("action_type") in ("write_file", "create_and_run_script")
                and log.get("result", {}).get("success")
            ]
            if writes:
                result["completed"] = True
                result["confidence"] = 0.7
                result["warnings"].append("写入动作成功但无法验证文件")
            else:
                result["warnings"].append("任务要求创建文件但未检测到文件创建证据")
        return result

    def _check_screenshot(self, evidence_list, result):
        screenshot_evidence = [e for e in evidence_list if e.evidence_type == "screenshot"]
        if screenshot_evidence:
            result["completed"] = True
            result["confidence"] = 0.95
        else:
            result["warnings"].append("截图任务但无截图证据")
        return result

    def _check_app_operation(self, evidence_list, result):
        app_evidence = [e for e in evidence_list if e.evidence_type == "app_opened"]
        if app_evidence:
            result["completed"] = True
            result["confidence"] = 0.85
        else:
            result["completed"] = True
            result["confidence"] = 0.5
        return result

    def _check_command(self, action_logs, result):
        cmd_success = [
            log for log in action_logs
            if log.get("action", {}).get("action_type") in ("run_shell", "create_and_run_script")
            and log.get("result", {}).get("success")
        ]
        if cmd_success:
            result["completed"] = True
            result["confidence"] = 0.8
        return result

    def _check_search(self, action_logs, result):
        search_success = [
            log for log in action_logs
            if log.get("action", {}).get("action_type") == "call_tool"
            and log.get("result", {}).get("success")
        ]
        if search_success:
            result["completed"] = True
            result["confidence"] = 0.8
        return result

    def reset(self) -> None:
        self.evidence.reset()


# 单例
_validator: Optional[GoalCompletionValidator] = None


def get_goal_validator() -> GoalCompletionValidator:
    global _validator
    if _validator is None:
        _validator = GoalCompletionValidator()
    return _validator
