"""
统一路径配置。当 Mac App 打包后，Bundle 内 data 只读，
通过环境变量 MACAGENT_DATA_DIR 指定可写目录（Application Support）。
"""
import os

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("MACAGENT_DATA_DIR") or os.path.join(_BACKEND_DIR, "data")
BACKEND_ROOT = _BACKEND_DIR

__all__ = ["DATA_DIR", "_BACKEND_DIR", "BACKEND_ROOT"]
