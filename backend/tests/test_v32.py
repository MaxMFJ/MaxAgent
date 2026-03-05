"""
v3.2 / Phase C 功能单元测试
==============================
运行方式（在 backend 目录下）：
  python tests/test_v32.py
  python tests/test_v32.py -v
  python -m pytest tests/test_v32.py -v

覆盖范围：
  1. TestTraceLogger       — trace_logger 增强：append_span / get_trace_summary / list_traces / delete_trace
  2. TestFailureTypeReflect — reflect_engine 失败类型分类与模板
  3. TestEpisodicMemoryImportance — episodic_memory 重要性加权 (compute_importance_score / search_similar)
  4. TestV32FeatureFlags   — app_state 中 v3.2 / Phase C Feature Flags 存在且类型正确
  5. TestTracesRoute        — traces API 路由基础逻辑（无需 HTTP，仅测逻辑层）
"""
import os
import sys
import json
import tempfile
import unittest

# ── Mock 不需要安装的依赖 ────────────────────────────────────────────────────
try:
    from unittest.mock import MagicMock, patch
    for _mod in (
        "openai", "numpy", "httpx", "sentence_transformers", "faiss", "psutil",
        "pyperclip", "duckduckgo_search", "bs4", "aiohttp", "tiktoken",
    ):
        if _mod not in sys.modules:
            sys.modules[_mod] = MagicMock()
except Exception:
    pass

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ============================================================================
# 1. TraceLogger 增强
# ============================================================================
class TestTraceLogger(unittest.TestCase):
    """core/trace_logger.py — v3.2 新增函数"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        # 临时覆盖 TRACES_DIR
        import core.trace_logger as tl
        self._orig_dir = tl.TRACES_DIR
        tl.TRACES_DIR = self._tmp

    def tearDown(self):
        import core.trace_logger as tl
        tl.TRACES_DIR = self._orig_dir
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_span(self, task_id: str, span: dict):
        import core.trace_logger as tl
        tl.append_span(task_id, span)

    def test_append_span_auto_ts(self):
        """append_span 自动补全 ts 字段"""
        import core.trace_logger as tl
        tl.append_span("t1", {"type": "llm"})
        spans = tl.get_trace_spans("t1")
        self.assertEqual(len(spans), 1)
        self.assertIn("ts", spans[0])
        self.assertIsInstance(spans[0]["ts"], float)

    def test_get_trace_summary_basic(self):
        """get_trace_summary 正确汇总 token / 步数 / 工具"""
        import core.trace_logger as tl
        tl.append_span("t2", {"type": "llm", "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}, "latency_ms": 300})
        tl.append_span("t2", {"type": "tool", "success": True, "latency_ms": 50})
        tl.append_span("t2", {"type": "tool", "success": False, "error": "cmd not found"})
        s = tl.get_trace_summary("t2")
        self.assertTrue(s["exists"])
        self.assertEqual(s["total_spans"], 3)
        self.assertEqual(s["tokens"]["total"], 150)
        self.assertEqual(s["tool_calls"]["success"], 1)
        self.assertEqual(s["tool_calls"]["failure"], 1)
        self.assertIn("cmd not found", s["recent_errors"][0])

    def test_get_trace_summary_not_found(self):
        """task_id 不存在时 exists=False"""
        import core.trace_logger as tl
        s = tl.get_trace_summary("__no_such_task__")
        self.assertFalse(s["exists"])

    def test_list_traces(self):
        """list_traces 能返回已写入的 task"""
        import core.trace_logger as tl
        tl.append_span("t3", {"type": "step"})
        results = tl.list_traces()
        ids = [r["task_id"] for r in results]
        self.assertIn("t3", ids)

    def test_delete_trace(self):
        """delete_trace 能删除文件，再次删除返回 False"""
        import core.trace_logger as tl
        tl.append_span("t4", {"type": "llm"})
        self.assertTrue(tl.delete_trace("t4"))
        self.assertFalse(tl.delete_trace("t4"))

    def test_get_trace_spans_pagination(self):
        """get_trace_spans 支持 offset/limit 分页"""
        import core.trace_logger as tl
        for i in range(10):
            tl.append_span("t5", {"type": "step", "i": i})
        all_spans = tl.get_trace_spans("t5")
        self.assertEqual(len(all_spans), 10)
        page = tl.get_trace_spans("t5", offset=3, limit=4)
        self.assertEqual(len(page), 4)
        self.assertEqual(page[0]["i"], 3)

    def test_get_trace_spans_type_filter(self):
        """get_trace_spans span_type 过滤"""
        import core.trace_logger as tl
        tl.append_span("t6", {"type": "llm"})
        tl.append_span("t6", {"type": "tool"})
        tl.append_span("t6", {"type": "llm"})
        llm_only = tl.get_trace_spans("t6", span_type="llm")
        self.assertEqual(len(llm_only), 2)


# ============================================================================
# 2. 失败类型分类与反思模板
# ============================================================================
class TestFailureTypeReflect(unittest.TestCase):
    """agent/reflect_engine.py — Phase C 失败类型"""

    def test_classify_permission(self):
        from agent.reflect_engine import classify_failure_type, FailureType
        ft = classify_failure_type("permission denied: /usr/bin")
        self.assertEqual(ft, FailureType.PERMISSION)

    def test_classify_command_error(self):
        from agent.reflect_engine import classify_failure_type, FailureType
        ft = classify_failure_type("bash: command not found: myapp")
        self.assertEqual(ft, FailureType.COMMAND_ERROR)

    def test_classify_file_not_found(self):
        from agent.reflect_engine import classify_failure_type, FailureType
        ft = classify_failure_type("No such file or directory: /tmp/foo.txt")
        self.assertEqual(ft, FailureType.FILE_NOT_FOUND)

    def test_classify_network_error(self):
        from agent.reflect_engine import classify_failure_type, FailureType
        ft = classify_failure_type("Connection refused: 127.0.0.1:9999")
        self.assertEqual(ft, FailureType.NETWORK_ERROR)

    def test_classify_timeout(self):
        from agent.reflect_engine import classify_failure_type, FailureType
        ft = classify_failure_type("Operation timed out after 30 seconds")
        self.assertEqual(ft, FailureType.TIMEOUT)

    def test_classify_unknown(self):
        from agent.reflect_engine import classify_failure_type, FailureType
        ft = classify_failure_type("")
        self.assertEqual(ft, FailureType.UNKNOWN)

    def test_templates_all_types_present(self):
        """所有 FailureType 值都有对应的模板"""
        from agent.reflect_engine import FailureType, FAILURE_REFLECTION_TEMPLATES
        for ftype in FailureType:
            self.assertIn(ftype, FAILURE_REFLECTION_TEMPLATES, msg=f"Missing template for {ftype}")

    def test_reflect_result_has_failure_type(self):
        """ReflectResult.from_llm_response 接受 failure_type 参数"""
        from agent.reflect_engine import ReflectResult, FailureType
        r = ReflectResult.from_llm_response(
            '{"efficiency_score": 3, "successes": [], "failures": ["err"], "strategies": [], "improvements": []}',
            failure_type=FailureType.COMMAND_ERROR,
        )
        self.assertEqual(r.failure_type, FailureType.COMMAND_ERROR)
        self.assertEqual(r.efficiency_score, 3)

    def test_reflect_result_to_dict_includes_failure_type(self):
        """ReflectResult.to_dict() 包含 failure_type 字段"""
        from agent.reflect_engine import ReflectResult, FailureType
        r = ReflectResult(efficiency_score=7, failure_type=FailureType.PERMISSION)
        d = r.to_dict()
        self.assertIn("failure_type", d)
        self.assertEqual(d["failure_type"], "permission")


# ============================================================================
# 3. 重要性加权 Memory
# ============================================================================
class TestEpisodicMemoryImportance(unittest.TestCase):
    """agent/episodic_memory.py — Phase C 重要性加权"""

    def _make_episode(self, **kwargs):
        from agent.episodic_memory import Episode
        from datetime import datetime
        defaults = dict(
            episode_id="ep_test",
            task_description="测试任务",
            result="completed",
            success=False,
            total_actions=5,
            created_at=datetime.now(),
        )
        defaults.update(kwargs)
        return Episode(**defaults)

    def test_compute_importance_score_success(self):
        """成功 episode 的重要性显著高于失败且无反馈的"""
        ep_success = self._make_episode(episode_id="ep1", success=True)
        ep_fail = self._make_episode(episode_id="ep2", success=False)
        ep_success.compute_importance_score()
        ep_fail.compute_importance_score()
        self.assertGreater(ep_success.importance_score, ep_fail.importance_score)

    def test_compute_importance_score_range(self):
        """importance_score 在 [0, 1] 范围内"""
        ep = self._make_episode(success=True, user_feedback="很好")
        ep.compute_importance_score()
        self.assertGreaterEqual(ep.importance_score, 0.0)
        self.assertLessEqual(ep.importance_score, 1.0)

    def test_compute_importance_score_user_feedback_boost(self):
        """有用户反馈的 episode 重要性高于无反馈"""
        ep_with = self._make_episode(episode_id="ep3", success=False, user_feedback="这个方法有帮助")
        ep_without = self._make_episode(episode_id="ep4", success=False)
        ep_with.compute_importance_score()
        ep_without.compute_importance_score()
        self.assertGreater(ep_with.importance_score, ep_without.importance_score)

    def test_episode_to_dict_includes_importance(self):
        """to_dict() 包含 importance_score"""
        ep = self._make_episode(importance_score=0.75)
        d = ep.to_dict()
        self.assertIn("importance_score", d)
        self.assertAlmostEqual(d["importance_score"], 0.75)

    def test_episode_from_dict_restores_importance(self):
        """from_dict() 能恢复 importance_score"""
        from agent.episodic_memory import Episode
        from datetime import datetime
        d = {
            "episode_id": "ep5",
            "task_description": "foo",
            "action_log": [],
            "result": "ok",
            "success": True,
            "total_actions": 3,
            "total_iterations": 3,
            "execution_time_ms": 1000,
            "user_feedback": None,
            "strategies_used": [],
            "reflection": None,
            "created_at": datetime.now().isoformat(),
            "token_usage": {},
            "importance_score": 0.88,
        }
        ep = Episode.from_dict(d)
        self.assertAlmostEqual(ep.importance_score, 0.88)

    def test_search_similar_importance_weighted(self):
        """开启重要性加权时，高重要性 episode 排名更靠前"""
        import tempfile
        from agent.episodic_memory import EpisodicMemory, Episode
        from datetime import datetime

        with tempfile.TemporaryDirectory() as tmpdir:
            mem = EpisodicMemory(storage_dir=tmpdir, enable_vector_search=False)

            # ep_high: 高度相似 + 高重要性（成功 + 有反馈）
            ep_high = Episode(
                episode_id="high",
                task_description="在 /tmp 目录创建 Python 脚本",
                success=True,
                total_actions=3,
                user_feedback="棒！",
                result="ok",
                created_at=datetime.now(),
            )
            ep_high.compute_importance_score()

            # ep_low: 高度相似 + 低重要性
            ep_low = Episode(
                episode_id="low",
                task_description="在 /tmp 目录创建 Python 脚本",
                success=False,
                total_actions=3,
                user_feedback=None,
                result="fail",
                created_at=datetime.now(),
            )
            ep_low.compute_importance_score()

            mem._episodes_cache["high"] = ep_high
            mem._episodes_cache["low"] = ep_low

            # Mock _get_all_episodes 以避免文件 IO
            mem._get_all_episodes = lambda: [ep_high, ep_low]

            results = mem.search_similar(
                "在 /tmp 创建 Python 脚本",
                top_k=2,
                importance_weight=0.5,
            )
            self.assertEqual(len(results), 2)
            # 高重要性的应排在首位
            self.assertEqual(results[0].episode_id, "high")

    def test_update_importance(self):
        """update_importance 能持久化新的 importance_score"""
        import tempfile
        from agent.episodic_memory import EpisodicMemory, Episode
        from datetime import datetime

        with tempfile.TemporaryDirectory() as tmpdir:
            mem = EpisodicMemory(storage_dir=tmpdir, enable_vector_search=False)
            ep = Episode(
                episode_id="upd1",
                task_description="测试更新重要性",
                success=False,
                result="fail",
                total_actions=2,
                created_at=datetime.now(),
                importance_score=0.4,
            )
            # add_episode 会触发 compute_importance_score，先记录 add 后的实际值
            mem.add_episode(ep)
            base_score = mem.get_episode("upd1").importance_score

            ok = mem.update_importance("upd1", delta=0.2)
            self.assertTrue(ok)
            refreshed = mem.get_episode("upd1")
            self.assertIsNotNone(refreshed)
            expected = min(base_score + 0.2, 1.0)
            self.assertAlmostEqual(refreshed.importance_score, expected, places=2)


# ============================================================================
# 4. v3.2 / Phase C Feature Flags
# ============================================================================
class TestV32FeatureFlags(unittest.TestCase):
    """app_state.py — v3.2 Feature Flags 存在且类型正确"""

    def setUp(self):
        import app_state
        self.m = app_state

    def test_v32_flags_exist(self):
        v32_flags = [
            "TRACE_TOKEN_STATS",
            "TRACE_TOOL_CALLS",
            "HEALTH_DEEP_LLM_TIMEOUT",
            "ENABLE_IDEMPOTENT_TASKS",
        ]
        for flag in v32_flags:
            self.assertTrue(hasattr(self.m, flag), msg=f"Missing flag: {flag}")

    def test_phase_c_flags_exist(self):
        phase_c_flags = [
            "ENABLE_IMPORTANCE_WEIGHTED_MEMORY",
            "ENABLE_FAILURE_TYPE_REFLECTION",
            "ENABLE_EXTENDED_THINKING",
            "EXTENDED_THINKING_BUDGET_TOKENS",
            "ENABLE_SUBAGENT",
        ]
        for flag in phase_c_flags:
            self.assertTrue(hasattr(self.m, flag), msg=f"Missing Phase C flag: {flag}")

    def test_type_bool(self):
        bool_flags = [
            "TRACE_TOKEN_STATS", "TRACE_TOOL_CALLS", "ENABLE_IDEMPOTENT_TASKS",
            "ENABLE_IMPORTANCE_WEIGHTED_MEMORY", "ENABLE_FAILURE_TYPE_REFLECTION",
            "ENABLE_EXTENDED_THINKING", "ENABLE_SUBAGENT",
        ]
        for flag in bool_flags:
            v = getattr(self.m, flag)
            self.assertIsInstance(v, bool, msg=f"{flag} should be bool, got {type(v)}")

    def test_type_numeric(self):
        self.assertIsInstance(self.m.HEALTH_DEEP_LLM_TIMEOUT, float)
        self.assertIsInstance(self.m.EXTENDED_THINKING_BUDGET_TOKENS, int)
        self.assertGreater(self.m.EXTENDED_THINKING_BUDGET_TOKENS, 0)
        self.assertGreater(self.m.HEALTH_DEEP_LLM_TIMEOUT, 0)

    def test_importance_memory_default_true(self):
        """重要性加权 memory 默认开启"""
        self.assertTrue(self.m.ENABLE_IMPORTANCE_WEIGHTED_MEMORY)

    def test_failure_reflection_default_true(self):
        """失败类型反思默认开启"""
        self.assertTrue(self.m.ENABLE_FAILURE_TYPE_REFLECTION)

    def test_extended_thinking_default_false(self):
        """Extended Thinking 默认关闭（高成本，需显式开启）"""
        self.assertFalse(self.m.ENABLE_EXTENDED_THINKING)

    def test_subagent_default_false(self):
        """Subagent 默认关闭"""
        self.assertFalse(self.m.ENABLE_SUBAGENT)


# ============================================================================
# Entry point
# ============================================================================
if __name__ == "__main__":
    import sys
    verbosity = 2 if "-v" in sys.argv else 1
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [
        TestTraceLogger,
        TestFailureTypeReflect,
        TestEpisodicMemoryImportance,
        TestV32FeatureFlags,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
