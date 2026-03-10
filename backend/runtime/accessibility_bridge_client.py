"""
accessibility_bridge_client.py
Python 客户端 — 调用 Swift AccessibilityBridge HTTP 服务 (端口 5650)

当 Python 进程没有辅助功能权限，或 pyobjc 不可用时，
可通过此客户端调用运行在 Swift App 进程中的原生 AX API。

Swift Bridge 端点:
  GET  /ax/status       — 检查 Bridge 状态与权限
  GET  /ax/apps         — 列出所有运行中的应用
  POST /ax/windows      — 获取应用窗口信息
  POST /ax/elements     — 获取元素树（层级结构）
  POST /ax/elements/flat — 获取扁平元素列表
  POST /ax/action       — 执行元素操作（如点击按钮）
  POST /ax/set-value    — 设置元素值（如输入文本）
  GET  /ax/focused      — 获取当前聚焦元素
  POST /ax/element-at   — 获取指定坐标处的元素
  POST /ax/find         — 按条件搜索元素
"""

import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)


def _read_bridge_port() -> int:
    """从共享配置文件读取 AX Bridge 端口，回退到默认值"""
    config_path = os.path.join(tempfile.gettempdir(), "macagent_ports.json")
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
            return int(cfg.get("ax_bridge_port", 5650))
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return 5650


BRIDGE_BASE_URL = f"http://127.0.0.1:{_read_bridge_port()}"
BRIDGE_TIMEOUT = aiohttp.ClientTimeout(total=10)


async def _request(method: str, path: str, json_body: Optional[dict] = None) -> Tuple[bool, dict]:
    """发送请求到 Swift Bridge"""
    url = f"{BRIDGE_BASE_URL}{path}"
    try:
        async with aiohttp.ClientSession(timeout=BRIDGE_TIMEOUT) as session:
            if method == "GET":
                async with session.get(url) as resp:
                    data = await resp.json()
                    return resp.status == 200, data
            else:
                async with session.post(url, json=json_body or {}) as resp:
                    data = await resp.json()
                    return resp.status == 200, data
    except aiohttp.ClientConnectorError:
        logger.debug("Swift AX Bridge 未运行 (端口 %s)", BRIDGE_BASE_URL)
        return False, {"error": "Bridge not running"}
    except Exception as e:
        logger.warning("Swift AX Bridge 请求失败: %s", e)
        return False, {"error": str(e)}


async def is_bridge_available() -> bool:
    """检查 Swift Bridge 是否可用"""
    ok, data = await _request("GET", "/ax/status")
    return ok and data.get("trusted", False)


async def get_status() -> Dict[str, Any]:
    """获取 Bridge 状态"""
    ok, data = await _request("GET", "/ax/status")
    return data


async def list_apps() -> List[Dict[str, Any]]:
    """列出所有打开的应用"""
    ok, data = await _request("GET", "/ax/apps")
    if ok:
        return data.get("apps", [])
    return []


async def get_windows(app_name: str) -> List[Dict[str, Any]]:
    """获取应用的窗口列表"""
    ok, data = await _request("POST", "/ax/windows", {"app_name": app_name})
    if ok:
        return data.get("windows", [])
    return []


async def get_element_tree(
    app_name: str,
    max_depth: int = 5,
    window_index: int = 0,
) -> List[Dict[str, Any]]:
    """获取元素树（含子元素层级）"""
    ok, data = await _request("POST", "/ax/elements", {
        "app_name": app_name,
        "max_depth": max_depth,
        "window_index": window_index,
    })
    if ok:
        return data.get("elements", [])
    return []


async def get_flat_elements(
    app_name: str,
    max_depth: int = 5,
    window_index: int = 0,
    max_count: int = 200,
) -> Tuple[List[Dict[str, Any]], int]:
    """获取扁平元素列表 — 返回 (elements, total_count)"""
    ok, data = await _request("POST", "/ax/elements/flat", {
        "app_name": app_name,
        "max_depth": max_depth,
        "window_index": window_index,
        "max_count": max_count,
    })
    if ok:
        return data.get("elements", []), data.get("total_count", 0)
    return [], 0


async def perform_action(
    app_name: str,
    role: Optional[str] = None,
    title: Optional[str] = None,
    action_name: str = "AXPress",
    window_index: int = 0,
) -> Tuple[bool, str]:
    """通过 AX API 执行元素操作"""
    ok, data = await _request("POST", "/ax/action", {
        "app_name": app_name,
        "role": role,
        "title": title,
        "action_name": action_name,
        "window_index": window_index,
    })
    if ok and data.get("success"):
        return True, ""
    return False, data.get("error", "Action failed")


async def set_value(
    app_name: str,
    value: str,
    role: Optional[str] = None,
    title: Optional[str] = None,
    window_index: int = 0,
) -> Tuple[bool, str]:
    """通过 AX API 设置元素值"""
    ok, data = await _request("POST", "/ax/set-value", {
        "app_name": app_name,
        "role": role,
        "title": title,
        "value": value,
        "window_index": window_index,
    })
    if ok and data.get("success"):
        return True, ""
    return False, data.get("error", "Set value failed")


async def get_focused_element() -> Optional[Dict[str, Any]]:
    """获取当前聚焦元素"""
    ok, data = await _request("GET", "/ax/focused")
    if ok:
        elem = data.get("element")
        if elem and not isinstance(elem, type(None)):
            return elem
    return None


async def get_element_at(x: float, y: float) -> Optional[Dict[str, Any]]:
    """获取指定坐标处的元素"""
    ok, data = await _request("POST", "/ax/element-at", {"x": x, "y": y})
    if ok:
        elem = data.get("element")
        if elem and not isinstance(elem, type(None)):
            return elem
    return None


async def find_elements(
    app_name: str,
    role: Optional[str] = None,
    title: Optional[str] = None,
    max_depth: int = 5,
    window_index: int = 0,
    max_count: int = 50,
) -> List[Dict[str, Any]]:
    """按条件搜索元素"""
    body: Dict[str, Any] = {"app_name": app_name, "max_depth": max_depth, "window_index": window_index, "max_count": max_count}
    if role:
        body["role"] = role
    if title:
        body["title"] = title
    ok, data = await _request("POST", "/ax/find", body)
    if ok:
        return data.get("elements", [])
    return []
