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
]
