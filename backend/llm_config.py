"""
LLM 配置持久化
将用户通过 Mac App 配置的 API key / provider / model 保存到磁盘，
uvicorn reload 后自动恢复，避免丢失运行时配置。
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CONFIG_FILE = os.path.join(DATA_DIR, "llm_config.json")


def load_llm_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load llm_config: {e}")
        return {}


def save_llm_config(
    *,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    cfg = load_llm_config()
    if provider is not None:
        cfg["provider"] = provider
    if api_key is not None:
        cfg["api_key"] = api_key
    if base_url is not None:
        cfg["base_url"] = base_url
    if model is not None:
        cfg["model"] = model
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save llm_config: {e}")
    return cfg


def get_persisted_api_key() -> Optional[str]:
    """优先返回持久化的 api_key，其次 env var"""
    cfg = load_llm_config()
    key = cfg.get("api_key", "").strip()
    if key:
        return key
    return os.getenv("DEEPSEEK_API_KEY")
