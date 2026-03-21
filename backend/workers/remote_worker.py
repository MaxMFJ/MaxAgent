#!/usr/bin/env python3
"""
Remote Worker — Duck Runtime v3.0 Reference Client

Usage:
  python remote_worker.py \\
    --server http://192.168.1.100:19700 \\
    --worker-id duck_remote_01 \\
    --duck-type coder \\
    --token YOUR_TOKEN

Loop:
  1. Register
  2. heartbeat()
  3. task = pull()
  4. if task: execute() → complete()
  5. else: sleep(backoff)

Backoff: 1s → 2s → 5s → max 10s
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from typing import Any, Dict, Optional

# Use httpx for async HTTP if available, fallback to aiohttp
try:
    import httpx
    _HTTP_CLIENT = "httpx"
except ImportError:
    try:
        import aiohttp
        _HTTP_CLIENT = "aiohttp"
    except ImportError:
        print("ERROR: Install httpx or aiohttp: pip install httpx")
        sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("remote_worker")

# ─── Configuration ───────────────────────────────────
BACKOFF_STEPS = [1, 2, 5, 10]  # seconds
HEARTBEAT_INTERVAL = 15  # seconds


class RemoteWorker:
    """Remote worker node that pulls tasks from the Runtime Authority"""

    def __init__(
        self,
        server_url: str,
        worker_id: str,
        duck_type: str,
        token: str = "",
    ):
        self.server_url = server_url.rstrip("/")
        self.worker_id = worker_id
        self.duck_type = duck_type
        self.token = token
        self._headers = {}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self._running = True
        self._current_task_id: Optional[str] = None
        self._backoff_idx = 0

    # ─── HTTP helpers ────────────────────────────────

    async def _post(self, path: str, data: dict) -> Optional[dict]:
        """POST JSON to server, return response dict or None"""
        url = f"{self.server_url}{path}"
        try:
            if _HTTP_CLIENT == "httpx":
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        url, json=data, headers=self._headers
                    )
                    if resp.status_code == 204:
                        return None
                    resp.raise_for_status()
                    return resp.json()
            else:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url, json=data, headers=self._headers
                    ) as resp:
                        if resp.status == 204:
                            return None
                        resp.raise_for_status()
                        return await resp.json()
        except Exception as e:
            logger.error(f"HTTP error {path}: {e}")
            return None

    # ─── Protocol Methods ────────────────────────────

    async def register(self) -> bool:
        """Register with the runtime authority"""
        result = await self._post("/workers/register", {
            "worker_id": self.worker_id,
            "duck_type": self.duck_type,
            "capabilities": [],
            "version": "3.0",
        })
        if result:
            logger.info(f"Registered: lease={result.get('lease_seconds')}s")
            return True
        return False

    async def heartbeat(self) -> bool:
        """Send heartbeat, optionally extend task lease"""
        result = await self._post("/workers/heartbeat", {
            "worker_id": self.worker_id,
            "running_task_id": self._current_task_id,
        })
        return result is not None

    async def pull(self) -> Optional[dict]:
        """Pull a task from the ready queue"""
        result = await self._post("/workers/pull", {
            "worker_id": self.worker_id,
            "duck_type": self.duck_type,
        })
        return result

    async def complete(self, task_id: str, result: Any, status: str = "completed"):
        """Report task completion"""
        await self._post("/workers/complete", {
            "worker_id": self.worker_id,
            "task_id": task_id,
            "result": result,
            "status": status,
        })

    # ─── Task Execution ─────────────────────────────

    async def execute_task(self, task: dict) -> tuple:
        """
        Execute a task. Override this in subclasses for real work.
        Returns (result, status).
        """
        payload = task.get("payload", {})
        description = payload.get("description", "")
        task_type = payload.get("task_type", "general")
        params = payload.get("params", {})

        logger.info(f"Executing: {description[:80]}...")

        # Placeholder: simulate work
        await asyncio.sleep(2)

        return {"output": f"Completed by {self.worker_id}"}, "completed"

    # ─── Main Loop ───────────────────────────────────

    async def run(self):
        """Main worker loop"""
        # Register
        for attempt in range(3):
            if await self.register():
                break
            logger.warning(f"Registration failed, retrying ({attempt + 1}/3)...")
            await asyncio.sleep(2)
        else:
            logger.error("Failed to register after 3 attempts")
            return

        # Heartbeat background task
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        try:
            while self._running:
                # Pull task
                task = await self.pull()

                if task is None:
                    # No tasks, backoff
                    delay = BACKOFF_STEPS[min(self._backoff_idx, len(BACKOFF_STEPS) - 1)]
                    self._backoff_idx = min(self._backoff_idx + 1, len(BACKOFF_STEPS) - 1)
                    await asyncio.sleep(delay)
                    continue

                # Reset backoff on successful pull
                self._backoff_idx = 0
                task_id = task["task_id"]
                self._current_task_id = task_id

                logger.info(
                    f"Pulled task: {task_id} "
                    f"(dag={task.get('dag_id', 'N/A')}, node={task.get('node_id', 'N/A')})"
                )

                # Execute
                try:
                    result, status = await self.execute_task(task)
                except Exception as e:
                    logger.error(f"Task execution failed: {e}")
                    result, status = str(e), "failed"

                # Complete
                await self.complete(task_id, result, status)
                self._current_task_id = None
                logger.info(f"Task {task_id} completed: {status}")

        except asyncio.CancelledError:
            pass
        finally:
            heartbeat_task.cancel()
            self._running = False

    async def _heartbeat_loop(self):
        """Background heartbeat"""
        while self._running:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await self.heartbeat()
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")

    def stop(self):
        """Stop the worker"""
        self._running = False


# ─── CLI ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Duck Remote Worker v3.0")
    parser.add_argument("--server", required=True, help="Runtime server URL")
    parser.add_argument("--worker-id", default=f"rw_{uuid.uuid4().hex[:6]}")
    parser.add_argument("--duck-type", default="general")
    parser.add_argument("--token", default=os.environ.get("DUCK_WORKER_TOKEN", ""))
    args = parser.parse_args()

    worker = RemoteWorker(
        server_url=args.server,
        worker_id=args.worker_id,
        duck_type=args.duck_type,
        token=args.token,
    )

    logger.info(
        f"Starting remote worker: id={args.worker_id} type={args.duck_type} "
        f"server={args.server}"
    )

    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
        worker.stop()


if __name__ == "__main__":
    main()
