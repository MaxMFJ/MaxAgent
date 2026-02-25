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
    manager = get_local_llm_manager()
    client, config = await manager.get_client(force_refresh=True)
    ollama_ok, ollama_model = await manager.check_ollama()
    lm_studio_ok, lm_studio_model = await manager.check_lm_studio()

    return {
        "current": {
            "provider": config.provider.value,
            "model": config.model,
            "available": client is not None,
        },
        "ollama": {"available": ollama_ok, "model": ollama_model},
        "lm_studio": {"available": lm_studio_ok, "model": lm_studio_model},
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
