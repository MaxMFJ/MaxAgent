"""
GitHub Token 配置：用于拉取开放技能源（Open Skill Sources），提高 API 限额。
支持环境变量 GITHUB_TOKEN + 文件持久化；Mac 设置页通过 API 写入后在此读取。
"""
import json
import os
from pathlib import Path
from typing import Optional

_config_path: Optional[Path] = None
_cached: Optional[dict] = None


def _get_config_path() -> Path:
    global _config_path
    if _config_path is None:
        base = Path(__file__).resolve().parent.parent  # backend/
        _config_path = base / "data" / "github_config.json"
    return _config_path


def load_github_config() -> dict:
    """从文件加载 GitHub 配置"""
    global _cached
    path = _get_config_path()
    if not path.exists():
        _cached = {}
        return _cached
    try:
        with open(path, "r", encoding="utf-8") as f:
            _cached = json.load(f)
        return _cached or {}
    except Exception:
        _cached = {}
        return _cached


def save_github_config(github_token: Optional[str] = None) -> dict:
    """保存 GitHub 配置到文件；传入 None 表示不覆盖已有 token"""
    global _cached
    path = _get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_github_config()
    if github_token is not None:
        current["github_token"] = github_token
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    _cached = current
    return current


def get_github_token() -> str:
    """优先返回环境变量 GITHUB_TOKEN，否则返回文件中保存的 token（供 open_skill_sources / capsule_sync 使用）"""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    cfg = load_github_config()
    return (cfg.get("github_token") or "").strip()


def apply_github_config() -> None:
    """将文件中的 token 写入当前进程环境，使 os.environ.get('GITHUB_TOKEN') 生效"""
    token = load_github_config().get("github_token") or ""
    if token:
        os.environ["GITHUB_TOKEN"] = token
