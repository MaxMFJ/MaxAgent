#!/usr/bin/env python3
"""
MacAgent Backend Server
FastAPI server with WebSocket support for the macOS AI Agent
Supports both ReAct and Autonomous execution modes
"""
import os
# 尽早加载 .env，供 Cursor CLI 等子进程继承 CURSOR_API_KEY
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass
import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Optional, Dict, Set
from datetime import datetime
from enum import Enum

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.core import AgentCore
from agent.llm_client import LLMClient, LLMConfig
from agent.autonomous_agent import AutonomousAgent
from agent.reflect_engine import get_reflect_engine
from agent.episodic_memory import get_episodic_memory, get_strategy_db, Episode
from agent.local_llm_manager import get_local_llm_manager
from agent.model_selector import get_model_selector
from agent.self_healing import (
    SelfHealingAgent, get_self_healing_agent,
    DiagnosticEngine, get_diagnostic_engine,
    ProblemType
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 减少 uvicorn access log 的噪音
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


# ============== Server Status (升级状态) ==============

class ServerStatus(str, Enum):
    """服务端状态"""
    NORMAL = "normal"
    UPGRADING = "upgrading"
    RESTARTING = "restarting"


# 全局服务状态
server_status: ServerStatus = ServerStatus.NORMAL


# ============== Multi-Client Connection Management ==============

class ClientType(str, Enum):
    """客户端类型"""
    MAC = "mac"
    IOS = "ios"
    UNKNOWN = "unknown"


@dataclass
class ClientConnection:
    """客户端连接信息"""
    websocket: WebSocket
    client_id: str
    client_type: ClientType
    session_id: str
    connected_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)


class ConnectionManager:
    """管理所有 WebSocket 连接，支持多客户端同步"""
    
    def __init__(self):
        self._connections: Dict[str, ClientConnection] = {}
        self._session_connections: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()
    
    def get_server_status(self) -> ServerStatus:
        return server_status
    
    async def connect(
        self, 
        websocket: WebSocket, 
        client_id: str,
        client_type: ClientType = ClientType.UNKNOWN,
        session_id: str = "default"
    ) -> ClientConnection:
        """注册新连接"""
        async with self._lock:
            conn = ClientConnection(
                websocket=websocket,
                client_id=client_id,
                client_type=client_type,
                session_id=session_id
            )
            self._connections[client_id] = conn
            
            if session_id not in self._session_connections:
                self._session_connections[session_id] = set()
            self._session_connections[session_id].add(client_id)
            
            logger.info(f"Client connected: {client_id} ({client_type.value}), session: {session_id}")
            return conn
    
    async def disconnect(self, client_id: str):
        """断开连接"""
        async with self._lock:
            if client_id in self._connections:
                conn = self._connections[client_id]
                session_id = conn.session_id
                
                del self._connections[client_id]
                
                if session_id in self._session_connections:
                    self._session_connections[session_id].discard(client_id)
                    if not self._session_connections[session_id]:
                        del self._session_connections[session_id]
                
                logger.info(f"Client disconnected: {client_id}")
    
    async def broadcast_to_session(self, session_id: str, message: dict, exclude_client: str = None):
        """向会话内所有客户端广播消息"""
        if session_id not in self._session_connections:
            return
        
        client_ids = list(self._session_connections[session_id])
        disconnected = []
        
        for client_id in client_ids:
            if client_id == exclude_client:
                continue
            
            if client_id in self._connections:
                conn = self._connections[client_id]
                try:
                    await conn.websocket.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send to {client_id}: {e}")
                    disconnected.append(client_id)
        
        for client_id in disconnected:
            await self.disconnect(client_id)
    
    async def broadcast_all(self, message: dict, exclude_client: str = None):
        """向所有连接的客户端广播消息"""
        client_ids = list(self._connections.keys())
        disconnected = []
        
        for client_id in client_ids:
            if client_id == exclude_client:
                continue
            
            if client_id in self._connections:
                conn = self._connections[client_id]
                try:
                    await conn.websocket.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send to {client_id}: {e}")
                    disconnected.append(client_id)
        
        for client_id in disconnected:
            await self.disconnect(client_id)
    
    def get_connection(self, client_id: str) -> Optional[ClientConnection]:
        """获取连接信息"""
        return self._connections.get(client_id)
    
    def get_session_clients(self, session_id: str) -> list:
        """获取会话内的所有客户端"""
        if session_id not in self._session_connections:
            return []
        return [
            {
                "client_id": cid,
                "client_type": self._connections[cid].client_type.value,
                "connected_at": self._connections[cid].connected_at.isoformat()
            }
            for cid in self._session_connections[session_id]
            if cid in self._connections
        ]
    
    def get_stats(self) -> dict:
        """获取连接统计"""
        type_counts = {}
        for conn in self._connections.values():
            t = conn.client_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        
        return {
            "total_connections": len(self._connections),
            "sessions": len(self._session_connections),
            "by_type": type_counts
        }


# 全局连接管理器
connection_manager = ConnectionManager()

# 会话级流任务：session_id -> asyncio.Task，用于终止任务
_session_stream_tasks: Dict[str, asyncio.Task] = {}


async def _broadcast_status_change(status: str, message: str = ""):
    """广播状态变更给所有连接"""
    global server_status
    if status in [e.value for e in ServerStatus]:
        server_status = ServerStatus(status)
    msg = {
        "type": "status_change",
        "status": status,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }
    await connection_manager.broadcast_all(msg)


async def _broadcast_upgrade_message(msg: dict):
    """广播升级相关消息给所有连接"""
    await connection_manager.broadcast_all(msg)


async def _trigger_tool_upgrade(reason: str, user_message: str, session_id: str = "default"):
    """触发工具自我升级流程"""
    try:
        from agent.tool_upgrade_orchestrator import get_upgrade_orchestrator
        orchestrator = get_upgrade_orchestrator()
        async for progress in orchestrator.execute_upgrade(reason, user_message, session_id):
            logger.info(f"Upgrade progress: {progress.get('type')} {progress.get('phase', '')}")
            # 闭环：将 upgrade_complete / upgrade_error 广播给客户端
            if progress.get("type") == "upgrade_complete":
                await _broadcast_upgrade_message(progress)
            elif progress.get("type") == "upgrade_error":
                await _broadcast_upgrade_message(progress)
    except Exception as e:
        logger.error(f"Tool upgrade trigger failed: {e}")
        await _broadcast_status_change("normal", f"升级失败: {str(e)}")
        await _broadcast_upgrade_message({"type": "upgrade_error", "error": str(e)})


def _load_generated_tools() -> list:
    """动态加载 tools/generated/ 下的新工具"""
    if not agent_core:
        return []
    return agent_core.registry.load_generated_tools(agent_core.runtime_adapter)


async def _trigger_restart(delay_seconds: int = 5):
    """
    重启前通知流程：广播 restarting 状态，下发「即将重启」，延迟后退出
    进程管理器（如 launchd、systemd）负责重启
    """
    global server_status
    server_status = ServerStatus.RESTARTING
    await _broadcast_status_change("restarting", "系统即将重启，请稍候...")
    await _broadcast_upgrade_message({
        "type": "content",
        "content": "⏳ 系统即将重启，请稍候重连...",
        "is_system": True
    })
    logger.info(f"Restarting in {delay_seconds}s...")
    await asyncio.sleep(delay_seconds)
    import sys
    sys.exit(0)


async def safe_send_json(websocket: WebSocket, message: dict) -> bool:
    """
    安全发送 JSON，客户端已断开时捕获异常。
    返回 True 表示发送成功，False 表示连接已断开（调用方应停止发送并退出循环）。
    """
    try:
        await websocket.send_json(message)
        return True
    except WebSocketDisconnect:
        logger.debug("Client disconnected during send")
        return False
    except Exception as e:
        err_msg = str(e).lower()
        if "not connected" in err_msg or "accept" in err_msg or "1006" in err_msg:
            logger.debug(f"WebSocket closed, skip send: {e}")
            return False
        raise


# ============== Authentication ==============

AUTH_TOKEN: Optional[str] = os.environ.get("MACAGENT_AUTH_TOKEN")
AUTH_ENABLED: bool = os.environ.get("MACAGENT_AUTH_ENABLED", "false").lower() == "true"

# 工具自我升级：检测到无法执行时是否自动触发
AUTO_TOOL_UPGRADE: bool = os.environ.get("MACAGENT_AUTO_TOOL_UPGRADE", "true").lower() == "true"


def generate_auth_token() -> str:
    """生成新的认证 token"""
    return secrets.token_urlsafe(32)


def verify_token(token: Optional[str]) -> bool:
    """验证 token"""
    if not AUTH_ENABLED:
        return True
    if not AUTH_TOKEN:
        return True
    return token == AUTH_TOKEN


class ConfigUpdate(BaseModel):
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


class SmtpConfigUpdate(BaseModel):
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None


class ChatMessage(BaseModel):
    content: str
    conversation_id: Optional[str] = None


llm_client: Optional[LLMClient] = None  # Remote LLM (DeepSeek/OpenAI)
local_llm_client: Optional[LLMClient] = None  # Local LLM (Ollama/LM Studio)
agent_core: Optional[AgentCore] = None
autonomous_agent: Optional[AutonomousAgent] = None
reflect_llm: Optional[LLMClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm_client, local_llm_client, agent_core, autonomous_agent, reflect_llm
    
    # Initialize remote LLM (DeepSeek/OpenAI)
    llm_client = LLMClient()
    from runtime import get_runtime_adapter
    _adapter = get_runtime_adapter()
    agent_core = AgentCore(llm_client, runtime_adapter=_adapter)
    
    # Initialize local LLM (Ollama) - for model selection feature
    local_llm_client = LLMClient(LLMConfig(
        provider="ollama",
        base_url="http://localhost:11434/v1",
        model="qwen2.5-coder:7b",
        api_key="ollama"
    ))
    
    # Initialize reflect LLM (also Ollama local, can use different model)
    reflect_llm = LLMClient(LLMConfig(
        provider="ollama",
        base_url="http://localhost:11434/v1",
        model="qwen2.5:7b",
        api_key="ollama"
    ))
    
    # Initialize autonomous agent with both remote and local LLMs
    autonomous_agent = AutonomousAgent(
        llm_client=llm_client,
        local_llm_client=local_llm_client,
        reflect_llm=reflect_llm,
        runtime_adapter=_adapter,
        enable_reflection=True,
        enable_model_selection=True  # Enable intelligent model selection
    )
    
    # 后台预加载向量模型（不阻塞启动）
    try:
        from agent.vector_store import preload_embedding_model
        preload_embedding_model()
    except Exception as e:
        logger.warning(f"Failed to start model preloading: {e}")
    
    # 初始化工具升级编排器（注入 Git、广播、动态加载、重启回调）
    try:
        from agent.tool_upgrade_orchestrator import get_upgrade_orchestrator
        from agent.upgrade_git import git_checkpoint, git_rollback
        get_upgrade_orchestrator(
            llm_client=llm_client,
            on_status_change=_broadcast_status_change,
            on_broadcast=_broadcast_upgrade_message,
            on_load_generated_tools=_load_generated_tools,
            on_trigger_restart=lambda: _trigger_restart(5),
            on_git_checkpoint=git_checkpoint,
            on_git_rollback=git_rollback
        )
        logger.info("Tool upgrade orchestrator initialized")
    except Exception as e:
        logger.warning(f"Tool upgrade orchestrator init skipped: {e}")

    # EventBus 解耦服务：注入主循环，ErrorService、SelfHealingWorker、UpgradeService
    try:
        import asyncio
        from agent.event_bus import get_event_bus
        from agent.error_service import get_error_service
        from agent.self_healing_worker import get_self_healing_worker
        from agent.upgrade_service import get_upgrade_service

        get_event_bus().set_loop(asyncio.get_running_loop())

        async def _broadcast_to_session(sid: str, chunk: dict):
            await connection_manager.broadcast_to_session(sid, chunk)

        get_error_service()
        get_self_healing_worker(on_broadcast=lambda sid, c: _broadcast_to_session(sid, c))
        get_upgrade_service(
            on_trigger_upgrade=_trigger_tool_upgrade,
            on_broadcast=lambda sid, c: _broadcast_to_session(sid, c),
            auto_upgrade=AUTO_TOOL_UPGRADE,
        )
        logger.info("EventBus services (Error, SelfHealing, Upgrade) initialized")
    except Exception as e:
        logger.warning(f"EventBus services init skipped: {e}")
    
    logger.info("MacAgent backend started (ReAct + Autonomous modes with Model Selection)")
    yield
    logger.info("MacAgent backend shutting down")


app = FastAPI(
    title="MacAgent Backend",
    description="AI Agent backend for macOS automation",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint，包含服务状态（normal/upgrading/restarting）"""
    return {
        "status": "healthy",
        "server_status": server_status.value,
        "provider": llm_client.config.provider if llm_client else None,
        "model": llm_client.config.model if llm_client else None
    }


@app.get("/server-status")
async def get_server_status():
    """获取服务状态（normal/upgrading/restarting）"""
    return {"server_status": server_status.value}


class UpgradeTriggerRequest(BaseModel):
    reason: str
    user_message: str


@app.post("/upgrade/trigger")
async def trigger_upgrade(request: UpgradeTriggerRequest):
    """手动触发工具自我升级"""
    if server_status == ServerStatus.UPGRADING:
        raise HTTPException(status_code=409, detail="升级已在进行中")
    asyncio.create_task(_trigger_tool_upgrade(
        request.reason, request.user_message, "default"
    ))
    return {"status": "triggered", "message": "升级流程已启动"}


class ToolApproveRequest(BaseModel):
    tool_name: str
    file_path: Optional[str] = None  # 可选，默认 tools/generated/{tool_name}_tool.py


@app.post("/tools/approve")
async def approve_tool(request: ToolApproveRequest):
    """人工审批工具：将 hash 加入 signatures.json，允许加载"""
    try:
        from agent.upgrade_security import approve_tool as do_approve
        import os
        fp = request.file_path
        if not fp:
            fp = os.path.join(
                os.path.dirname(__file__), "tools", "generated",
                f"{request.tool_name.replace('_tool','')}_tool.py"
            )
            if not os.path.exists(fp):
                fp = os.path.join(
                    os.path.dirname(__file__), "tools", "generated",
                    f"{request.tool_name}.py"
                )
        ok, msg = do_approve(fp, request.tool_name)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"status": "approved", "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tools/reload")
async def reload_tools():
    """动态加载 tools/generated/ 下的新工具，无需重启"""
    if not agent_core:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    loaded = _load_generated_tools()
    return {"status": "ok", "loaded_tools": loaded}


@app.post("/upgrade/restart")
async def trigger_restart_endpoint(delay: int = 5):
    """触发重启流程：先广播 restarting 和「即将重启」，延迟后退出"""
    if server_status == ServerStatus.UPGRADING:
        raise HTTPException(status_code=409, detail="升级进行中，请稍后再试")
    asyncio.create_task(_trigger_restart(min(max(delay, 2), 30)))
    return {"status": "triggered", "message": f"将在 {delay} 秒后重启"}


@app.get("/connections")
async def get_connections():
    """获取当前连接统计"""
    return connection_manager.get_stats()


@app.get("/auth/status")
async def auth_status():
    """获取认证状态"""
    return {
        "auth_enabled": AUTH_ENABLED,
        "has_token": AUTH_TOKEN is not None
    }


@app.post("/auth/generate-token")
async def generate_token():
    """生成新的认证 token（仅限本地访问）"""
    global AUTH_TOKEN, AUTH_ENABLED
    AUTH_TOKEN = generate_auth_token()
    AUTH_ENABLED = True
    return {
        "token": AUTH_TOKEN,
        "message": "Token generated. Share this with your iOS device."
    }


@app.post("/auth/disable")
async def disable_auth():
    """禁用认证（仅限本地访问）"""
    global AUTH_ENABLED
    AUTH_ENABLED = False
    return {"message": "Authentication disabled"}


# 日志缓冲区
_log_buffer: list = []
_max_log_entries = 200

class LogCapture(logging.Handler):
    """Capture logs to buffer for API access"""
    def emit(self, record):
        from datetime import datetime
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": record.levelname,
            "message": self.format(record)
        }
        _log_buffer.append(log_entry)
        if len(_log_buffer) > _max_log_entries:
            _log_buffer.pop(0)

# 添加日志捕获处理器
_log_handler = LogCapture()
_log_handler.setLevel(logging.INFO)
_log_handler.setFormatter(logging.Formatter('%(name)s - %(message)s'))
logging.getLogger().addHandler(_log_handler)


@app.get("/logs")
async def get_logs(limit: int = 100, since_index: int = 0):
    """Get recent logs for frontend display"""
    logs = _log_buffer[since_index:since_index + limit]
    return {
        "logs": logs,
        "total": len(_log_buffer),
        "next_index": since_index + len(logs)
    }


@app.delete("/logs")
async def clear_logs():
    """Clear log buffer"""
    _log_buffer.clear()
    return {"status": "cleared"}


@app.get("/config")
async def get_config():
    """Get current configuration"""
    if not llm_client:
        raise HTTPException(status_code=500, detail="LLM client not initialized")
    return {
        "provider": llm_client.config.provider,
        "model": llm_client.config.model,
        "base_url": llm_client.config.base_url,
        "has_api_key": bool(llm_client.config.api_key)
    }


@app.post("/config")
async def update_config(config: ConfigUpdate):
    """Update LLM configuration"""
    global llm_client, agent_core, autonomous_agent
    
    current_config = llm_client.config if llm_client else LLMConfig()
    
    new_config = LLMConfig(
        provider=config.provider or current_config.provider,
        api_key=config.api_key or current_config.api_key,
        base_url=config.base_url or current_config.base_url,
        model=config.model or current_config.model
    )
    
    # 只更新 LLM client，保留 agent_core 和上下文
    new_llm_client = LLMClient(new_config)
    
    if agent_core:
        # 更新现有 agent 的 LLM client，保留上下文
        agent_core.llm = new_llm_client
        llm_client = new_llm_client
    else:
        llm_client = new_llm_client
        from runtime import get_runtime_adapter
        agent_core = AgentCore(llm_client, runtime_adapter=get_runtime_adapter())
    
    # 同时更新自主 agent
    if autonomous_agent:
        autonomous_agent.update_llm(new_llm_client)
    
    # 同步更新升级编排器的 LLM（否则升级流程仍用启动时的 dummy API key）
    try:
        from agent.tool_upgrade_orchestrator import get_upgrade_orchestrator
        get_upgrade_orchestrator().update_llm(new_llm_client)
    except Exception:
        pass
    
    return {"status": "updated", "provider": new_config.provider, "model": new_config.model}


@app.get("/config/smtp")
async def get_smtp_config_endpoint():
    """获取 SMTP 配置（不含密码）"""
    from smtp_config import load_smtp_config
    cfg = load_smtp_config()
    return {
        "smtp_server": cfg.get("smtp_server", ""),
        "smtp_port": cfg.get("smtp_port", 465),
        "smtp_user": cfg.get("smtp_user", ""),
        "configured": bool(cfg.get("smtp_server") and cfg.get("smtp_user") and cfg.get("smtp_password"))
    }


@app.post("/config/smtp")
async def update_smtp_config_endpoint(config: SmtpConfigUpdate):
    """更新 SMTP 配置（Mac 设置页同步）"""
    from smtp_config import update_smtp_config
    result = update_smtp_config(
        smtp_server=config.smtp_server,
        smtp_port=config.smtp_port,
        smtp_user=config.smtp_user,
        smtp_password=config.smtp_password,
    )
    return {"status": "updated", **result}


@app.get("/tools")
async def list_tools():
    """List available tools"""
    if not agent_core:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    return {"tools": [tool.to_function_schema() for tool in agent_core.tools]}


@app.get("/memory/status")
async def memory_status():
    """Get vector memory status"""
    from agent.vector_store import _vector_stores, get_embedding_model
    
    model = get_embedding_model()
    model_loaded = model is not None
    model_name = model.get_sentence_embedding_dimension() if model else None
    
    sessions = {}
    for session_id, store in _vector_stores.items():
        sessions[session_id] = {
            "items": len(store.items),
            "has_embeddings": store._embeddings_matrix is not None
        }
    
    return {
        "embedding_model_loaded": model_loaded,
        "embedding_dimension": model_name,
        "sessions": sessions,
        "total_memories": sum(len(s.items) for s in _vector_stores.values())
    }


@app.get("/local-llm/status")
async def local_llm_status():
    """Check local LLM services (Ollama, LM Studio) status"""
    manager = get_local_llm_manager()
    
    # Force refresh to get current status
    client, config = await manager.get_client(force_refresh=True)
    
    # Also check both services explicitly
    ollama_ok, ollama_model = await manager.check_ollama()
    lm_studio_ok, lm_studio_model = await manager.check_lm_studio()
    
    return {
        "current": {
            "provider": config.provider.value,
            "model": config.model,
            "available": client is not None
        },
        "ollama": {
            "available": ollama_ok,
            "model": ollama_model
        },
        "lm_studio": {
            "available": lm_studio_ok,
            "model": lm_studio_model
        }
    }


@app.get("/model-selector/status")
async def model_selector_status():
    """Get model selector status and learned strategies"""
    selector = get_model_selector()
    return selector.get_statistics()


@app.post("/model-selector/analyze")
async def analyze_task(task: ChatMessage):
    """Analyze a task and recommend a model"""
    selector = get_model_selector()
    
    # Check availability
    manager = get_local_llm_manager()
    _, local_config = await manager.get_client(force_refresh=True)
    
    from agent.local_llm_manager import LocalLLMProvider
    local_available = local_config.provider != LocalLLMProvider.NONE
    
    selection = selector.select(
        task=task.content,
        local_available=local_available,
        remote_available=llm_client is not None
    )
    
    return selection.to_dict()


# ============== Self-Healing System ==============

class DiagnoseRequest(BaseModel):
    error_message: str
    stack_trace: str = ""
    context: Optional[dict] = None


class HealRequest(BaseModel):
    error_message: str
    stack_trace: str = ""
    context: Optional[dict] = None
    auto_confirm: bool = False


@app.get("/self-healing/status")
async def self_healing_status():
    """Get self-healing system status and statistics"""
    agent = get_self_healing_agent()
    return {
        "current_status": agent.current_status.value,
        "statistics": agent.get_statistics(),
        "recent_healings": agent.get_recent_healings(5)
    }


@app.post("/self-healing/diagnose")
async def diagnose_problem(request: DiagnoseRequest):
    """Diagnose a problem without attempting repair"""
    engine = get_diagnostic_engine()
    result = engine.diagnose(
        error_message=request.error_message,
        stack_trace=request.stack_trace,
        context=request.context or {}
    )
    return result.to_dict()


@app.post("/self-healing/plan")
async def create_repair_plan(request: DiagnoseRequest):
    """Create a repair plan for a diagnosed problem"""
    agent = get_self_healing_agent()
    
    diagnostic = agent.diagnose_only(
        error_message=request.error_message,
        stack_trace=request.stack_trace,
        context=request.context or {}
    )
    
    plan = agent.plan_only(diagnostic, request.context or {})
    
    return {
        "diagnostic": diagnostic.to_dict(),
        "plan": plan.to_dict()
    }


@app.websocket("/ws/self-healing")
async def self_healing_websocket(websocket: WebSocket):
    """WebSocket endpoint for streaming self-healing process"""
    await websocket.accept()
    logger.info("Self-healing WebSocket connected")
    
    try:
        while True:
            message = await websocket.receive_json()
            
            if message.get("type") == "heal":
                # Execute self-healing
                agent = get_self_healing_agent()
                
                async for update in agent.heal(
                    error_message=message.get("error_message", ""),
                    stack_trace=message.get("stack_trace", ""),
                    context={
                        **(message.get("context") or {}),
                        "auto_confirm": message.get("auto_confirm", False),
                        "confirmed": message.get("confirmed", False)
                    }
                ):
                    await websocket.send_json(update)
            
            elif message.get("type") == "confirm":
                # User confirms a repair plan
                await websocket.send_json({
                    "type": "confirmation_received",
                    "message": "确认已收到，继续执行修复..."
                })
            
            elif message.get("type") == "get_statistics":
                agent = get_self_healing_agent()
                await websocket.send_json({
                    "type": "statistics",
                    "data": agent.get_statistics()
                })
            
            elif message.get("type") == "get_history":
                agent = get_self_healing_agent()
                count = message.get("count", 10)
                await websocket.send_json({
                    "type": "history",
                    "data": agent.get_recent_healings(count)
                })
    
    except WebSocketDisconnect:
        logger.info("Self-healing WebSocket disconnected")
    except Exception as e:
        logger.error(f"Self-healing WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass


@app.post("/chat")
async def chat(message: ChatMessage):
    """Non-streaming chat endpoint"""
    if not agent_core:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        session_id = message.conversation_id or "default"
        response = await agent_core.run(message.content, session_id=session_id)
        return {"response": response}
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    client_type: Optional[str] = Query("unknown"),
    client_id: Optional[str] = Query(None)
):
    """WebSocket endpoint for streaming chat with multi-client support"""
    
    # 验证 token
    if not verify_token(token):
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    await websocket.accept()
    
    # 生成客户端 ID
    actual_client_id = client_id or f"client_{secrets.token_hex(8)}"
    actual_client_type = ClientType(client_type) if client_type in [e.value for e in ClientType] else ClientType.UNKNOWN
    
    # 注册连接
    current_session_id = "default"
    conn = await connection_manager.connect(
        websocket=websocket,
        client_id=actual_client_id,
        client_type=actual_client_type,
        session_id=current_session_id
    )
    
    logger.info(f"WebSocket connection established: {actual_client_id} ({actual_client_type.value})")
    
    # 发送连接确认（包含当前服务状态）
    await safe_send_json(websocket, {
        "type": "connected",
        "client_id": actual_client_id,
        "session_id": current_session_id,
        "clients_in_session": connection_manager.get_session_clients(current_session_id),
        "server_status": server_status.value
    })
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # 更新活动时间
            conn.last_activity = datetime.now()
            
            if message.get("type") == "stop":
                session_id = message.get("session_id") or message.get("conversation_id") or current_session_id
                task = _session_stream_tasks.get(session_id)
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    _session_stream_tasks.pop(session_id, None)
                    stopped_msg = {"type": "stopped", "session_id": session_id}
                    await safe_send_json(websocket, stopped_msg)
                    await connection_manager.broadcast_to_session(session_id, stopped_msg, exclude_client=actual_client_id)
                    logger.info(f"Stream stopped by user (session: {session_id})")
                continue
            
            elif message.get("type") == "chat":
                content = message.get("content", "")
                session_id = message.get("session_id") or message.get("conversation_id") or current_session_id
                current_session_id = session_id
                
                logger.info(f"Received chat message (session: {session_id}): {content[:100]}...")
                
                await connection_manager.broadcast_to_session(
                    session_id,
                    {
                        "type": "user_message",
                        "content": content,
                        "from_client": actual_client_id,
                        "from_client_type": actual_client_type.value,
                        "timestamp": datetime.now().isoformat()
                    },
                    exclude_client=actual_client_id
                )
                
                if not agent_core:
                    logger.error("Agent not initialized!")
                    await safe_send_json(websocket, {"type": "error", "message": "Agent not initialized"})
                    continue
                
                if session_id in _session_stream_tasks:
                    old_task = _session_stream_tasks[session_id]
                    if not old_task.done():
                        old_task.cancel()
                        try:
                            await old_task
                        except asyncio.CancelledError:
                            pass
                    _session_stream_tasks.pop(session_id, None)
                
                async def _run_stream_and_send():
                    nonlocal session_id, actual_client_id, content
                    chunk_count = 0
                    has_error = False
                    client_gone = False
                    total_usage = None
                    extra_system_prompt = ""
                    try:
                        # 联网增强（从 Core 抽离到 main）
                        try:
                            from agent.web_augmented_thinking import ThinkingAugmenter
                            aug = ThinkingAugmenter()
                            a = await aug.augment(content)
                            if a and a.get("success"):
                                extra_system_prompt = aug.format_augmentation_for_llm(a)
                                if extra_system_prompt:
                                    web_chunk = {"type": "web_augmentation", "augmentation_type": a.get("type"), "query": a.get("query"), "success": True}
                                    if not await safe_send_json(websocket, web_chunk):
                                        client_gone = True
                                    if not client_gone:
                                        await connection_manager.broadcast_to_session(session_id, web_chunk, exclude_client=actual_client_id)
                        except Exception as e:
                            logger.warning(f"Web augmentation failed: {e}")

                        async for chunk in agent_core.run_stream(content, session_id=session_id, extra_system_prompt=extra_system_prompt):
                            chunk_count += 1
                            chunk_type = chunk.get('type', 'unknown')
                            if chunk_type == 'stream_end':
                                total_usage = chunk.get('usage')
                                continue
                            # tool_result: 抽取图片并下发，不向前端传 data
                            if chunk_type == 'tool_result':
                                data = chunk.pop('data', None)
                                to_send = {k: v for k, v in chunk.items()}
                                if not await safe_send_json(websocket, to_send):
                                    client_gone = True
                                    break
                                await connection_manager.broadcast_to_session(session_id, to_send, exclude_client=actual_client_id)
                                if data:
                                    from agent.image_extractor import extract_image_from_result
                                    img = extract_image_from_result(data)
                                    if img:
                                        if not await safe_send_json(websocket, img):
                                            client_gone = True
                                            break
                                        await connection_manager.broadcast_to_session(session_id, img, exclude_client=actual_client_id)
                            else:
                                if not await safe_send_json(websocket, chunk):
                                    client_gone = True
                                    break
                                await connection_manager.broadcast_to_session(session_id, chunk, exclude_client=actual_client_id)
                            if chunk_type == 'error':
                                has_error = True
                            if client_gone:
                                break
                        if client_gone:
                            raise WebSocketDisconnect(code=1006)
                        if not has_error:
                            model_name = agent_core.llm.config.model if agent_core and agent_core.llm else None
                            done_msg = {"type": "done", "model": model_name}
                            if total_usage:
                                done_msg["usage"] = total_usage
                            await safe_send_json(websocket, done_msg)
                            await connection_manager.broadcast_to_session(session_id, done_msg, exclude_client=actual_client_id)
                    except asyncio.CancelledError:
                        stopped_msg = {"type": "stopped", "session_id": session_id}
                        await safe_send_json(websocket, stopped_msg)
                        await connection_manager.broadcast_to_session(session_id, stopped_msg, exclude_client=actual_client_id)
                        raise
                    except WebSocketDisconnect:
                        raise
                    except Exception as e:
                        logger.error(f"Error in stream: {e}", exc_info=True)
                        await safe_send_json(websocket, {"type": "error", "message": str(e)})
                    finally:
                        _session_stream_tasks.pop(session_id, None)
                
                _session_stream_tasks[session_id] = asyncio.create_task(_run_stream_and_send())
            
            elif message.get("type") == "ping":
                await safe_send_json(websocket, {"type": "pong"})
            
            elif message.get("type") == "new_session":
                # 支持创建新会话
                session_id = message.get("session_id", f"session_{id(websocket)}")
                old_session_id = current_session_id
                current_session_id = session_id
                
                # 更新连接管理器中的会话
                async with connection_manager._lock:
                    if actual_client_id in connection_manager._connections:
                        connection_manager._connections[actual_client_id].session_id = session_id
                        # 从旧会话移除
                        if old_session_id in connection_manager._session_connections:
                            connection_manager._session_connections[old_session_id].discard(actual_client_id)
                        # 加入新会话
                        if session_id not in connection_manager._session_connections:
                            connection_manager._session_connections[session_id] = set()
                        connection_manager._session_connections[session_id].add(actual_client_id)
                
                logger.info(f"New session created: {session_id}")
                await safe_send_json(websocket, {
                    "type": "session_created", 
                    "session_id": session_id,
                    "clients_in_session": connection_manager.get_session_clients(session_id)
                })
            
            elif message.get("type") == "clear_session":
                # 支持清除会话历史
                session_id = message.get("session_id") or current_session_id
                if agent_core:
                    agent_core.reset_conversation(session_id)
                    logger.info(f"Session cleared: {session_id}")
                await safe_send_json(websocket, {"type": "session_cleared", "session_id": session_id})
                # 广播给同一会话的其他客户端
                await connection_manager.broadcast_to_session(
                    session_id,
                    {"type": "session_cleared", "session_id": session_id, "by_client": actual_client_id},
                    exclude_client=actual_client_id
                )
            
            elif message.get("type") == "autonomous_task":
                # 自主执行模式
                task = message.get("task", "")
                session_id = message.get("session_id") or current_session_id
                
                # Apply model selection settings from client
                enable_model_selection = message.get("enable_model_selection", True)
                prefer_local = message.get("prefer_local", False)
                
                if autonomous_agent:
                    autonomous_agent.enable_model_selection = enable_model_selection
                    autonomous_agent._prefer_local = prefer_local
                
                logger.info(f"Received autonomous task (session: {session_id}): {task[:100]}...")
                
                # 广播任务开始给同一会话的其他客户端
                await connection_manager.broadcast_to_session(
                    session_id,
                    {
                        "type": "autonomous_task_started",
                        "task": task,
                        "from_client": actual_client_id,
                        "from_client_type": actual_client_type.value,
                        "timestamp": datetime.now().isoformat()
                    },
                    exclude_client=actual_client_id
                )
                
                if not autonomous_agent:
                    await safe_send_json(websocket, {"type": "error", "message": "Autonomous agent not initialized"})
                    continue
                
                try:
                    client_gone = False
                    async for chunk in autonomous_agent.run_autonomous(task, session_id=session_id):
                        if not await safe_send_json(websocket, chunk):
                            client_gone = True
                            break
                        
                        # 广播给同一会话的其他客户端
                        await connection_manager.broadcast_to_session(
                            session_id, chunk, exclude_client=actual_client_id
                        )
                        
                        # 如果任务完成，保存到经验记忆
                        if chunk.get("type") == "task_complete":
                            try:
                                memory = get_episodic_memory()
                                episode = Episode(
                                    episode_id=chunk.get("task_id", ""),
                                    task_description=task,
                                    result=chunk.get("summary", ""),
                                    success=chunk.get("success", False),
                                    total_actions=chunk.get("total_actions", 0),
                                    total_iterations=chunk.get("iterations", 0),
                                    token_usage=chunk.get("token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
                                )
                                memory.add_episode(episode)
                            except Exception as e:
                                logger.error(f"Failed to save episode: {e}")
                    
                    if client_gone:
                        raise WebSocketDisconnect(code=1006)
                    
                    done_msg = {"type": "done"}
                    await safe_send_json(websocket, done_msg)
                    await connection_manager.broadcast_to_session(
                        session_id, done_msg, exclude_client=actual_client_id
                    )
                    
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    logger.error(f"Error in autonomous execution: {e}", exc_info=True)
                    await safe_send_json(websocket, {"type": "error", "message": str(e)})
            
            elif message.get("type") == "get_episodes":
                # 获取历史任务执行记录
                try:
                    memory = get_episodic_memory()
                    episodes = memory.get_recent(count=message.get("count", 10))
                    await safe_send_json(websocket, {
                        "type": "episodes",
                        "episodes": [ep.to_dict() for ep in episodes]
                    })
                except Exception as e:
                    await safe_send_json(websocket, {"type": "error", "message": str(e)})
            
            elif message.get("type") == "get_statistics":
                # 获取执行统计
                try:
                    memory = get_episodic_memory()
                    stats = memory.get_statistics()
                    strategies = get_strategy_db().get_top_strategies(5)
                    await safe_send_json(websocket, {
                        "type": "statistics",
                        "stats": stats,
                        "top_strategies": strategies
                    })
                except Exception as e:
                    await safe_send_json(websocket, {"type": "error", "message": str(e)})
            
            elif message.get("type") == "get_model_stats":
                # 获取模型选择统计
                try:
                    selector = get_model_selector()
                    stats = selector.get_statistics()
                    await safe_send_json(websocket, {
                        "type": "model_stats",
                        "stats": stats
                    })
                except Exception as e:
                    await safe_send_json(websocket, {"type": "error", "message": str(e)})
            
            elif message.get("type") == "analyze_task":
                # 分析任务并推荐模型
                try:
                    task_content = message.get("task", "")
                    selector = get_model_selector()
                    
                    manager = get_local_llm_manager()
                    _, local_config = await manager.get_client(force_refresh=True)
                    
                    from agent.local_llm_manager import LocalLLMProvider
                    local_available = local_config.provider != LocalLLMProvider.NONE
                    
                    selection = selector.select(
                        task=task_content,
                        local_available=local_available,
                        remote_available=llm_client is not None
                    )
                    
                    await safe_send_json(websocket, {
                        "type": "task_analysis",
                        "selection": selection.to_dict()
                    })
                except Exception as e:
                    await safe_send_json(websocket, {"type": "error", "message": str(e)})
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {actual_client_id}")
        # 广播断开连接事件
        await connection_manager.broadcast_to_session(
            current_session_id,
            {
                "type": "client_disconnected",
                "client_id": actual_client_id,
                "client_type": actual_client_type.value
            },
            exclude_client=actual_client_id
        )
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await safe_send_json(websocket, {"type": "error", "message": str(e)})
    finally:
        # 清理连接
        await connection_manager.disconnect(actual_client_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8765,
        reload=True,
        reload_excludes=["**/tools/generated/*"],  # 工具升级写入新文件不触发重启，避免断开连接
        log_level="info",
        ws_ping_interval=None,  # 禁用服务端 ping
        ws_ping_timeout=None,   # 禁用 ping 超时
        timeout_keep_alive=300  # 5分钟 keep-alive
    )
