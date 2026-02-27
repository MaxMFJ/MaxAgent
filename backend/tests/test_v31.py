"""
v3.1 功能单元测试
运行: 在 backend 目录下执行
  python -m pytest tests/test_v31.py -v
  或（仅用标准库）
  python tests/test_v31.py
"""
import os
import sys
import unittest

# 避免 agent 链导入失败：先 mock 再导入（openai / numpy 等可能未安装）
try:
    from unittest.mock import MagicMock
    for _mod in (
        "openai", "numpy", "httpx", "sentence_transformers", "faiss", "psutil",
        "pyperclip", "duckduckgo_search", "bs4", "aiohttp",
    ):
        if _mod not in sys.modules:
            sys.modules[_mod] = MagicMock()
except Exception:
    pass

# 确保 backend 在 path 中
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ---------- 1. 安全校验 ----------
class TestSafety(unittest.TestCase):
    """v3.1 统一安全校验"""

    def test_validate_command_dangerous(self):
        from agent.safety import validate_command
        ok, err = validate_command("rm -rf /")
        self.assertFalse(ok)
        self.assertTrue("危险" in err or "拦截" in err)

    def test_validate_command_dangerous_patterns(self):
        from agent.safety import validate_command
        for cmd in ["rm -rf /*", "chmod -R 777 /", "dd if=/dev/zero", "sudo rm -rf /tmp"]:
            ok, _ = validate_command(cmd)
            self.assertFalse(ok, msg=f"expected dangerous: {cmd}")

    def test_validate_command_safe(self):
        from agent.safety import validate_command
        ok, err = validate_command("ls -la")
        self.assertTrue(ok)
        self.assertEqual(err, "")
        ok, _ = validate_command("echo hello")
        self.assertTrue(ok)

    def test_validate_action_safe_run_shell(self):
        from agent.action_schema import AgentAction, ActionType
        from agent.safety import validate_action_safe
        ok, err = validate_action_safe(
            AgentAction(ActionType.RUN_SHELL, {"command": "rm -rf /"}, "x")
        )
        self.assertFalse(ok)
        ok, _ = validate_action_safe(
            AgentAction(ActionType.RUN_SHELL, {"command": "ls"}, "x")
        )
        self.assertTrue(ok)

    def test_validate_action_safe_write_file(self):
        from agent.action_schema import AgentAction, ActionType
        from agent.safety import validate_action_safe
        ok, err = validate_action_safe(
            AgentAction(ActionType.WRITE_FILE, {"path": "/System/foo", "content": "x"}, "x")
        )
        self.assertFalse(ok)
        ok, _ = validate_action_safe(
            AgentAction(ActionType.WRITE_FILE, {"path": "/tmp/foo", "content": "x"}, "x")
        )
        self.assertTrue(ok)

    def test_validate_action_safe_delete_file(self):
        from agent.action_schema import AgentAction, ActionType
        from agent.safety import validate_action_safe
        ok, _ = validate_action_safe(
            AgentAction(ActionType.DELETE_FILE, {"path": "/usr/bin/foo"}, "x")
        )
        self.assertFalse(ok)
        ok, _ = validate_action_safe(
            AgentAction(ActionType.DELETE_FILE, {"path": "/tmp/foo"}, "x")
        )
        self.assertTrue(ok)

    def test_validate_action_safe_call_tool_terminal(self):
        from agent.action_schema import AgentAction, ActionType
        from agent.safety import validate_action_safe
        ok, _ = validate_action_safe(
            AgentAction(
                ActionType.CALL_TOOL,
                {"tool_name": "terminal", "args": {"command": "rm -rf /"}},
                "x",
            )
        )
        self.assertFalse(ok)
        ok, _ = validate_action_safe(
            AgentAction(
                ActionType.CALL_TOOL,
                {"tool_name": "terminal", "args": {"command": "ls"}},
                "x",
            )
        )
        self.assertTrue(ok)

    def test_validate_action_safe_script_dangerous(self):
        from agent.action_schema import AgentAction, ActionType
        from agent.safety import validate_action_safe
        ok, _ = validate_action_safe(
            AgentAction(
                ActionType.CREATE_AND_RUN_SCRIPT,
                {"language": "bash", "code": "rm -rf /"},
                "x",
            )
        )
        self.assertFalse(ok)


# ---------- 2. 结构化 memory / summarize ----------
class TestStructuredMemory(unittest.TestCase):
    """v3.1 结构化 memory 与 summarize_history_for_llm"""

    def test_get_structured_history_empty(self):
        from agent.action_schema import TaskContext
        ctx = TaskContext(task_id="t1", task_description="测试任务")
        out = ctx.get_structured_history()
        self.assertEqual(out, [])

    def test_summarize_history_empty(self):
        from agent.action_schema import TaskContext
        ctx = TaskContext(task_id="t1", task_description="测试任务")
        s = ctx.summarize_history_for_llm()
        self.assertIn("测试任务", s)
        self.assertIn("当前迭代", s)

    def test_get_structured_history_with_logs(self):
        from agent.action_schema import (
            TaskContext, AgentAction, ActionResult, ActionType,
        )
        ctx = TaskContext(task_id="t1", task_description="任务")
        ctx.current_iteration = 2
        action = AgentAction(ActionType.READ_FILE, {"path": "/tmp/a"}, "read")
        result = ActionResult(action_id=action.action_id, success=True, output="content")
        ctx.add_action_log(action, result)
        structured = ctx.get_structured_history()
        self.assertEqual(len(structured), 1)
        self.assertEqual(structured[0]["action_type"], "read_file")
        self.assertTrue(structured[0]["success"])
        self.assertIn("content", structured[0]["observation_summary"])

    def test_summarize_history_with_logs(self):
        from agent.action_schema import (
            TaskContext, AgentAction, ActionResult, ActionType,
        )
        ctx = TaskContext(task_id="t1", task_description="任务")
        ctx.current_iteration = 3
        for i in range(3):
            action = AgentAction(ActionType.THINK, {}, f"thought_{i}")
            result = ActionResult(action_id=action.action_id, success=(i != 1), output=f"out_{i}", error="err" if i == 1 else None)
            ctx.add_action_log(action, result)
        s = ctx.summarize_history_for_llm(max_recent=5, max_chars=2000)
        self.assertIn("任务", s)
        self.assertIn("最近步骤", s)
        self.assertIn("think", s)
        self.assertIn("当前迭代", s)

    def test_summarize_truncate(self):
        from agent.action_schema import (
            TaskContext, AgentAction, ActionResult, ActionType,
        )
        ctx = TaskContext(task_id="t1", task_description="任务")
        ctx.current_iteration = 15
        for i in range(12):
            action = AgentAction(ActionType.THINK, {}, f"step {i}")
            result = ActionResult(action_id=action.action_id, success=True, output=f"x{i}" * 50)
            ctx.add_action_log(action, result)
        s = ctx.summarize_history_for_llm(max_recent=3, max_chars=500)
        self.assertTrue("已截断" in s or len(s) <= 500 + 50)


# ---------- 3. Escalation（基于 hash fallback，不依赖 BGE）----------
class TestEscalation(unittest.TestCase):
    """v3.1 escalation 重复失败检测（使用 mock context，走 md5 分支）"""

    def test_detect_repeated_failure_returns_normal_when_few_logs(self):
        from agent.action_schema import TaskContext
        from agent.autonomous_agent import AutonomousAgent
        from unittest.mock import MagicMock
        mock_llm = MagicMock()
        agent = AutonomousAgent(llm_client=mock_llm)
        ctx = TaskContext(task_id="t1", task_description="任务")
        ctx.action_logs = []
        level = agent._detect_repeated_failure(ctx)
        self.assertEqual(level, 0)  # ESCALATION_NORMAL

    def test_detect_repeated_failure_same_error_hash(self):
        from agent.action_schema import TaskContext, AgentAction, ActionResult, ActionType
        from agent.autonomous_agent import AutonomousAgent
        from unittest.mock import MagicMock
        mock_llm = MagicMock()
        agent = AutonomousAgent(llm_client=mock_llm)
        ctx = TaskContext(task_id="t1", task_description="任务")
        for i in range(3):
            ctx.current_iteration = i + 1
            action = AgentAction(ActionType.RUN_SHELL, {"command": "ls"}, "r")
            result = ActionResult(action_id=action.action_id, success=False, error="Permission denied")
            ctx.add_action_log(action, result)
        level = agent._detect_repeated_failure(ctx)
        self.assertGreaterEqual(level, 1)


# ---------- 4. App_state v3.1 开关 ----------
class TestAppStateFlags(unittest.TestCase):
    """v3.1 FeatureFlag 可从 app_state 读取"""

    def test_v31_flags_exist(self):
        from app_state import (
            USE_SUMMARIZED_CONTEXT,
            GOAL_RESTATE_EVERY_N,
            ENABLE_PLAN_AND_EXECUTE,
            ENABLE_MID_LOOP_REFLECTION,
            ESCALATION_FORCE_AFTER_N,
            ESCALATION_SKILL_AFTER_N,
        )
        self.assertIsInstance(USE_SUMMARIZED_CONTEXT, bool)
        self.assertIsInstance(GOAL_RESTATE_EVERY_N, int)
        self.assertGreaterEqual(GOAL_RESTATE_EVERY_N, 1)
        self.assertIsInstance(ENABLE_PLAN_AND_EXECUTE, bool)
        self.assertIsInstance(ENABLE_MID_LOOP_REFLECTION, bool)
        self.assertGreaterEqual(ESCALATION_FORCE_AFTER_N, 1)
        self.assertGreaterEqual(ESCALATION_SKILL_AFTER_N, 2)


if __name__ == "__main__":
    unittest.main()
