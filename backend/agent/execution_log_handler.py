"""
Execution Log Handler - 工具执行期间将 Python 日志转发到 WebSocket
用于客户端实时展示工具日志
"""
import logging
from typing import Optional


class QueueLogHandler(logging.Handler):
    """将日志记录放入 queue（支持 queue.Queue 或 asyncio.Queue），供流式读取"""

    def __init__(self, queue, logger_names: Optional[list] = None):
        super().__init__()
        self._queue = queue
        self._logger_names = logger_names  # None = 接受所有，或 ["tools"]

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self._logger_names and record.name != "root":
                if not any(record.name == n or record.name.startswith(n + ".") for n in self._logger_names):
                    return
            msg = self.format(record)
            try:
                self._queue.put_nowait({
                    "level": record.levelname.lower(),
                    "message": msg,
                    "logger": record.name,
                })
            except Exception:
                pass
        except Exception:
            self.handleError(record)
