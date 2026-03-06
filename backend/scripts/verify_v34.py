#!/usr/bin/env python3
"""v3.3 + v3.4 feature verification script"""
import sys, os
# Add backend/ to path (script lives in backend/scripts/)
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

errors = []

print("=== v3.3 功能验证 ===")

# 1. FeatureFlag
try:
    from app_state import (ENABLE_HITL, ENABLE_AUDIT_LOG, ENABLE_SESSION_RESUME,
                           ENABLE_SUBAGENT, ENABLE_IDEMPOTENT_TASKS, ENABLE_EVOMAP)
    print(f"OK FeatureFlag: HITL={ENABLE_HITL} AUDIT={ENABLE_AUDIT_LOG} SESSION_RESUME={ENABLE_SESSION_RESUME}")
    print(f"   SUBAGENT={ENABLE_SUBAGENT} IDEMPOTENT={ENABLE_IDEMPOTENT_TASKS} EVOMAP={ENABLE_EVOMAP}")
except Exception as e:
    print(f"FAIL FeatureFlag: {e}")
    errors.append("FeatureFlag")

# 2. HITL
try:
    from routes.hitl import router as _r
    print("OK HITL Router registered")
except Exception as e:
    print(f"FAIL HITL: {e}")
    errors.append("HITL")

# 3. Audit
try:
    from routes.audit import router as _r
    print("OK Audit Router registered")
except Exception as e:
    print(f"FAIL Audit: {e}")
    errors.append("Audit")

# 4. Sessions
try:
    from routes.sessions import router as _r
    print("OK Sessions Router registered")
except Exception as e:
    print(f"FAIL Sessions: {e}")
    errors.append("Sessions")

# 5. Subagents
try:
    from routes.subagents import router as _r
    print("OK Subagents Router registered")
except Exception as e:
    print(f"FAIL Subagents: {e}")
    errors.append("Subagents")

# 6. Idempotent cache
try:
    from core.idempotent_cache import get_idempotent_cache
    print("OK Idempotent Cache importable")
except Exception as e:
    print(f"SKIP Idempotent Cache (may not exist): {e}")

print()
print("=== v3.4 功能验证 ===")

# 7. exec_phases
try:
    from agent.exec_phases import PhaseTracker, auto_verify, ExecutionPhase, infer_phase
    pt = PhaseTracker()
    pt.record(1, "write_file", True)
    pt.record(2, "run_shell", True)
    pt.record(3, "think", False)
    stats = pt.stats()
    print(f"OK exec_phases: PhaseTracker works, stats={stats['gather']}/{stats['act']}/{stats['verify']} (G/A/V)")
    phase = infer_phase("write_file")
    print(f"   infer_phase('write_file') = {phase.value}")
except Exception as e:
    print(f"FAIL exec_phases: {e}")
    errors.append("exec_phases")

# 8. MCP client
try:
    from agent.mcp_client import get_mcp_manager, MCPServerConfig
    mgr = get_mcp_manager()
    status = mgr.server_status()
    print(f"OK mcp_client: MCPManager OK, {len(status)} servers connected")
except Exception as e:
    print(f"FAIL mcp_client: {e}")
    errors.append("mcp_client")

# 9. MCP routes
try:
    from routes.mcp import router as _r
    print("OK routes/mcp.py Router registered")
except Exception as e:
    print(f"FAIL routes/mcp: {e}")
    errors.append("routes/mcp")

# 10. snapshot_manager
try:
    import tempfile
    from pathlib import Path
    from agent.snapshot_manager import SnapshotManager
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = SnapshotManager(snapshot_dir=Path(tmpdir))
        # Create a test file then capture snapshot
        test_file = os.path.join(tmpdir, "test.txt")
        with open(test_file, "w") as f:
            f.write("hello world")
        entry = mgr.capture("write", test_file, task_id="test-task", session_id="test-session")
        assert entry is not None, "Snapshot entry is None"
        assert entry.original_content == "hello world"
        # Overwrite then rollback
        with open(test_file, "w") as f:
            f.write("overwritten")
        result = mgr.rollback(entry.snapshot_id)
        assert result["success"], f"Rollback failed: {result}"
        with open(test_file) as f:
            restored = f.read()
        assert restored == "hello world", f"Wrong content after rollback: {restored!r}"
    print("OK snapshot_manager: capture + rollback verified")
except Exception as e:
    import traceback
    print(f"FAIL snapshot_manager: {e}")
    traceback.print_exc()
    errors.append("snapshot_manager")

# 11. rollback routes
try:
    from routes.rollback import router as _r
    print("OK routes/rollback.py Router registered")
except Exception as e:
    print(f"FAIL routes/rollback: {e}")
    errors.append("routes/rollback")

# 12. context routes
try:
    from routes.context import router as _r, _gather_context
    ctx = _gather_context(session_id=None)
    assert "generated_at" in ctx
    print(f"OK routes/context.py: _gather_context works, keys={list(ctx.keys())[:6]}")
except Exception as e:
    import traceback
    print(f"FAIL routes/context: {e}")
    traceback.print_exc()
    errors.append("routes/context")

# 13. ModelTier in model_selector
try:
    from agent.model_selector import ModelTier, get_tier_for_task, TaskAnalysis, TaskType
    analysis = TaskAnalysis(
        task_type=TaskType.COMPLEX_REASONING,
        complexity_score=8,
        is_sensitive=False,
        requires_knowledge=True,
        requires_long_context=False,
        estimated_steps=6,
    )
    tier = get_tier_for_task(analysis)
    assert tier == ModelTier.STRONG
    analysis2 = TaskAnalysis(
        task_type=TaskType.SIMPLE_OPERATION,
        complexity_score=2,
        is_sensitive=False,
        requires_knowledge=False,
        requires_long_context=False,
        estimated_steps=1,
    )
    tier2 = get_tier_for_task(analysis2)
    assert tier2 == ModelTier.FAST
    print(f"OK ModelTier routing: COMPLEX_REASONING => {tier.value}, SIMPLE_OPERATION => {tier2.value}")
except Exception as e:
    import traceback
    print(f"FAIL ModelTier: {e}")
    traceback.print_exc()
    errors.append("ModelTier")

# 14. routes/__init__ has all new routers
try:
    from routes import all_routers
    router_count = len(all_routers)
    print(f"OK routes/__init__: {router_count} routers registered total")
    # Check new v3.4 routers are in the list
    from routes.mcp import router as mcp_r
    from routes.rollback import router as rb_r
    from routes.context import router as ctx_r
    assert mcp_r in all_routers, "mcp_router missing from all_routers"
    assert rb_r in all_routers, "rollback_router missing from all_routers"
    assert ctx_r in all_routers, "context_router missing from all_routers"
    print("   mcp/rollback/context routers all present in all_routers")
except Exception as e:
    import traceback
    print(f"FAIL routes/__init__: {e}")
    traceback.print_exc()
    errors.append("routes/__init__")

print()
if errors:
    print(f"RESULT: {len(errors)} FAILURES: {errors}")
    sys.exit(1)
else:
    print("RESULT: ALL CHECKS PASSED")
