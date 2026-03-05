"""Quick integration sanity check for v3.2 changes."""
import sys
import os

# ── mock heavy dependencies ─────────────────────────────────────────────────
from unittest.mock import MagicMock

for m in [
    "openai", "numpy", "httpx", "sentence_transformers", "faiss", "psutil",
    "pyperclip", "duckduckgo_search", "bs4", "aiohttp", "tiktoken",
    "fastapi", "fastapi.routing", "fastapi.params", "fastapi.types",
    "fastapi.responses",
]:
    if m not in sys.modules:
        sys.modules[m] = MagicMock()

import fastapi as fa_mock  # noqa: E402
fa_mock.APIRouter = lambda **kw: MagicMock()
fa_mock.Query = lambda *a, **kw: None
fa_mock.HTTPException = Exception

# ── ensure backend root is on path ──────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = []
failed = []

def ok(name):
    passed.append(name)
    print(f"  [OK] {name}")

def fail(name, err):
    failed.append(name)
    print(f"  [FAIL] {name}: {err}")

# 1. app_state — v3.2 / Phase-C flags present and defaults correct
try:
    import app_state as ap
    required = {
        "TRACE_TOKEN_STATS": True,
        "TRACE_TOOL_CALLS": True,
        "ENABLE_IDEMPOTENT_TASKS": False,
        "ENABLE_IMPORTANCE_WEIGHTED_MEMORY": True,
        "ENABLE_FAILURE_TYPE_REFLECTION": True,
        "ENABLE_EXTENDED_THINKING": False,
        "ENABLE_SUBAGENT": False,
    }
    issues = []
    for flag, expected in required.items():
        val = getattr(ap, flag, "MISSING")
        if val != expected:
            issues.append(f"{flag}={val!r} (expected {expected!r})")
        else:
            print(f"    {flag} = {val}")
    if issues:
        fail("app_state flags", "; ".join(issues))
    else:
        ok("app_state flags")
    # numeric flags
    assert hasattr(ap, "HEALTH_DEEP_LLM_TIMEOUT")
    assert hasattr(ap, "EXTENDED_THINKING_BUDGET_TOKENS")
    ok("app_state numeric flags")
except Exception as e:
    fail("app_state", e)

# 2. trace_logger — all 5 functions present
try:
    from core.trace_logger import (
        append_span, get_trace_summary, list_traces,
        delete_trace, get_trace_spans,
    )
    ok("trace_logger functions")
except Exception as e:
    fail("trace_logger", e)

# 3. reflect_engine — FailureType & template coverage
try:
    from agent.reflect_engine import (
        FailureType, classify_failure_type,
        FAILURE_REFLECTION_TEMPLATES, ReflectResult,
    )
    assert len(FAILURE_REFLECTION_TEMPLATES) == len(list(FailureType)), \
        f"template count {len(FAILURE_REFLECTION_TEMPLATES)} != FailureType count {len(list(FailureType))}"
    ft = classify_failure_type("permission denied")
    assert ft == FailureType.PERMISSION, f"got {ft}"
    ft2 = classify_failure_type("connection refused")
    assert ft2 == FailureType.NETWORK_ERROR, f"got {ft2}"
    ok("reflect_engine FailureType + templates")
    # ReflectResult fields
    import dataclasses
    fields = {f.name for f in dataclasses.fields(ReflectResult)}
    for f in ("failure_type", "root_cause", "correct_approach"):
        assert f in fields, f"missing field {f}"
    ok("ReflectResult fields")
except Exception as e:
    fail("reflect_engine", e)

# 4. episodic_memory — importance scoring
try:
    import datetime
    from agent.episodic_memory import Episode
    ep = Episode(
        episode_id="x", task_description="test", success=True,
        result="ok", total_actions=3, created_at=datetime.datetime.now(),
    )
    score = ep.compute_importance_score()
    assert 0.0 <= score <= 1.0, f"score out of range: {score}"
    d = ep.to_dict()
    assert "importance_score" in d
    ep2 = Episode.from_dict(d)
    assert abs(ep2.importance_score - score) < 1e-9
    ok(f"episodic_memory importance (score={score:.3f})")
except Exception as e:
    fail("episodic_memory", e)

# 5. routes/__init__ — traces_router registered
try:
    init_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "routes", "__init__.py",
    )
    src = open(init_path).read()
    assert "from .traces import router as traces_router" in src
    assert "traces_router" in src
    ok("routes/__init__.py traces_router")
except Exception as e:
    fail("routes/__init__.py", e)

# 6. llm_client — extra_body parameter
try:
    import inspect
    from agent.llm_client import LLMClient
    sig = inspect.signature(LLMClient.chat)
    assert "extra_body" in sig.parameters, "extra_body missing from LLMClient.chat"
    ok("llm_client extra_body param")
except Exception as e:
    fail("llm_client", e)

# ── Summary ──────────────────────────────────────────────────────────────────
print()
print(f"=== Result: {len(passed)} passed, {len(failed)} failed ===")
if failed:
    sys.exit(1)
