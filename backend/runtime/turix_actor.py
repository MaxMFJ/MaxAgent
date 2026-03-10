"""
TuriX Actor 视觉定位服务 — AX 失败后的 VLM 回退层

利用 TuriX Actor 模型（turix-actor）从截图中预测精确点击坐标。
Actor 模型接收截图 + 目标描述 → 返回归一化坐标 (0-1000)。

接口协议：OpenAI 兼容 Chat Completion API（支持 Vision）
默认端点：https://turixapi.io/v1
也支持本地 Ollama 部署。

用法：
    from runtime.turix_actor import TurixActorService
    service = TurixActorService()
    result = await service.locate_element("文件传输助手", screenshot_path="/tmp/screen.png")
    # result = {"found": True, "x": 523, "y": 312, "action": "Click", "normalized": [523, 312]}
"""

import asyncio
import base64
import json
import logging
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---- 屏幕分辨率 ----
def _get_screen_size() -> Tuple[int, int]:
    """返回 (width, height) 像素"""
    try:
        from Quartz import CGDisplayPixelsWide, CGDisplayPixelsHigh, CGMainDisplayID
        did = CGMainDisplayID()
        return int(CGDisplayPixelsWide(did)), int(CGDisplayPixelsHigh(did))
    except Exception:
        return 1920, 1080


def _screenshot_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _capture_screenshot() -> Optional[str]:
    """截取全屏，返回临时文件路径"""
    path = f"/tmp/turix_actor_{int(time.time())}.png"
    try:
        subprocess.run(["screencapture", "-x", "-C", path], check=True, timeout=5)
        if os.path.exists(path):
            return path
    except Exception as e:
        logger.warning("[TurixActor] screenshot failed: %s", e)
    return None


# ---- 配置读取 ----
def _load_turix_config() -> Dict[str, str]:
    """
    读取 TuriX Actor 配置，优先级：
    1. agent_config.json 中的 turix_* 字段（专用配置）
    2. 环境变量 TURIX_API_KEY / TURIX_BASE_URL / TURIX_MODEL
    3. 复用用户已配置的主 LLM（llm_config.json 中的 api_key/base_url）
    4. 内置默认值

    支持场景：
    - TuriX 官方 API（turixapi.io）
    - OpenAI GPT-4o Vision
    - LM Studio 本地视觉模型（http://localhost:1234/v1）
    - 任何 OpenAI 兼容的 VLM 端点
    """
    cfg: Dict[str, str] = {}

    # 1. 读取 TuriX 专用配置
    try:
        from config.agent_config import load_agent_config
        ac = load_agent_config()
        cfg["api_key"] = ac.get("turix_api_key", "")
        cfg["base_url"] = ac.get("turix_base_url", "")
        cfg["model"] = ac.get("turix_model", "")
        cfg["enabled"] = str(ac.get("turix_enabled", ""))
    except Exception:
        pass

    # 2. 环境变量覆盖
    cfg["api_key"] = os.environ.get("TURIX_API_KEY", "") or cfg.get("api_key", "")
    cfg["base_url"] = os.environ.get("TURIX_BASE_URL", "") or cfg.get("base_url", "")
    cfg["model"] = os.environ.get("TURIX_MODEL", "") or cfg.get("model", "")

    # 3. 如果没有专用配置，复用用户已配置的主 LLM
    if not cfg.get("api_key"):
        try:
            from config.llm_config import load_llm_config
            llm_cfg = load_llm_config()
            provider = (llm_cfg.get("provider") or "").lower()
            # 仅复用支持 Vision 的在线 LLM（不复用 ollama 等纯文本本地模型）
            if provider in ("openai", "deepseek", "newapi", "anthropic", "gemini", "lmstudio", "custom"):
                cfg["api_key"] = cfg["api_key"] or llm_cfg.get("api_key", "")
                if not cfg.get("base_url"):
                    cfg["base_url"] = llm_cfg.get("base_url", "")
                if not cfg.get("model"):
                    # 复用主 LLM 的模型（用户已选好的 VLM）
                    cfg["model"] = llm_cfg.get("model", "")
                logger.info("[TurixActor] 复用主 LLM 配置: provider=%s, base_url=%s, model=%s",
                            provider, cfg.get("base_url", "")[:50], cfg.get("model", ""))
        except Exception:
            pass

    # 4. 默认值：仅当有 TuriX 专用 key 时使用 TuriX 端点
    if not cfg.get("base_url"):
        cfg["base_url"] = "https://turixapi.io/v1"
    if not cfg.get("model"):
        cfg["model"] = "turix-actor"

    return cfg


class TurixActorService:
    """
    封装 TuriX Actor 模型调用。
    输入：截图 + 目标元素描述
    输出：屏幕像素坐标 (x, y)
    """

    # Actor 模型的坐标空间: 0-1000
    COORD_RANGE = 1000

    def __init__(self):
        self._config: Optional[Dict[str, str]] = None
        self._client = None

    def _get_config(self) -> Dict[str, str]:
        if self._config is None:
            self._config = _load_turix_config()
        return self._config

    def is_available(self) -> bool:
        """检查 TuriX Actor 是否可用（有 API key — 来自专用配置或主 LLM）"""
        cfg = self._get_config()
        enabled = cfg.get("enabled", "").lower()
        if enabled == "false":
            return False
        # 有 api_key 即可用（可能来自 turix 专用配置或主 LLM 复用）
        # LM Studio 等本地服务不需要 api_key
        has_key = bool(cfg.get("api_key"))
        is_local = any(local in (cfg.get("base_url") or "") for local in ("localhost", "127.0.0.1", "0.0.0.0"))
        return has_key or is_local

    def _get_client(self):
        """延迟创建 OpenAI 客户端"""
        if self._client is None:
            from openai import AsyncOpenAI
            cfg = self._get_config()
            # LM Studio 等本地服务可能不需要 api_key，用 dummy 值
            api_key = cfg.get("api_key") or "lm-studio"
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=cfg["base_url"],
            )
        return self._client

    def _build_messages(
        self,
        target_description: str,
        screenshot_b64: str,
        action_hint: str = "Click",
    ) -> List[Dict[str, Any]]:
        """
        构造 Actor 模型的消息。
        与 TuriX-CUA 兼容的精简 prompt — 只要求返回点击坐标。
        """
        system_msg = {
            "role": "system",
            "content": (
                "You are a precise UI element locator for macOS desktop screenshots.\n"
                "Given a screenshot and a target element description, "
                "output the pixel coordinates where that element is located.\n"
                "Output ONLY a JSON object in this exact format:\n"
                '{"action": [{"Click": {"position": [x, y]}}]}\n'
                "where x and y are the pixel coordinates of the element's center in the image.\n"
                "If the element is not found, output:\n"
                '{"action": [{"done": {"text": "element not found"}}]}'
            ),
        }
        user_msg = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Find and {action_hint} the element: \"{target_description}\"",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{screenshot_b64}",
                    },
                },
            ],
        }
        return [system_msg, user_msg]

    def _parse_response(self, content: str) -> Optional[Dict[str, Any]]:
        """
        从 Actor 模型响应中解析坐标。
        返回 {"action": "Click", "raw_coords": [x, y]} 或 None。
        """
        # 尝试直接 JSON 解析
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # 尝试从 markdown code block 提取
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                except json.JSONDecodeError:
                    return None
            else:
                # 尝试提取第一个 JSON 对象
                m = re.search(r"\{.*\}", content, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(0))
                    except json.JSONDecodeError:
                        return None
                else:
                    return None

        actions = data.get("action", [])
        if not isinstance(actions, list) or not actions:
            return None

        for act in actions:
            if not isinstance(act, dict):
                continue
            # Click action
            if "Click" in act:
                pos = act["Click"].get("position", [])
                if isinstance(pos, list) and len(pos) >= 2:
                    return {
                        "action": "Click",
                        "raw_coords": [int(pos[0]), int(pos[1])],
                    }
            # done = element not found
            if "done" in act:
                return None

        return None

    def _to_screen_coords(self, raw_x: int, raw_y: int, img_w: int = 0, img_h: int = 0) -> Tuple[int, int]:
        """
        将模型返回的坐标转换为屏幕像素坐标（CGEvent 坐标系）。

        自动检测坐标空间：
        - 如果 max(x,y) > 1000 → 像素坐标（Claude/GPT 常见行为）
          - 如果有截图尺寸信息，按 img→screen 比例缩放
          - 否则假定像素坐标 = 屏幕坐标（非 Retina 场景）
        - 如果 max(x,y) <= 1000 → 归一化坐标（turix-actor 协议）
        """
        sw, sh = _get_screen_size()

        if max(raw_x, raw_y) > self.COORD_RANGE:
            # 像素坐标模式
            if img_w > 0 and img_h > 0 and (img_w != sw or img_h != sh):
                # 截图分辨率与屏幕不同（Retina 等），按比例缩放
                x = int(raw_x * sw / img_w)
                y = int(raw_y * sh / img_h)
            else:
                # 截图分辨率 = 屏幕分辨率，直接使用
                x = min(raw_x, sw - 1)
                y = min(raw_y, sh - 1)
            logger.debug("[TurixActor] pixel coords (%d,%d) → screen (%d,%d)", raw_x, raw_y, x, y)
            return x, y
        else:
            # 归一化坐标模式 (0-1000)
            x = int(raw_x * sw / self.COORD_RANGE)
            y = int(raw_y * sh / self.COORD_RANGE)
            logger.debug("[TurixActor] normalized (%d,%d) → screen (%d,%d)", raw_x, raw_y, x, y)
            return x, y

    async def locate_element(
        self,
        target_description: str,
        screenshot_path: Optional[str] = None,
        action_hint: str = "Click",
        timeout: float = 15.0,
    ) -> Dict[str, Any]:
        """
        使用 TuriX Actor 模型定位 UI 元素。

        Args:
            target_description: 元素描述（如 "文件传输助手", "发送按钮"）
            screenshot_path: 截图路径（None 则自动截屏）
            action_hint: 动作类型提示（"Click" / "input_text"）
            timeout: API 调用超时（秒）

        Returns:
            {
                "found": bool,
                "x": int,           # 屏幕像素坐标
                "y": int,
                "normalized": [nx, ny],  # 0-1000 归一化坐标
                "action": str,
                "source": "turix_actor",
                "error": str,       # 仅失败时
            }
        """
        if not self.is_available():
            return {"found": False, "error": "TuriX Actor not configured", "source": "turix_actor"}

        # 截图
        auto_screenshot = False
        if screenshot_path is None:
            screenshot_path = _capture_screenshot()
            auto_screenshot = True
        if screenshot_path is None or not os.path.exists(screenshot_path):
            return {"found": False, "error": "Screenshot failed", "source": "turix_actor"}

        try:
            b64 = _screenshot_to_base64(screenshot_path)

            # 获取截图尺寸（用于坐标空间自动检测）
            img_w, img_h = 0, 0
            try:
                import struct
                with open(screenshot_path, "rb") as f:
                    header = f.read(32)
                    if header[:8] == b'\x89PNG\r\n\x1a\n':
                        # PNG: IHDR chunk at offset 16
                        img_w = struct.unpack(">I", header[16:20])[0]
                        img_h = struct.unpack(">I", header[20:24])[0]
            except Exception:
                pass

            messages = self._build_messages(target_description, b64, action_hint)
            cfg = self._get_config()
            client = self._get_client()

            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=cfg["model"],
                    messages=messages,
                    max_tokens=256,
                    temperature=0.0,
                ),
                timeout=timeout,
            )

            content = response.choices[0].message.content or ""
            logger.debug("[TurixActor] raw response: %s", content[:300])

            parsed = self._parse_response(content)
            if parsed is None:
                return {"found": False, "error": "Actor returned no valid coordinates", "source": "turix_actor"}

            rx, ry = parsed["raw_coords"]
            sx, sy = self._to_screen_coords(rx, ry, img_w, img_h)

            return {
                "found": True,
                "x": sx,
                "y": sy,
                "raw_coords": [rx, ry],
                "action": parsed["action"],
                "source": "turix_actor",
            }

        except asyncio.TimeoutError:
            logger.warning("[TurixActor] API call timed out after %.1fs", timeout)
            return {"found": False, "error": f"API timeout ({timeout}s)", "source": "turix_actor"}
        except Exception as e:
            logger.warning("[TurixActor] API call failed: %s", e)
            return {"found": False, "error": str(e), "source": "turix_actor"}
        finally:
            if auto_screenshot and screenshot_path:
                try:
                    os.remove(screenshot_path)
                except OSError:
                    pass

    async def find_elements(
        self,
        target_description: str,
        screenshot_path: Optional[str] = None,
        timeout: float = 15.0,
    ) -> List[Dict[str, Any]]:
        """
        视觉查找元素，返回与 _find_elements 兼容的元素列表。
        TuriX Actor 通常只返回一个最佳匹配。
        """
        result = await self.locate_element(
            target_description,
            screenshot_path=screenshot_path,
            timeout=timeout,
        )
        if not result.get("found"):
            return []

        return [{
            "name": target_description,
            "role": "TurixVision",
            "center": {"x": result["x"], "y": result["y"]},
            "raw_coords": result.get("raw_coords"),
            "confidence": 0.9,
            "source": "turix_actor",
        }]


# ---- 模块级单例 ----
_service: Optional[TurixActorService] = None


def get_turix_actor() -> TurixActorService:
    """获取全局 TurixActorService 单例"""
    global _service
    if _service is None:
        _service = TurixActorService()
    return _service
