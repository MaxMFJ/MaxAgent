#!/usr/bin/env python3
"""
MacAgent Backend Server
FastAPI server with WebSocket support for the macOS AI Agent
Supports both ReAct and Autonomous execution modes

模块结构：
  main.py              - 入口：lifespan、app 创建、路由注册
  app_state.py         - 全局状态管理（LLM clients、agent_core 等）
  auth.py              - 认证逻辑
  connection_manager.py - WebSocket 连接管理 + 广播
  ws_handler.py        - 主 WebSocket /ws 端点
  routes/              - HTTP 路由模块（按领域拆分）
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    try:
        from github_config import apply_github_config
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

setup_log_capture()


# ============== Lifespan ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 主模型（默认 DeepSeek）
    llm = LLMClient()
    set_llm_client(llm)

    # 云端模型：自主任务选择"远程"时始终使用此客户端
    cloud_llm = LLMClient()
    set_cloud_llm_client(cloud_llm)

    from runtime import get_runtime_adapter
    _adapter = get_runtime_adapter()
    core = AgentCore(llm, runtime_adapter=_adapter)
    set_agent_core(core)

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

    logger.info("MacAgent backend started (ReAct + Autonomous modes with Model Selection)")
    yield
    logger.info("MacAgent backend shutting down")


# ============== App Creation ==============

app = FastAPI(
    title="MacAgent Backend",
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
        ws_ping_interval=30,
        ws_ping_timeout=60,
        timeout_keep_alive=300,
    )
