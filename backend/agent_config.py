"""
Agent 相关配置持久化（如 LangChain 兼容开关）
供客户端（Mac/iOS 设置）读写，无需重启后端即可生效
"""

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CONFIG_FILE = os.path.join(_DATA_DIR, "agent_config.json")

# 默认启用 LangChain 兼容（未安装依赖时自动退化为原生）
DEFAULT_LANGCHAIN_COMPAT = True


def load_agent_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load agent_config: %s", e)
        return {}


def save_agent_config(updates: dict) -> dict:
    cfg = load_agent_config()
    for k, v in updates.items():
        if v is not None:
            cfg[k] = v
    os.makedirs(_DATA_DIR, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Failed to save agent_config: %s", e)
    return cfg


def get_langchain_compat_from_config() -> Optional[bool]:
    """从配置文件读取 langchain_compat，未设置返回 None（由调用方用 env/默认）"""
    cfg = load_agent_config()
    if "langchain_compat" not in cfg:
        return None
    return bool(cfg["langchain_compat"])
