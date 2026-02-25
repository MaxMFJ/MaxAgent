"""日志 + 系统消息路由"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from agent.system_message_service import get_system_message_service

router = APIRouter()

# 日志缓冲区（全局共享）
log_buffer: list = []
_max_log_entries = 200


class LogCapture(logging.Handler):
    """Capture logs to buffer for API access"""
    def emit(self, record):
        from datetime import datetime
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": record.levelname,
            "message": self.format(record),
        }
        log_buffer.append(log_entry)
        if len(log_buffer) > _max_log_entries:
            log_buffer.pop(0)


def setup_log_capture():
    """在 main.py 启动时调用，安装日志捕获 handler"""
    handler = LogCapture()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(name)s - %(message)s"))
    logging.getLogger().addHandler(handler)


@router.get("/logs")
async def get_logs(limit: int = 100, since_index: int = 0):
    logs = log_buffer[since_index:since_index + limit]
    return {
        "logs": logs,
        "total": len(log_buffer),
        "next_index": since_index + len(logs),
    }


@router.delete("/logs")
async def clear_logs():
    log_buffer.clear()
    return {"status": "cleared"}


# ============== System Messages ==============

@router.get("/system-messages")
async def get_system_messages(limit: int = 50, category: Optional[str] = None):
    svc = get_system_message_service()
    return {
        "messages": svc.get_all(limit=limit, category=category),
        "unread_count": svc.get_unread_count(),
    }


@router.post("/system-messages/{message_id}/read")
async def mark_system_message_read(message_id: str):
    svc = get_system_message_service()
    ok = svc.mark_read(message_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "ok", "unread_count": svc.get_unread_count()}


@router.post("/system-messages/read-all")
async def mark_all_system_messages_read():
    svc = get_system_message_service()
    count = svc.mark_all_read()
    return {"status": "ok", "marked": count, "unread_count": 0}


@router.delete("/system-messages")
async def clear_system_messages():
    svc = get_system_message_service()
    count = svc.clear()
    return {"status": "cleared", "removed": count}
