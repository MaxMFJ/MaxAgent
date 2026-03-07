"""
Egg Builder — Duck Agent 部署包生成器

生成独立的 Egg ZIP 部署包，复制到其他电脑后解压运行即可
启动一个 Duck Agent 并自动连接回主 Agent。

Egg 包含:
- duck_client.py      精简客户端代码
- config.json         连接配置 + 模板
- start_duck.sh       macOS/Linux 启动脚本
- start_duck.bat      Windows 启动脚本
- requirements.txt    Python 依赖
"""
from __future__ import annotations

import io
import json
import logging
import secrets
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from services.duck_protocol import DuckType
from services.duck_template import DuckTemplate, get_template

logger = logging.getLogger(__name__)

# Egg 存储目录
DATA_DIR = Path(__file__).parent.parent / "data"
EGG_STORE_DIR = DATA_DIR / "duck_eggs"
EGG_REGISTRY_FILE = DATA_DIR / "duck_eggs.json"


@dataclass
class EggRecord:
    """Egg 记录（持久化到 duck_eggs.json）"""
    egg_id: str
    duck_type: str
    name: str
    token: str                      # 认证 token
    created_at: float
    downloaded: bool = False
    downloaded_at: Optional[float] = None
    connected: bool = False         # Duck 是否已连接回主 Agent

    def to_dict(self) -> dict:
        return {
            "egg_id": self.egg_id,
            "duck_type": self.duck_type,
            "name": self.name,
            "token": self.token,
            "created_at": self.created_at,
            "downloaded": self.downloaded,
            "downloaded_at": self.downloaded_at,
            "connected": self.connected,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EggRecord":
        return cls(**d)


class EggBuilder:
    """Egg 打包器（单例）"""

    _instance: Optional["EggBuilder"] = None

    def __init__(self):
        self._eggs: Dict[str, EggRecord] = {}
        self._loaded = False

    @classmethod
    def get_instance(cls) -> "EggBuilder":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ─── 持久化 ──────────────────────────────────────

    def _ensure_loaded(self):
        if self._loaded:
            return
        EGG_STORE_DIR.mkdir(parents=True, exist_ok=True)
        if EGG_REGISTRY_FILE.exists():
            try:
                raw = json.loads(EGG_REGISTRY_FILE.read_text(encoding="utf-8"))
                for item in raw:
                    rec = EggRecord.from_dict(item)
                    self._eggs[rec.egg_id] = rec
            except Exception as e:
                logger.warning(f"Failed to load egg registry: {e}")
        self._loaded = True

    def _save_registry(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = [rec.to_dict() for rec in self._eggs.values()]
        EGG_REGISTRY_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ─── 创建 Egg ────────────────────────────────────

    def create_egg(
        self,
        duck_type: DuckType,
        name: Optional[str] = None,
        main_agent_url: str = "ws://127.0.0.1:8765/duck/ws",
    ) -> EggRecord:
        """
        创建一个新的 Egg 部署包。
        返回 EggRecord 及生成的 ZIP 文件路径。
        """
        self._ensure_loaded()

        template = get_template(duck_type)
        egg_id = f"egg_{uuid.uuid4().hex[:8]}"
        token = secrets.token_urlsafe(32)
        egg_name = name or f"{template.name} ({egg_id})"

        record = EggRecord(
            egg_id=egg_id,
            duck_type=duck_type.value,
            name=egg_name,
            token=token,
            created_at=time.time(),
        )

        # 生成 ZIP
        zip_path = EGG_STORE_DIR / f"{egg_id}.zip"
        self._build_zip(zip_path, egg_id, token, template, main_agent_url)

        self._eggs[egg_id] = record
        self._save_registry()

        logger.info(f"Egg created: {egg_id} type={duck_type.value}")
        return record

    # ─── 下载 ────────────────────────────────────────

    def get_egg_path(self, egg_id: str) -> Optional[Path]:
        """获取 Egg ZIP 文件路径"""
        self._ensure_loaded()
        record = self._eggs.get(egg_id)
        if not record:
            return None
        path = EGG_STORE_DIR / f"{egg_id}.zip"
        if not path.exists():
            return None
        record.downloaded = True
        record.downloaded_at = time.time()
        self._save_registry()
        return path

    def get_egg_record(self, egg_id: str) -> Optional[EggRecord]:
        self._ensure_loaded()
        return self._eggs.get(egg_id)

    def list_eggs(self) -> List[EggRecord]:
        self._ensure_loaded()
        return sorted(self._eggs.values(), key=lambda e: e.created_at, reverse=True)

    def delete_egg(self, egg_id: str) -> bool:
        self._ensure_loaded()
        record = self._eggs.pop(egg_id, None)
        if not record:
            return False
        zip_path = EGG_STORE_DIR / f"{egg_id}.zip"
        if zip_path.exists():
            zip_path.unlink()
        self._save_registry()
        logger.info(f"Egg deleted: {egg_id}")
        return True

    def mark_connected(self, egg_id: str):
        """标记 Egg 对应的 Duck 已连接"""
        self._ensure_loaded()
        record = self._eggs.get(egg_id)
        if record:
            record.connected = True
            self._save_registry()

    # ─── ZIP 构建 ────────────────────────────────────

    def _build_zip(
        self,
        zip_path: Path,
        egg_id: str,
        token: str,
        template: DuckTemplate,
        main_agent_url: str,
    ):
        """打包 Egg ZIP 文件"""
        EGG_STORE_DIR.mkdir(parents=True, exist_ok=True)

        config = {
            "egg_id": egg_id,
            "token": token,
            "main_agent_url": main_agent_url,
            "duck_type": template.duck_type.value,
            "name": template.name,
            "skills": template.skills,
            "system_prompt": template.system_prompt,
        }

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # config.json
            zf.writestr(
                f"{egg_id}/config.json",
                json.dumps(config, ensure_ascii=False, indent=2),
            )

            # requirements.txt
            zf.writestr(
                f"{egg_id}/requirements.txt",
                _EGG_REQUIREMENTS,
            )

            # duck_client.py
            zf.writestr(
                f"{egg_id}/duck_client.py",
                _EGG_CLIENT_CODE,
            )

            # start_duck.sh (macOS/Linux)
            zf.writestr(
                f"{egg_id}/start_duck.sh",
                _EGG_START_SH,
            )

            # start_duck.bat (Windows)
            zf.writestr(
                f"{egg_id}/start_duck.bat",
                _EGG_START_BAT,
            )

            # README
            zf.writestr(
                f"{egg_id}/README.md",
                _egg_readme(template, egg_id),
            )


def get_egg_builder() -> EggBuilder:
    return EggBuilder.get_instance()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Egg 内置文件模板
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_EGG_REQUIREMENTS = """\
websockets>=12.0
pydantic>=2.0
"""

_EGG_CLIENT_CODE = '''\
#!/usr/bin/env python3
"""
Duck Agent Client — Egg 自动生成的精简客户端。
解压后运行本文件即可连接到主 Agent。
"""
import asyncio
import json
import platform
import socket
import sys
import time
from pathlib import Path

try:
    import websockets
except ImportError:
    print("ERROR: websockets not installed. Run: pip install websockets")
    sys.exit(1)


def load_config():
    cfg_path = Path(__file__).parent / "config.json"
    if not cfg_path.exists():
        print("ERROR: config.json not found")
        sys.exit(1)
    return json.loads(cfg_path.read_text(encoding="utf-8"))


async def main():
    config = load_config()
    egg_id = config["egg_id"]
    token = config["token"]
    url = config["main_agent_url"]
    duck_type = config["duck_type"]
    name = config["name"]
    skills = config["skills"]

    uri = f"{url}?token={token}&duck_id={egg_id}"

    print(f"[Duck] {name} ({duck_type}) connecting to {url}...")

    reconnect_delay = 2
    max_reconnect_delay = 60

    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"[Duck] Connected! Registering as {egg_id}...")

                # 发送 REGISTER 消息
                register_msg = {
                    "type": "register",
                    "msg_id": f"reg_{int(time.time())}",
                    "duck_id": egg_id,
                    "payload": {
                        "duck_type": duck_type,
                        "name": name,
                        "skills": skills,
                        "hostname": socket.gethostname(),
                        "platform": platform.system().lower(),
                        "token": token,
                    },
                    "timestamp": time.time(),
                }
                await ws.send(json.dumps(register_msg))

                reconnect_delay = 2  # 重置重连延迟

                # 主循环: 接收消息
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    msg_type = msg.get("type", "")

                    if msg_type == "ping":
                        # 回复心跳
                        heartbeat = {
                            "type": "heartbeat",
                            "duck_id": egg_id,
                            "payload": {},
                            "timestamp": time.time(),
                        }
                        await ws.send(json.dumps(heartbeat))

                    elif msg_type == "task":
                        payload = msg.get("payload", {})
                        task_id = payload.get("task_id", "unknown")
                        description = payload.get("description", "")
                        print(f"[Duck] Received task: {task_id} - {description}")

                        # 执行任务
                        result = await execute_task(config, payload)

                        # 返回结果
                        result_msg = {
                            "type": "result",
                            "duck_id": egg_id,
                            "payload": result,
                            "timestamp": time.time(),
                        }
                        await ws.send(json.dumps(result_msg))
                        print(f"[Duck] Task {task_id} completed")

                    elif msg_type == "cancel_task":
                        task_id = msg.get("payload", {}).get("task_id")
                        print(f"[Duck] Task cancelled: {task_id}")

                    elif msg_type == "ack":
                        print("[Duck] Registration acknowledged")

        except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            print(f"[Duck] Connection lost: {e}. Reconnecting in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)


async def execute_task(config, payload):
    """执行任务并返回结果。可扩展为调用 LLM 或其他工具。"""
    task_id = payload.get("task_id", "")
    description = payload.get("description", "")
    params = payload.get("params", {})

    start_time = time.time()

    try:
        # 基础实现: 返回确认信息
        # TODO: 接入 LLM API 实现智能任务处理
        output = {
            "message": f"Task processed by {config['name']}",
            "description": description,
            "params": params,
        }

        return {
            "task_id": task_id,
            "success": True,
            "output": output,
            "error": None,
            "duration": time.time() - start_time,
        }
    except Exception as e:
        return {
            "task_id": task_id,
            "success": False,
            "output": None,
            "error": str(e),
            "duration": time.time() - start_time,
        }


if __name__ == "__main__":
    print("=" * 50)
    print("  Chow Duck Agent Client")
    print("=" * 50)
    asyncio.run(main())
'''

_EGG_START_SH = '''\
#!/bin/bash
# Chow Duck — 启动脚本 (macOS/Linux)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================"
echo "  Chow Duck Agent — Starting..."
echo "================================================"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found. Please install Python 3.10+"
    exit 1
fi

# 创建虚拟环境（如果不存在）
if [ ! -d ".venv" ]; then
    echo "[Setup] Creating virtual environment..."
    python3 -m venv .venv
fi

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
echo "[Setup] Installing dependencies..."
pip install -q -r requirements.txt

# 启动 Duck Client
echo "[Duck] Starting client..."
python3 duck_client.py
'''

_EGG_START_BAT = '''\
@echo off
REM Chow Duck — 启动脚本 (Windows)

cd /d "%~dp0"

echo ================================================
echo   Chow Duck Agent — Starting...
echo ================================================

REM 检查 Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: python not found. Please install Python 3.10+
    exit /b 1
)

REM 创建虚拟环境（如果不存在）
if not exist ".venv" (
    echo [Setup] Creating virtual environment...
    python -m venv .venv
)

REM 激活虚拟环境
call .venv\\Scripts\\activate.bat

REM 安装依赖
echo [Setup] Installing dependencies...
pip install -q -r requirements.txt

REM 启动 Duck Client
echo [Duck] Starting client...
python duck_client.py
'''


def _egg_readme(template: DuckTemplate, egg_id: str) -> str:
    return f"""\
# {template.icon} {template.name} — Egg Deployment Package

> Egg ID: `{egg_id}`
> Type: {template.duck_type.value}

## Quick Start

### macOS / Linux
```bash
chmod +x start_duck.sh
./start_duck.sh
```

### Windows
```cmd
start_duck.bat
```

## What This Does

1. Creates a Python virtual environment
2. Installs required dependencies
3. Connects to the main Chow Duck Agent via WebSocket
4. Registers as a **{template.name}**
5. Waits for tasks from the main Agent

## Skills

{chr(10).join(f'- {s}' for s in template.skills)}

## Configuration

Edit `config.json` to change:
- `main_agent_url`: The WebSocket URL of your main Agent
- Other settings as needed

## Requirements

- Python 3.10+
- Network access to the main Agent
"""
