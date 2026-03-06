"""
MCP (Model Context Protocol) Client — v3.4
Connects to external MCP servers and exposes their tools to the MacAgent tool space.

Supports two transport modes:
  stdio  — Launch a subprocess and communicate via stdin/stdout JSON-RPC
  http   — HTTP/SSE transport (server-sent events for streaming, POST for calls)

Usage:
    manager = get_mcp_manager()
    await manager.add_server("filesystem", transport="stdio",
                              command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
    tools = await manager.list_tools()        # [{name, description, inputSchema}, ...]
    result = await manager.call_tool("filesystem", "readFile", {"path": "/tmp/hello.txt"})
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class MCPServerConfig:
    name: str                              # Unique server identifier
    transport: str                         # "stdio" | "http"
    # stdio
    command: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    # http
    url: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    # connection meta
    timeout: float = 30.0
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "env": self.env,
            "url": self.url,
            "headers": self.headers,
            "timeout": self.timeout,
            "enabled": self.enabled,
        }


@dataclass
class MCPToolEntry:
    server_name: str
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.server_name}/{self.name}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "server": self.server_name,
            "name": self.name,
            "full_name": self.full_name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------

def _make_request(method: str, params: Any = None, req_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id or str(uuid.uuid4()),
        "method": method,
        **({"params": params} if params is not None else {}),
    }


def _check_error(resp: Dict[str, Any]) -> None:
    if "error" in resp:
        err = resp["error"]
        raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message')}")


# ---------------------------------------------------------------------------
# Transport implementations
# ---------------------------------------------------------------------------

class _StdioTransport:
    """Communicate with a MCP server process via stdin/stdout (newline-delimited JSON)."""

    def __init__(self, config: MCPServerConfig):
        self._config = config
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        import os as _os
        import shutil as _shutil
        env = {**_os.environ, **self._config.env}
        # 确保 PATH 包含 Homebrew keg-only Node.js（macOS 上 App 启动时 PATH 有限）
        _extra_dirs = []
        import glob as _glob
        for pattern in ("/opt/homebrew/opt/node@*/bin", "/usr/local/opt/node@*/bin",
                        "/opt/homebrew/bin", "/usr/local/bin"):
            _extra_dirs.extend(_glob.glob(pattern))
        if _extra_dirs:
            existing = env.get("PATH", "")
            for d in _extra_dirs:
                if d not in existing:
                    existing = d + ":" + existing
            env["PATH"] = existing
        # 尝试解析 command[0] 的绝对路径
        cmd = list(self._config.command)
        if cmd and not _os.path.isabs(cmd[0]):
            resolved = _shutil.which(cmd[0], path=env.get("PATH"))
            if resolved:
                cmd[0] = resolved
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._reader_task = asyncio.create_task(self._read_loop(), name=f"mcp-{self._config.name}-reader")
        logger.info("MCP stdio server started: %s (pid=%s)", self._config.name, self._proc.pid)

    async def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        try:
            async for line in self._proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg_id = str(msg.get("id", ""))
                if msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        fut.set_result(msg)
        except Exception as e:
            logger.warning("MCP stdio reader error (%s): %s", self._config.name, e)

    async def call(self, method: str, params: Any = None) -> Dict[str, Any]:
        req = _make_request(method, params)
        req_id = req["id"]
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        assert self._proc and self._proc.stdin
        line = json.dumps(req) + "\n"
        try:
            self._proc.stdin.write(line.encode())
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError):
            self._pending.pop(req_id, None)
            # 进程已退出，读取 stderr 获取错误原因
            stderr_text = await self._read_stderr()
            raise RuntimeError(f"MCP 进程已退出: {stderr_text}" if stderr_text else "MCP 进程意外退出")
        try:
            return await asyncio.wait_for(fut, timeout=self._config.timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            stderr_text = await self._read_stderr()
            raise RuntimeError(f"MCP 响应超时 ({self._config.timeout}s): {stderr_text}" if stderr_text
                               else f"MCP 响应超时 ({self._config.timeout}s)")
        finally:
            self._pending.pop(req_id, None)

    async def _read_stderr(self) -> str:
        """尝试读取子进程 stderr 的内容用于错误诊断。"""
        if not self._proc or not self._proc.stderr:
            return ""
        try:
            data = await asyncio.wait_for(self._proc.stderr.read(4096), timeout=2)
            return data.decode(errors="replace").strip()[-500:]  # 最多 500 字符
        except Exception:
            return ""

    async def stop(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self._proc:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except Exception:
                pass


class _HttpTransport:
    """Communicate with a MCP server via HTTP POST (simple request/response mode)."""

    def __init__(self, config: MCPServerConfig):
        self._config = config
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._config.url.rstrip("/"),
            headers=self._config.headers,
            timeout=self._config.timeout,
        )
        logger.info("MCP HTTP server configured: %s → %s", self._config.name, self._config.url)

    async def call(self, method: str, params: Any = None) -> Dict[str, Any]:
        assert self._client
        req = _make_request(method, params)
        resp = await self._client.post("/", json=req)
        resp.raise_for_status()
        return resp.json()

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()


# ---------------------------------------------------------------------------
# MCP Connection (wraps transport + caches tool list)
# ---------------------------------------------------------------------------

class MCPConnection:
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._transport: Optional[_StdioTransport | _HttpTransport] = None
        self._tools: List[MCPToolEntry] = []
        self._connected = False

    async def connect(self) -> None:
        if self.config.transport == "stdio":
            self._transport = _StdioTransport(self.config)
        elif self.config.transport == "http":
            self._transport = _HttpTransport(self.config)
        else:
            raise ValueError(f"Unknown MCP transport: {self.config.transport}")
        await self._transport.start()
        # Initialize handshake
        init_resp = await self._transport.call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "MacAgent", "version": "3.4"},
        })
        _check_error(init_resp)
        # Notify initialized
        try:
            await self._transport.call("notifications/initialized")
        except Exception:
            pass
        self._connected = True
        await self._refresh_tools()
        logger.info("MCP connected: %s (%d tools)", self.config.name, len(self._tools))

    async def _refresh_tools(self) -> None:
        resp = await self._transport.call("tools/list")
        _check_error(resp)
        raw_tools = resp.get("result", {}).get("tools", [])
        self._tools = [
            MCPToolEntry(
                server_name=self.config.name,
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in raw_tools
        ]

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        resp = await self._transport.call("tools/call", {"name": tool_name, "arguments": arguments})
        _check_error(resp)
        return resp.get("result", {})

    async def disconnect(self) -> None:
        if self._transport:
            await self._transport.stop()
        self._connected = False

    @property
    def tools(self) -> List[MCPToolEntry]:
        return self._tools

    @property
    def connected(self) -> bool:
        return self._connected


# ---------------------------------------------------------------------------
# Manager (singleton)
# ---------------------------------------------------------------------------

class MCPManager:
    """Manages multiple MCP server connections."""

    def __init__(self):
        self._connections: Dict[str, MCPConnection] = {}
        self._lock = asyncio.Lock()
        self._config_path: Optional[str] = None

    def set_config_path(self, path: str) -> None:
        self._config_path = path

    async def add_server(self, config: MCPServerConfig) -> MCPConnection:
        """Add and immediately connect to an MCP server."""
        async with self._lock:
            if config.name in self._connections:
                old = self._connections[config.name]
                await old.disconnect()
            conn = MCPConnection(config)
            try:
                await conn.connect()
            except Exception as e:
                logger.error("Failed to connect MCP server '%s': %s", config.name, e)
                raise
            self._connections[config.name] = conn
            await self._save_config()
            return conn

    async def remove_server(self, name: str) -> None:
        async with self._lock:
            conn = self._connections.pop(name, None)
            if conn:
                await conn.disconnect()
            await self._save_config()

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Return all tools from all connected servers."""
        result = []
        for conn in self._connections.values():
            if conn.connected:
                result.extend(t.to_dict() for t in conn.tools)
        return result

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        conn = self._connections.get(server_name)
        if not conn or not conn.connected:
            raise RuntimeError(f"MCP server '{server_name}' not connected")
        return await conn.call_tool(tool_name, arguments)

    def server_status(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": name,
                "connected": conn.connected,
                "transport": conn.config.transport,
                "tool_count": len(conn.tools),
            }
            for name, conn in self._connections.items()
        ]

    async def shutdown(self) -> None:
        for conn in self._connections.values():
            try:
                await conn.disconnect()
            except Exception:
                pass
        self._connections.clear()

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------

    async def _save_config(self) -> None:
        if not self._config_path:
            return
        import os, aiofiles  # type: ignore  noqa
        try:
            data = [conn.config.to_dict() for conn in self._connections.values()]
            async with aiofiles.open(self._config_path, "w") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("Failed to save MCP config: %s", e)

    async def load_config(self, path: str) -> None:
        """Load and connect servers from a stored JSON config."""
        import os
        self._config_path = path
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for raw in data:
                if not raw.get("enabled", True):
                    continue
                cfg = MCPServerConfig(**{k: raw[k] for k in raw if k in MCPServerConfig.__dataclass_fields__})
                try:
                    await self.add_server(cfg)
                except Exception as e:
                    logger.warning("Auto-connect MCP server '%s' failed: %s", cfg.name, e)
        except Exception as e:
            logger.warning("Failed to load MCP config from %s: %s", path, e)


_mcp_manager: Optional[MCPManager] = None


def get_mcp_manager() -> MCPManager:
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
    return _mcp_manager
