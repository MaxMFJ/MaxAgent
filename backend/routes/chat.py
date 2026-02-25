"""非流式 Chat 路由"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app_state import get_agent_core

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatMessage(BaseModel):
    content: str
    conversation_id: Optional[str] = None


@router.post("/chat")
async def chat(message: ChatMessage):
    agent_core = get_agent_core()
    if not agent_core:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    try:
        session_id = message.conversation_id or "default"
        response = await agent_core.run(message.content, session_id=session_id)
        return {"response": response}
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
