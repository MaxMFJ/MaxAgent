#!/usr/bin/env python3
"""
Chow Duck Backend Server
FastAPI server with WebSocket support for the macOS AI Agent
Supports both ReAct and Autonomous execution modes

模块结构（详见 docs/backend-structure.md）：
  main.py              - 入口：lifespan、app 创建、路由注册
  app_state.py         - 全局状态（LLM/agent 单例、TaskTracker、FeatureFlags）
  auth.py              - 认证
  connection_manager.py - WebSocket 连接与 session 广播
  ws_handler.py        - WebSocket /ws 消息分发
  config/              - 配置持久化（agent/llm/smtp/github）
  core/                - v3 框架（错误模型、状态机、限流、超时）
  agent/               - Agent 能力（对话、自主、自愈、升级等）
  routes/              - HTTP 路由
  tools/               - 工具实现
  runtime/             - 平台适配
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    try:
        from config.github_config import apply_github_config
        apply_github_config()
    except Exception:
        pass
except ImportError:
    pass

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app_state import (
    ENABLE_EVOMAP, AUTO_TOOL_UPGRADE,
    set_llm_client, set_cloud_llm_client, set_local_llm_client,
    set_agent_core, set_autonomous_agent, set_reflect_llm,
    get_llm_client, get_local_llm_client, get_agent_core,
)
from connection_manager import connection_manager
from routes import all_routers
from routes.logs import setup_log_capture, log_buffer
from routes.upgrade import trigger_tool_upgrade
from routes.tools import _load_generated_tools
from ws_handler import router as ws_router

from agent.core import AgentCore
from agent.llm_client import LLMClient, LLMConfig
from agent.autonomous_agent import AutonomousAgent
from agent.system_message_service import get_system_message_service
from agent.log_analyzer import get_log_analyzer

logger = logging.getLogger(__name__)

# 统一日志配置：只在 root logger 上挂一个 StreamHandler，避免与 uvicorn 叠加导致重复输出
_root = logging.getLogger()
if not _root.handlers:
    _sh = logging.StreamHandler()
    _sh.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    _root.addHandler(_sh)
_root.setLevel(logging.INFO)

logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
# websockets 的 keepalive ping timeout / ConnectionClosed 是客户端断连时的正常行为，不需要 ERROR 级别
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

setup_log_capture()


# ============== Lifespan ==============


def _llm_config_from_persisted():
    """从 Mac App 持久化的 llm_config.json 构建 LLMConfig，供主模型启动时使用。"""
    try:
        from config.llm_config import load_llm_config, get_persisted_api_key
    except Exception:
        return None
    cfg = load_llm_config()
    if not cfg:
        return None
    provider = (cfg.get("provider") or "deepseek").strip()
    api_key = (cfg.get("api_key") or "").strip() or get_persisted_api_key()
    base_url = (cfg.get("base_url") or "").strip() or os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    model = (cfg.get("model") or "").strip() or os.getenv("LLM_MODEL", "deepseek-chat")
    max_tokens = cfg.get("max_tokens")
    if max_tokens is not None and isinstance(max_tokens, (int, float)) and max_tokens > 0:
        max_tokens = int(max_tokens)
    else:
        max_tokens = None  # 使用 LLMConfig 默认值 4096
    kwargs = {"provider": provider, "api_key": api_key, "base_url": base_url, "model": model}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return LLMConfig(**kwargs)


def _cloud_llm_config_for_startup():
    """
    自主任务选“远程”时使用的客户端配置。
    若当前持久化为本地(lmstudio/ollama)，使用上次保存的云端配置(remote_fallback)，否则与主配置一致。
    """
    from config.llm_config import get_remote_fallback_config
    initial = _llm_config_from_persisted()
    if not initial:
        return None
    provider = (initial.provider or "").strip().lower()
    if provider in ("ollama", "lmstudio"):
        fallback = get_remote_fallback_config()
        if fallback:
            return LLMConfig(
                provider=fallback["provider"],
                api_key=fallback.get("api_key", ""),
                base_url=fallback.get("base_url", ""),
                model=fallback.get("model", ""),
            )
        # 无远程回退时使用默认 DeepSeek，避免“选远程”仍请求本地 502
        return LLMConfig(
            provider="deepseek",
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
        )
    return initial


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 主模型：优先使用 Mac App 持久化的配置（可为 newapi/deepseek/lmstudio/ollama）
    initial_config = _llm_config_from_persisted()
    llm = LLMClient(initial_config)
    set_llm_client(llm)

    # 云端模型：自主任务选择"远程"时使用。若当前为本地(lmstudio/ollama)，用 remote_fallback 或默认 DeepSeek，避免仍请求本地 502
    cloud_config = _cloud_llm_config_for_startup() or initial_config
    cloud_llm = LLMClient(cloud_config)
    set_cloud_llm_client(cloud_llm)

    from runtime import get_runtime_adapter
    _adapter = get_runtime_adapter()
    core = AgentCore(llm, runtime_adapter=_adapter)
    set_agent_core(core)

    # 启动时检查辅助功能/GUI 权限并记录日志
    try:
        from runtime.permission_checker import get_permission_status
        perm_status = get_permission_status()
        if perm_status.get("trusted"):
            logger.info("辅助功能权限: 已授予 (process=%s)", perm_status.get("process_path", "?"))
        else:
            logger.warning("辅助功能权限: 未授予！键鼠模拟将失败。%s", perm_status.get("guidance", ""))
    except Exception as e:
        logger.warning(f"辅助功能权限检查跳过: {e}")
    try:
        from runtime import cg_event
        if cg_event.HAS_QUARTZ:
            logger.info("CGEvent (Quartz): 可用")
        else:
            logger.warning("CGEvent (Quartz): 不可用，将回退至 cliclick/AppleScript")
    except Exception as e:
        logger.warning(f"CGEvent 检查跳过: {e}")
    import shutil
    if shutil.which("cliclick"):
        logger.info("cliclick: 可用 (%s)", shutil.which("cliclick"))
    else:
        logger.warning("cliclick: 未找到（PATH=%s）。如果 CGEvent 不可用，鼠标操作将失败。安装: brew install cliclick", os.environ.get("PATH", "")[:200])

    # 终端会话增强：记录 cwd/输出供后续命令和 prompt 注入
    try:
        from tools.middleware import register_post_hook
        from agent.terminal_session import get_terminal_session_store, get_current_session_id

        async def _terminal_session_post_hook(name, args, result):
            if name != "terminal":
                return None
            sid = get_current_session_id()
            if not sid:
                return None
            data = result.data if isinstance(result.data, dict) else {}
            get_terminal_session_store().update(
                session_id=sid,
                cwd=data.get("working_directory", ""),
                command=data.get("command", ""),
                stdout=data.get("stdout", ""),
                stderr=data.get("stderr", ""),
                exit_code=data.get("exit_code", 0),
            )
            return None

        register_post_hook(_terminal_session_post_hook)

        from tools.middleware import register_pre_hook

        def _terminal_session_pre_hook(name, args):
            """终端未指定 working_directory 时，复用上条命令的 cwd"""
            if name != "terminal":
                return None
            if args.get("working_directory"):
                return None
            sid = get_current_session_id()
            if not sid:
                return None
            last_cwd = get_terminal_session_store().get_default_cwd(sid)
            if last_cwd:
                args = dict(args)
                args["working_directory"] = last_cwd
                return args
            return None

        register_pre_hook(_terminal_session_pre_hook)
        logger.info("Terminal session hooks registered")
    except Exception as e:
        logger.warning(f"Terminal session hook setup skipped: {e}")

    local_llm = LLMClient(LLMConfig(
        provider="ollama",
        base_url="http://localhost:11434/v1",
        model="qwen2.5-coder:7b",
        api_key="ollama",
    ))
    set_local_llm_client(local_llm)

    reflect = LLMClient(LLMConfig(
        provider="ollama",
        base_url="http://localhost:11434/v1",
        model="qwen2.5:7b",
        api_key="ollama",
    ))
    set_reflect_llm(reflect)

    autonomous = AutonomousAgent(
        llm_client=cloud_llm,
        local_llm_client=local_llm,
        reflect_llm=reflect,
        runtime_adapter=_adapter,
        enable_reflection=True,
        enable_model_selection=True,
    )
    set_autonomous_agent(autonomous)

    # 任务持久化管理器初始化：加载上次中断的任务
    try:
        from task_persistence import get_persistence_manager
        persistence_manager = get_persistence_manager()
        await persistence_manager.initialize()
        logger.info("Task persistence manager initialized")
    except Exception as e:
        logger.warning(f"Task persistence manager init failed: {e}")

    # BGE 向量模型预加载
    if os.environ.get("ENABLE_VECTOR_SEARCH", "true").lower() == "true":
        try:
            from agent.vector_store import preload_embedding_model
            preload_embedding_model()
        except Exception as e:
            logger.warning(f"Failed to start BGE preloading: {e}")
    else:
        logger.info("Vector search disabled (ENABLE_VECTOR_SEARCH=false), BGE not loaded")

    # Self-Upgrade 编排框架
    try:
        from agent.self_upgrade import get_orchestrator as get_self_upgrade_orchestrator

        def _llm_chat_for_upgrade(messages, tools=None):
            client = get_llm_client() or get_local_llm_client()
            if not client:
                raise RuntimeError("No LLM client")
            return client.chat(messages=messages, tools=tools)

        def _get_existing_tools():
            ac = get_agent_core()
            if not ac:
                return set()
            return {t.name for t in ac.registry.list_tools()}

        get_self_upgrade_orchestrator(
            llm_chat=_llm_chat_for_upgrade,
            on_load_generated_tools=_load_generated_tools,
            get_existing_tools=_get_existing_tools,
        )
        logger.info("Self-Upgrade orchestrator initialized")
    except Exception as e:
        logger.warning(f"Self-Upgrade orchestrator init skipped: {e}")

    # Capsule 本地加载
    try:
        from agent.capsule_bootstrap import bootstrap_capsules

        async def _init_capsules():
            try:
                result = await bootstrap_capsules(run_sync_first=True)
                if result.get("registered", 0) > 0:
                    logger.info(f"Capsule bootstrap: {result['registered']} local capsules registered")
            except Exception as e:
                logger.warning(f"Capsule bootstrap failed (non-blocking): {e}")

        asyncio.create_task(_init_capsules())
        logger.info("Capsule bootstrap scheduled (background)")
    except Exception as e:
        logger.warning(f"Capsule bootstrap setup skipped: {e}")

    # EvoMap 进化网络
    if ENABLE_EVOMAP:
        try:
            from agent.evomap_service import get_evomap_service
            evomap_svc = get_evomap_service()
            macagent_capabilities = [
                "app_control", "file_operation", "terminal", "browser",
                "screenshot", "system", "mail", "search",
            ]

            async def _init_evomap():
                try:
                    result = await evomap_svc.initialize(macagent_capabilities)
                    logger.info(f"EvoMap initialized: registration={result['registration'].get('status') if result.get('registration') else 'skipped'}")
                except Exception as e:
                    logger.warning(f"EvoMap initialization failed (non-blocking): {e}")

            asyncio.create_task(_init_evomap())
            logger.info("EvoMap initialization scheduled (background)")
        except Exception as e:
            logger.warning(f"EvoMap setup skipped: {e}")
    else:
        logger.info("EvoMap disabled (ENABLE_EVOMAP=false), using local Capsule / open skills only")

    # EventBus 解耦服务
    try:
        from agent.event_bus import get_event_bus
        from agent.error_service import get_error_service
        from agent.self_healing_worker import get_self_healing_worker
        from agent.upgrade_service import get_upgrade_service

        get_event_bus().set_loop(asyncio.get_running_loop())

        async def _broadcast_to_session(sid: str, chunk: dict):
            await connection_manager.broadcast_to_session(sid, chunk)

        if ENABLE_EVOMAP:
            try:
                from agent.evomap_upgrade_hook import init_evomap_upgrade_hook
                init_evomap_upgrade_hook()
                logger.info("EvoMap upgrade hook initialized")
            except Exception as e:
                logger.warning(f"EvoMap upgrade hook init skipped: {e}")

        get_error_service()
        get_self_healing_worker(on_broadcast=lambda sid, c: _broadcast_to_session(sid, c))
        get_upgrade_service(
            on_trigger_upgrade=trigger_tool_upgrade,
            on_broadcast=lambda sid, c: _broadcast_to_session(sid, c),
            auto_upgrade=AUTO_TOOL_UPGRADE,
        )
        logger.info("EventBus services (Error, SelfHealing, Upgrade) initialized")
    except Exception as e:
        logger.warning(f"EventBus services init skipped: {e}")

    # 系统消息服务 + 启动日志分析
    try:
        sys_msg_svc = get_system_message_service()
        sys_msg_svc.set_broadcast(lambda msg: connection_manager.broadcast_all(msg))

        async def _startup_log_analysis():
            await asyncio.sleep(8)
            try:
                analyzer = get_log_analyzer()
                analyzer.analyze_on_startup(log_buffer)
                logger.info("Startup log analysis completed")
            except Exception as e:
                logger.warning(f"Startup log analysis failed: {e}")

        asyncio.create_task(_startup_log_analysis())
        logger.info("SystemMessageService initialized, startup log analysis scheduled")
    except Exception as e:
        logger.warning(f"SystemMessageService init failed: {e}")

    logger.info("Chow Duck backend started (ReAct + Autonomous modes with Model Selection)")

    # Tunnel Lifecycle Service 初始化（异步启动 cloudflared，不阻塞后端）
    try:
        from services.tunnel_lifecycle import get_tunnel_lifecycle
        tunnel_svc = get_tunnel_lifecycle()
        await tunnel_svc.initialize()
        logger.info("TunnelLifecycleService initialized")
    except Exception as e:
        logger.warning(f"TunnelLifecycleService init failed (non-blocking): {e}")

    try:
        from routes.config import _langchain_installed
        if _langchain_installed():
            logger.info("LangChain: installed (pip packages available in this process)")
        else:
            logger.info("LangChain: not installed — install with: pip install -r requirements-langchain.txt")
    except Exception as e:
        logger.warning("LangChain check failed: %s", e)
    try:
        from app_state import get_langchain_compat_enabled
        compat_enabled = get_langchain_compat_enabled()
        if compat_enabled:
            logger.info("LangChain compat: enabled (langchain availability checked on first chat)")
        else:
            logger.info("LangChain compat: disabled — Chat uses native runner")
    except Exception as e:
        logger.debug("LangChain compat status not logged: %s", e)
    # MCP — load persisted server connections & sync tools to ToolRegistry
    try:
        from agent.mcp_client import get_mcp_manager
        _mcp_cfg = os.path.join(os.path.dirname(__file__), "data", "mcp_servers.json")
        await get_mcp_manager().load_config(_mcp_cfg)

        # Unified Tool Router: 将 MCP 工具注入 ToolRegistry
        from tools.mcp_adapter import sync_mcp_tools_to_registry
        synced = sync_mcp_tools_to_registry(core.registry, get_mcp_manager())
        logger.info("MCP manager initialized (config: %s, synced %d tools)", _mcp_cfg, len(synced))
    except Exception as e:
        logger.warning("MCP manager init skipped: %s", e)
    yield
    # MCP manager shutdown
    try:
        from agent.mcp_client import get_mcp_manager
        await get_mcp_manager().shutdown()
        logger.info("MCP manager shutdown complete")
    except Exception:
        pass
    # Tunnel lifecycle shutdown
    try:
        from services.tunnel_lifecycle import get_tunnel_lifecycle
        await get_tunnel_lifecycle().shutdown()
    except Exception:
        pass
    logger.info("Chow Duck backend shutting down")


# ============== App Creation ==============

app = FastAPI(
    title="Chow Duck Backend",
    description="AI Agent backend for macOS automation",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册所有 HTTP 路由
for r in all_routers:
    app.include_router(r)

# 注册 WebSocket 路由
app.include_router(ws_router)


# ============== Entry Point ==============

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8765,
        reload=True,
        reload_excludes=["venv", "models", "data", "__pycache__", ".git"],
        log_level="info",
        ws_ping_interval=20,
        ws_ping_timeout=120,
        timeout_keep_alive=300,
    )
