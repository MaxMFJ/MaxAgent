"""
ipc_client.py
Python 客户端 — 通过 TCP (端口 8767) 调用 Swift IPCService

协议: 4 字节大端长度头 + 4 字节 CRC32 校验 + JSON payload
支持: ACTION, BATCH, QUERY, SUBSCRIBE, HEARTBEAT

替代 accessibility_bridge_client.py，延迟更低，功能更全：
- 批量动作执行 (BATCH)
- 事件订阅 (SUBSCRIBE) — 免轮询
- 世界状态查询 (QUERY) — 带版本控制和增量 diff
- CRC32 完整性校验 + 自动重试
"""

import asyncio
import binascii
import json
import logging
import os
import struct
import tempfile
import uuid
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

IPC_HOST = "127.0.0.1"


def _read_ipc_port() -> int:
    """从共享配置文件读取 IPC 端口，回退到默认值"""
    config_path = os.path.join(tempfile.gettempdir(), "macagent_ports.json")
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
            return int(cfg.get("ipc_port", 8767))
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return 8767


IPC_PORT = _read_ipc_port()
CONNECT_TIMEOUT = 3.0
REQUEST_TIMEOUT = 10.0
AUTH_TOKEN_PATH = os.path.join(tempfile.gettempdir(), "macagent_ipc_token")
MAX_RETRY_ON_CRC_ERROR = 3


class IPCClient:
    """Swift IPC 连接客户端（TCP + 长度前缀 JSON）

    支持 dry_run 模式（不实际执行，返回模拟结果）和自动重连。
    """

    def __init__(self, dry_run: bool = False, client_id: Optional[str] = None):
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()
        self._event_callbacks: List[Callable[[dict], None]] = []
        self._event_task: Optional[asyncio.Task] = None
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribed: bool = False
        self._last_state_version: int = 0
        self._dry_run: bool = dry_run
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = 5
        self._reconnect_delay: float = 1.0  # 秒，指数退避
        self._auth_token: Optional[str] = None
        self._client_id: str = client_id or str(uuid.uuid4())

    def _read_auth_token(self) -> Optional[str]:
        """从本地文件读取认证令牌"""
        try:
            with open(AUTH_TOKEN_PATH, "r") as f:
                return f.read().strip()
        except (FileNotFoundError, PermissionError):
            logger.debug("[IPC] Auth token file not found: %s", AUTH_TOKEN_PATH)
            return None

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    @dry_run.setter
    def dry_run(self, value: bool):
        self._dry_run = value

    # ── 连接管理 ──

    async def connect(self) -> bool:
        """建立 TCP 连接"""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(IPC_HOST, IPC_PORT),
                timeout=CONNECT_TIMEOUT,
            )
            self._reconnect_attempts = 0
            # 每次连接时刷新 token
            self._auth_token = self._read_auth_token()
            logger.info("[IPC] Connected to %s:%s", IPC_HOST, IPC_PORT)
            return True
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError) as e:
            logger.debug("[IPC] Connection failed: %s", e)
            self._reader = self._writer = None
            return False

    async def disconnect(self):
        """关闭连接"""
        if self._event_task:
            self._event_task.cancel()
            self._event_task = None
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

    @property
    def is_connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def _ensure_connected(self) -> bool:
        """确保连接可用，断线时自动重连（指数退避）"""
        if self.is_connected:
            return True
        # 自动重连
        while self._reconnect_attempts < self._max_reconnect_attempts:
            delay = self._reconnect_delay * (2 ** self._reconnect_attempts)
            if self._reconnect_attempts > 0:
                logger.info("[IPC] Reconnecting in %.1fs (attempt %d/%d)",
                            delay, self._reconnect_attempts + 1, self._max_reconnect_attempts)
                await asyncio.sleep(delay)
            self._reconnect_attempts += 1
            if await self.connect():
                return True
        logger.warning("[IPC] Max reconnect attempts reached (%d)", self._max_reconnect_attempts)
        return False

    # ── 底层协议（含 CRC32 校验）──

    @staticmethod
    def _crc32(data: bytes) -> int:
        """计算 CRC32 校验值"""
        return binascii.crc32(data) & 0xFFFFFFFF

    async def _send_raw(self, data: bytes):
        """发送: 4 字节大端长度 + 4 字节 CRC32 + payload"""
        length = struct.pack(">I", len(data))
        checksum = struct.pack(">I", self._crc32(data))
        self._writer.write(length + checksum + data)
        await self._writer.drain()

    async def _recv_raw(self) -> Optional[bytes]:
        """接收: 4 字节大端长度 + 4 字节 CRC32 + payload"""
        try:
            header = await asyncio.wait_for(
                self._reader.readexactly(8), timeout=REQUEST_TIMEOUT
            )
            length = struct.unpack(">I", header[:4])[0]
            expected_crc = struct.unpack(">I", header[4:8])[0]
            if length > 10_000_000:
                logger.error("[IPC] Message too large: %d bytes", length)
                return None
            payload = await asyncio.wait_for(
                self._reader.readexactly(length), timeout=REQUEST_TIMEOUT
            )
            # CRC32 校验
            if expected_crc != 0:
                actual_crc = self._crc32(payload)
                if actual_crc != expected_crc:
                    logger.warning("[IPC] CRC32 mismatch: expected %08x, got %08x", expected_crc, actual_crc)
                    return None  # 触发重试
            return payload
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError) as e:
            logger.warning("[IPC] Recv error: %s", e)
            await self.disconnect()
            return None

    async def _recv_response_raw(self) -> Optional[bytes]:
        """接收响应数据，自动跳过并分发穿插的 EVENT 推送"""
        for _ in range(20):  # 最多跳过 20 个穿插事件
            raw = await self._recv_raw()
            if raw is None:
                return None
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return raw
            if msg.get("type") == "EVENT":
                # 穿插的事件推送 — 分发到队列并继续读取
                for cb in self._event_callbacks:
                    try:
                        cb(msg)
                    except Exception:
                        pass
                continue
            return raw
        return None

    async def _request(self, msg: dict, _retry_count: int = 0) -> Optional[dict]:
        """发送请求并等待响应，CRC32 校验失败自动重试"""
        async with self._lock:
            if not await self._ensure_connected():
                return None
            try:
                if self._auth_token and "token" not in msg:
                    msg["token"] = self._auth_token
                if "clientId" not in msg:
                    msg["clientId"] = self._client_id
                data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
                await self._send_raw(data)
                resp_data = await self._recv_response_raw()
                if resp_data is None:
                    need_retry = _retry_count < MAX_RETRY_ON_CRC_ERROR
                    if need_retry:
                        logger.info("[IPC] Retrying request (attempt %d/%d)", _retry_count + 1, MAX_RETRY_ON_CRC_ERROR)
                    else:
                        return None
                else:
                    resp = json.loads(resp_data)
                    if resp.get("type") == "NACK" and "CRC32" in (resp.get("error") or ""):
                        need_retry = _retry_count < MAX_RETRY_ON_CRC_ERROR
                        if need_retry:
                            logger.info("[IPC] Server CRC error, retrying (attempt %d/%d)", _retry_count + 1, MAX_RETRY_ON_CRC_ERROR)
                        else:
                            return resp
                    else:
                        if "stateVersion" in resp:
                            self._last_state_version = resp["stateVersion"]
                        return resp
            except Exception as e:
                logger.warning("[IPC] Request error: %s", e)
                await self.disconnect()
                return None
        # 在锁外重试（避免死锁）
        return await self._request(msg, _retry_count=_retry_count + 1)

    # ── 公共 API ──

    async def is_available(self) -> bool:
        """检查 IPC 服务是否可用"""
        resp = await self._request({
            "id": str(uuid.uuid4()),
            "type": "HEARTBEAT",
        })
        return resp is not None and resp.get("success", False)

    async def heartbeat(self) -> Optional[dict]:
        """心跳检测"""
        return await self._request({
            "id": str(uuid.uuid4()),
            "type": "HEARTBEAT",
        })

    # ── 单个动作 ──

    async def execute_action(
        self,
        action_type: str,
        parameters: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Optional[dict]:
        """执行单个 GUI 动作（dry_run 模式下返回模拟结果）"""
        if self._dry_run:
            return self._make_dry_run_result(action_type, parameters)
        action = {
            "actionId": str(uuid.uuid4()),
            "actionType": action_type,
            "parameters": parameters,
        }
        if timeout is not None:
            action["timeout"] = timeout

        resp = await self._request({
            "id": str(uuid.uuid4()),
            "type": "ACTION",
            "action": action,
        })
        if resp and resp.get("actionResult"):
            return resp["actionResult"]
        return resp

    # ── 批量动作 ──

    async def execute_batch(
        self,
        actions: List[Dict[str, Any]],
        atomic: bool = True,
        error_strategy: Optional[str] = None,
    ) -> Optional[dict]:
        """执行批量 GUI 动作（事务性）

        actions: [{"actionType": "focus_app", "parameters": {"app_name": "Safari"}}, ...]
        atomic: 如果为 True，任何一步失败则停止
        error_strategy: "stop_on_error" | "continue_on_error" | "rollback"
        """
        if self._dry_run:
            return {
                "batchId": str(uuid.uuid4()),
                "success": True,
                "results": [self._make_dry_run_result(a["actionType"], a.get("parameters", {})) for a in actions],
                "finalStateVersion": self._last_state_version,
                "durationMs": 0.0,
                "dry_run": True,
            }
        batch_actions = []
        for a in actions:
            batch_actions.append({
                "actionId": str(uuid.uuid4()),
                "actionType": a["actionType"],
                "parameters": a.get("parameters", {}),
                "timeout": a.get("timeout"),
            })

        batch_payload: Dict[str, Any] = {
                "batchId": str(uuid.uuid4()),
                "atomic": atomic,
                "actions": batch_actions,
            }
        if error_strategy:
            batch_payload["errorStrategy"] = error_strategy

        resp = await self._request({
            "id": str(uuid.uuid4()),
            "type": "BATCH",
            "batch": batch_payload,
        })
        if resp and resp.get("batchResult"):
            return resp["batchResult"]
        return resp

    # ── 查询 ──

    async def query_state(self, since_version: Optional[int] = None) -> Optional[dict]:
        """查询 GUI 世界状态（支持增量 diff）"""
        payload: Dict[str, Any] = {"query": "state"}
        if since_version is not None:
            payload["since_version"] = since_version
        elif self._last_state_version > 0:
            payload["since_version"] = self._last_state_version

        resp = await self._request({
            "id": str(uuid.uuid4()),
            "type": "QUERY",
            "payload": payload,
        })
        if resp and resp.get("payload"):
            return resp["payload"]
        return resp

    async def query_apps(self) -> Optional[List[dict]]:
        """列出所有运行中的应用"""
        resp = await self._request({
            "id": str(uuid.uuid4()),
            "type": "QUERY",
            "payload": {"query": "apps"},
        })
        if resp and resp.get("payload"):
            return resp["payload"].get("apps", [])
        return None

    async def query_windows(self, app_name: str) -> Optional[List[dict]]:
        """获取应用的窗口列表"""
        resp = await self._request({
            "id": str(uuid.uuid4()),
            "type": "QUERY",
            "payload": {"query": "windows", "app_name": app_name},
        })
        if resp and resp.get("payload"):
            return resp["payload"].get("windows", [])
        return None

    async def query_elements(
        self, app_name: str, max_depth: int = 5
    ) -> Optional[dict]:
        """获取应用 UI 元素"""
        resp = await self._request({
            "id": str(uuid.uuid4()),
            "type": "QUERY",
            "payload": {"query": "elements", "app_name": app_name, "max_depth": max_depth},
        })
        if resp and resp.get("payload"):
            return resp["payload"]
        return None

    async def query_focused(self) -> Optional[dict]:
        """获取当前聚焦元素"""
        resp = await self._request({
            "id": str(uuid.uuid4()),
            "type": "QUERY",
            "payload": {"query": "focused"},
        })
        if resp and resp.get("payload"):
            return resp["payload"]
        return None

    # ── 事件订阅 ──

    async def subscribe(
        self,
        event_types: Optional[List[str]] = None,
        callback: Optional[Callable[[dict], None]] = None,
    ) -> bool:
        """订阅 GUI 事件（免轮询）

        event_types: 事件类型列表。["*"] 订阅全部。
            可选: AXFocusedUIElementChanged, AXWindowCreated, AXWindowMoved, etc.
        callback: 事件回调函数
        """
        if callback:
            self._event_callbacks.append(callback)

        resp = await self._request({
            "id": str(uuid.uuid4()),
            "type": "SUBSCRIBE",
            "payload": {"events": event_types or ["*"]},
        })
        return resp is not None and resp.get("success", False)

    async def unsubscribe(self) -> bool:
        """取消事件订阅"""
        resp = await self._request({
            "id": str(uuid.uuid4()),
            "type": "UNSUBSCRIBE",
        })
        self._event_callbacks.clear()
        self._event_queue = asyncio.Queue()
        return resp is not None and resp.get("success", False)

    async def ensure_subscribed(self) -> bool:
        """确保已订阅 AX 事件（幂等调用）"""
        if self._subscribed:
            return True
        success = await self.subscribe(
            event_types=["*"],
            callback=self._on_ax_event,
        )
        if success:
            self._subscribed = True
            await asyncio.sleep(0.05)  # 50ms 等待 Swift 完成订阅处理
        return success

    def _on_ax_event(self, event: dict):
        """AX 事件回调 — 放入队列供 wait_for_ax_event 消费"""
        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # 队列满时丢弃最旧事件

    def _event_matches(self, msg: dict, event_types: Optional[List[str]], app_name: Optional[str]) -> bool:
        """检查事件是否匹配过滤条件"""
        evt_type = msg.get("eventType", "")
        evt_app = msg.get("payload", {}).get("app_name", "")
        if event_types and evt_type not in event_types:
            return False
        if app_name and app_name.lower() not in evt_app.lower():
            return False
        return True

    async def wait_for_ax_event(
        self,
        event_types: Optional[List[str]] = None,
        app_name: Optional[str] = None,
        timeout_ms: int = 500,
    ) -> Optional[dict]:
        """等待匹配的 AX 事件，超时返回 None

        从 TCP 连接直接读取 Swift 推送的 EVENT 消息。
        event_types: 期望的事件类型列表，如 ["AXFocusedUIElementChanged", "AXValueChanged"]
        app_name: 过滤应用名
        timeout_ms: 超时毫秒数，默认 500ms
        """
        await self.ensure_subscribed()
        import time
        deadline = time.monotonic() + timeout_ms / 1000.0

        # 先检查队列中已有的事件
        while not self._event_queue.empty():
            try:
                event = self._event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if self._event_matches(event, event_types, app_name):
                return event

        # 从 TCP 连接直接读取事件（此时不应有其他并发读取）
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            async with self._lock:
                if not self._reader:
                    return None
                try:
                    header = await asyncio.wait_for(
                        self._reader.readexactly(8), timeout=remaining,
                    )
                    length = struct.unpack(">I", header[:4])[0]
                    expected_crc = struct.unpack(">I", header[4:8])[0]
                    if length > 10_000_000:
                        return None
                    payload_data = await asyncio.wait_for(
                        self._reader.readexactly(length), timeout=remaining,
                    )
                    if expected_crc != 0:
                        actual_crc = self._crc32(payload_data)
                        if actual_crc != expected_crc:
                            continue
                    msg = json.loads(payload_data)
                except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError):
                    return None
                except json.JSONDecodeError:
                    continue

            if msg.get("type") == "EVENT":
                if self._event_matches(msg, event_types, app_name):
                    return msg
                # 不匹配的事件放入队列
                try:
                    self._event_queue.put_nowait(msg)
                except asyncio.QueueFull:
                    pass
            # 非 EVENT 消息（理论上不应出现）跳过

    # ── dry-run 辅助 ──

    def _make_dry_run_result(self, action_type: str, parameters: Dict[str, Any]) -> dict:
        """生成模拟动作结果（不实际执行）"""
        return {
            "actionId": str(uuid.uuid4()),
            "success": True,
            "error": None,
            "data": {"dry_run": True, "action_type": action_type, "parameters": parameters},
            "stateVersion": self._last_state_version,
        }

    # ── 便捷方法 (替代旧 bridge_client) ──

    async def focus_app(self, app_name: str) -> bool:
        result = await self.execute_action("focus_app", {"app_name": app_name})
        return result is not None and result.get("success", False)

    async def click_element(self, app_name: str, role: str = None, title: str = None) -> bool:
        params: Dict[str, Any] = {"app_name": app_name}
        if role:
            params["role"] = role
        if title:
            params["title"] = title
        result = await self.execute_action("click_element", params)
        return result is not None and result.get("success", False)

    async def click_position(self, x: float, y: float) -> bool:
        result = await self.execute_action("click_position", {"x": x, "y": y})
        return result is not None and result.get("success", False)

    async def set_value(self, app_name: str, value: str, role: str = None, title: str = None) -> bool:
        params: Dict[str, Any] = {"app_name": app_name, "value": value}
        if role:
            params["role"] = role
        if title:
            params["title"] = title
        result = await self.execute_action("set_value", params)
        return result is not None and result.get("success", False)

    async def type_text(self, text: str) -> bool:
        result = await self.execute_action("key_press", {"text": text})
        return result is not None and result.get("success", False)

    async def find_elements(
        self, app_name: str, role: str = None, title: str = None, max_count: int = 50
    ) -> Optional[List[dict]]:
        params: Dict[str, Any] = {"app_name": app_name, "max_count": max_count}
        if role:
            params["role"] = role
        if title:
            params["title"] = title
        result = await self.execute_action("find_element", params)
        if result and result.get("data"):
            return result["data"].get("elements", [])
        return None

    # ── GUI Intent Layer（高级动作抽象） ──

    async def submit_form(
        self,
        app_name: str,
        fields: Dict[str, str],
        submit_button_title: str = "Submit",
    ) -> dict:
        """填写表单并提交

        fields: {"字段role或title": "值", ...}
        submit_button_title: 提交按钮的标题
        """
        actions = []
        for field_key, value in fields.items():
            actions.append({
                "actionType": "set_value",
                "parameters": {"app_name": app_name, "title": field_key, "value": value},
            })
        actions.append({
            "actionType": "click_element",
            "parameters": {"app_name": app_name, "role": "AXButton", "title": submit_button_title},
        })
        result = await self.execute_batch(actions, atomic=True, error_strategy="rollback")
        return result or {"success": False, "error": "batch failed"}

    async def approve_dialog(
        self,
        app_name: str,
        button_title: str = "OK",
    ) -> bool:
        """确认对话框（点击 OK/确定 按钮）"""
        return await self.click_element(app_name, role="AXButton", title=button_title)

    async def select_menu_item(
        self,
        app_name: str,
        menu_path: List[str],
    ) -> bool:
        """选择菜单项

        menu_path: ["File", "Save As..."] — 按层级顺序
        """
        actions = []
        for item in menu_path:
            actions.append({
                "actionType": "click_element",
                "parameters": {"app_name": app_name, "role": "AXMenuItem", "title": item},
            })
        result = await self.execute_batch(actions, atomic=False, error_strategy="stop_on_error")
        return result is not None and result.get("success", False)

    async def fill_and_tab(
        self,
        app_name: str,
        values: List[str],
    ) -> bool:
        """依次填入值并按 Tab 切到下一字段"""
        actions = []
        for value in values:
            actions.append({
                "actionType": "key_press",
                "parameters": {"text": value},
            })
            actions.append({
                "actionType": "key_press",
                "parameters": {"text": "\t"},
            })
        result = await self.execute_batch(actions, atomic=False)
        return result is not None and result.get("success", False)

    # ── 多 Agent 协作 API ──

    async def register_agent(self, label: Optional[str] = None) -> Optional[dict]:
        """注册当前客户端为 Agent（建议在连接后立即调用）"""
        payload: Dict[str, Any] = {"query": "register_agent"}
        if label:
            payload["label"] = label
        return await self._request({
            "id": str(uuid.uuid4()),
            "type": "QUERY",
            "clientId": self._client_id,
            "payload": payload,
        })

    async def list_agents(self) -> Optional[List[dict]]:
        """列出所有已连接的 Agent"""
        resp = await self._request({
            "id": str(uuid.uuid4()),
            "type": "QUERY",
            "payload": {"query": "agents"},
        })
        if resp and resp.get("payload"):
            return resp["payload"].get("agents", [])
        return None

    async def claim_app(self, app_name: str) -> bool:
        """声明正在操作某应用（防止其他 Agent 冲突操作）"""
        resp = await self._request({
            "id": str(uuid.uuid4()),
            "type": "QUERY",
            "clientId": self._client_id,
            "payload": {"query": "claim_app", "app_name": app_name},
        })
        return resp is not None and resp.get("success", False)

    async def release_app(self, app_name: str) -> bool:
        """释放应用操作锁"""
        resp = await self._request({
            "id": str(uuid.uuid4()),
            "type": "QUERY",
            "clientId": self._client_id,
            "payload": {"query": "release_app", "app_name": app_name},
        })
        return resp is not None and resp.get("success", False)

    # ── Vision Fallback API ──

    async def find_text_on_screen(self, text: str, app_name: str = None) -> list:
        """通过 Vision OCR 在屏幕上搜索文字，返回匹配列表"""
        payload = {"query": "find_text", "text": text}
        if app_name:
            payload["app_name"] = app_name
        resp = await self._request({
            "id": str(uuid.uuid4()),
            "type": "QUERY",
            "payload": payload,
        })
        if resp and resp.get("success"):
            return resp.get("payload", {}).get("matches", [])
        return []

    async def click_text(self, text: str, app_name: str = None) -> dict:
        """先用 Vision OCR 找到文字位置，再点击。Vision 失败时尝试 PaddleOCR。"""
        matches = await self.find_text_on_screen(text, app_name)
        if not matches:
            # PaddleOCR 视觉回退
            try:
                from runtime.paddle_ocr import find_text_coords, is_available
                if is_available():
                    # 截图再 OCR
                    import time
                    screenshot_path = f"/tmp/ipc_click_text_{int(time.time())}.png"
                    screenshot_resp = await self.execute_action(
                        action_type="get_state", params={"app_name": app_name or ""}
                    )
                    # 使用系统截图
                    import asyncio
                    proc = await asyncio.create_subprocess_exec(
                        "screencapture", "-x", screenshot_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.communicate()
                    if os.path.exists(screenshot_path):
                        result = await find_text_coords(screenshot_path, text)
                        if result and result.get("found"):
                            return await self.execute_action(
                                action_type="click_position",
                                params={"x": result["center_x"], "y": result["center_y"]},
                            )
            except Exception:
                pass
            return {"success": False, "error": f"Text '{text}' not found on screen"}
        best = matches[0]
        return await self.execute_action(
            action_type="click_position",
            params={"x": best["x"], "y": best["y"]},
        )


# 全局单例
_client: Optional[IPCClient] = None


def get_ipc_client() -> IPCClient:
    """获取全局 IPC 客户端实例"""
    global _client
    if _client is None:
        _client = IPCClient()
    return _client


async def is_ipc_available() -> bool:
    """检查 IPC 服务是否可用"""
    client = get_ipc_client()
    return await client.is_available()
