"""Memory / Local LLM / Model Selector 路由"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app_state import get_llm_client
from agent.local_llm_manager import get_local_llm_manager
from agent.model_selector import get_model_selector

router = APIRouter()


class ChatMessage(BaseModel):
    content: str
    conversation_id: Optional[str] = None


@router.get("/memory/status")
async def memory_status():
    from agent.vector_store import _vector_stores, get_embedding_model

    model = get_embedding_model()
    model_loaded = model is not None
    model_name = model.get_sentence_embedding_dimension() if model else None

    sessions = {}
    for session_id, store in _vector_stores.items():
        sessions[session_id] = {
            "items": len(store.items),
            "has_embeddings": store._embeddings_matrix is not None,
        }

    return {
        "embedding_model_loaded": model_loaded,
        "embedding_dimension": model_name,
        "sessions": sessions,
        "total_memories": sum(len(s.items) for s in _vector_stores.values()),
    }


@router.get("/local-llm/status")
async def local_llm_status():
    import asyncio
    import httpx
    manager = get_local_llm_manager()

    async def _probe_lm_studio(url_base: str) -> bool:
        base = manager._direct_local_url(url_base).rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3].rstrip("/")
        paths_to_try = [f"{base}/api/v1/models", f"{base}/v1/models"]
        for path in paths_to_try:
            try:
                async with httpx.AsyncClient(timeout=3.0, trust_env=False) as c:
                    resp = await c.get(path, headers={"Accept": "application/json"})
                    if resp.status_code < 500:
                        return True
            except Exception:
                continue
        return False

    async def _probe_ollama() -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0, trust_env=False) as c:
                resp = await c.get("http://127.0.0.1:11434/api/tags", headers={"Accept": "application/json"})
                return resp.status_code < 500
        except Exception:
            return False

    # 并行检测：Ollama 与 LM Studio 互不依赖，无先后顺序
    from config.llm_config import get_lm_studio_base_url
    configured = get_lm_studio_base_url()

    tasks = [
        manager.get_client(force_refresh=True),
        manager.check_ollama(),
        manager.check_lm_studio(),
        _probe_ollama(),
        _probe_lm_studio(configured),
    ]
    if configured != "http://localhost:1234":
        tasks.append(_probe_lm_studio("http://localhost:1234"))

    results = await asyncio.gather(*tasks)
    client, config = results[0]
    ollama_configs = results[1]
    lm_studio_configs = results[2]
    ollama_server_probe = results[3]
    lm_studio_probe_cfg = results[4]
    lm_studio_probe_default = results[5] if len(results) > 5 else False

    ollama_ok = len(ollama_configs) > 0
    ollama_model = ollama_configs[0].model if ollama_configs else None
    lm_studio_ok = len(lm_studio_configs) > 0
    lm_studio_model = lm_studio_configs[0].model if lm_studio_configs else None

    ollama_server_running = ollama_ok or ollama_server_probe
    lm_studio_server_running = lm_studio_ok or lm_studio_probe_cfg or lm_studio_probe_default

    return {
        "current": {
            "provider": config.provider.value,
            "model": config.model,
            "available": client is not None,
        },
        "ollama": {
            "available": ollama_ok,
            "model": ollama_model,
            "server_running": ollama_server_running,
        },
        "lm_studio": {
            "available": lm_studio_ok,
            "model": lm_studio_model,
            "server_running": lm_studio_server_running,
        },
    }


@router.get("/model-selector/status")
async def model_selector_status():
    selector = get_model_selector()
    return selector.get_statistics()


@router.post("/model-selector/analyze")
async def analyze_task(task: ChatMessage):
    selector = get_model_selector()
    manager = get_local_llm_manager()
    _, local_config = await manager.get_client(force_refresh=True)

    from agent.local_llm_manager import LocalLLMProvider
    local_available = local_config.provider != LocalLLMProvider.NONE

    selection = selector.select(
        task=task.content,
        local_available=local_available,
        remote_available=get_llm_client() is not None,
    )
    return selection.to_dict()
