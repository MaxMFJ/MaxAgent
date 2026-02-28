"""
Usage Statistics Routes
========================
HTTP API endpoints for the monitoring dashboard's "用户平台统计" tab.
"""
from fastapi import APIRouter
from agent.usage_tracker import UsageTracker

router = APIRouter(prefix="/usage-stats", tags=["usage-stats"])


@router.get("/overview")
async def get_usage_overview():
    """
    Top-card summary data:
    - total_requests, success_count
    - total_tokens, total_prompt_tokens, total_completion_tokens
    - avg_rpm, avg_tpm
    - rpm_history, tpm_history (per-minute sparkline, 30 points)
    - request_history (same as rpm_history)
    """
    return UsageTracker.shared().get_overview()


@router.get("/model-analysis")
async def get_model_analysis():
    """
    Model-level breakdown:
    - consumption_distribution: [{model, tokens}]   -> stacked bar
    - consumption_trend: [{time, tokens}]            -> line chart (48h hourly)
    - call_distribution: [{model, count}]            -> donut chart
    - call_ranking: [{model, count}] top 10          -> horizontal bar
    """
    return UsageTracker.shared().get_model_analysis()
