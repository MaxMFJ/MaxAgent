"""
路由模块包
每个子模块导出一个 APIRouter，在 main.py 中统一注册。
"""
from .health import router as health_router
from .auth_routes import router as auth_router
from .config import router as config_router
from .tools import router as tools_router
from .upgrade import router as upgrade_router
from .logs import router as logs_router
from .memory import router as memory_router
from .self_healing import router as self_healing_router
from .evomap import router as evomap_router
from .capsules import router as capsules_router
from .chat import router as chat_router
from .workspace import router as workspace_router
from .monitor import router as monitor_router
from .usage_stats import router as usage_stats_router
from .tunnel import router as tunnel_router
from .permissions import router as permissions_router
from .files import router as files_router
from .traces import router as traces_router
from .feature_flags import router as feature_flags_router
from .audit import router as audit_router
from .hitl import router as hitl_router
from .sessions import router as sessions_router
from .subagents import router as subagents_router
from .mcp import router as mcp_router
from .rollback import router as rollback_router
from .context import router as context_router
from .duck_api import router as duck_api_router
from .duck_ws import router as duck_ws_router

all_routers = [
    health_router,
    auth_router,
    config_router,
    tools_router,
    upgrade_router,
    logs_router,
    memory_router,
    self_healing_router,
    evomap_router,
    capsules_router,
    chat_router,
    workspace_router,
    monitor_router,
    usage_stats_router,
    tunnel_router,
    permissions_router,
    files_router,
    traces_router,
    feature_flags_router,
    audit_router,
    hitl_router,
    sessions_router,
    subagents_router,
    mcp_router,
    rollback_router,
    context_router,
    duck_api_router,
    duck_ws_router,
]
