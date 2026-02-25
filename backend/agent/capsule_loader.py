"""
Capsule Loader - 从本地目录或 GitHub 加载 EvoMap Capsule
支持：
  - 本地 ./capsules/ 目录递归扫描
  - GitHub raw URL（单文件 JSON/YAML）
  - GitHub repos/contents API 递归扫描整个仓库目录
  - 自动识别 EvoMap 格式（gene/capsule/metadata/signature 或 skill）
  - GEP Capsule 自动转换为 SkillCapsule 格式
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from .capsule_models import (
    SkillCapsule,
    is_evomap_capsule_format,
    gep_capsule_to_skill,
)

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CAPSULES_DIR = BACKEND_ROOT / "capsules"
DEFAULT_CAPSULES_CACHE = BACKEND_ROOT / "capsules_cache"

GITHUB_RAW_PATTERN = re.compile(
    r"^https?://(?:raw\.)?github(?:usercontent)?\.com/[^/]+/[^/]+/[^/]+/.+\.(json|yaml|yml)$",
    re.I,
)

GITHUB_REPO_PATTERN = re.compile(
    r"^https?://(?:api\.)?github\.com/repos/([^/]+)/([^/]+)/contents/(.*)$",
    re.I,
)

GITHUB_SHORTHAND = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+)(?:/tree/([^/]+)/(.+))?/?$",
    re.I,
)


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load JSON {path}: {e}")
        return None


def _load_yaml(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        logger.warning("PyYAML not installed, skip YAML files")
        return None
    except Exception as e:
        logger.warning(f"Failed to load YAML {path}: {e}")
        return None


def _try_convert_gep(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """尝试将 GEP Capsule 转换为 Skill 格式。"""
    if data.get("trigger") is not None and data.get("gene") is not None:
        return gep_capsule_to_skill(data)
    return None


def _parse_single(data: Any, source: str) -> Optional[Dict[str, Any]]:
    """解析单条或列表，返回符合 EvoMap 的 capsule 字典。支持 GEP 自动转换。"""
    if isinstance(data, dict):
        if is_evomap_capsule_format(data):
            # 如果是 GEP 格式但不是 Skill 格式，尝试转换
            if not (data.get("inputs") and data.get("outputs")):
                converted = _try_convert_gep(data)
                if converted:
                    return converted
            return dict(data)
        if "capsule" in data:
            return _parse_single(data["capsule"], source)
        if "gene" in data:
            g = data["gene"]
            if isinstance(g, dict):
                if is_evomap_capsule_format(g):
                    return _parse_single(g, source)
                converted = _try_convert_gep(g)
                if converted:
                    return converted
        return None
    if isinstance(data, list):
        out = []
        for item in data:
            p = _parse_single(item, source)
            if p:
                out.append(p)
        return out[0] if len(out) == 1 else None
    return None


def load_from_file(file_path: Path, source_label: str = "local") -> List[Dict[str, Any]]:
    """
    从单个文件加载 Capsule(s)。
    支持 .json / .yaml / .yml；支持单对象或 {"capsules": [...]} 或数组。
    """
    result: List[Dict[str, Any]] = []
    suffix = file_path.suffix.lower()
    raw: Any = None
    if suffix == ".json":
        raw = _load_json(file_path)
    elif suffix in (".yaml", ".yml"):
        raw = _load_yaml(file_path)
    else:
        return result

    if raw is None:
        return result

    def _annotate(parsed):
        if isinstance(parsed, dict):
            parsed.setdefault("_source", source_label)
            parsed.setdefault("_file", str(file_path))
            parsed.setdefault("source", source_label)
            result.append(parsed)
        elif isinstance(parsed, list):
            for p in parsed:
                _annotate(p)

    if isinstance(raw, list):
        for item in raw:
            parsed = _parse_single(item, source_label)
            _annotate(parsed)
        return result

    if isinstance(raw, dict):
        if "capsules" in raw:
            for c in raw.get("capsules", []):
                parsed = _parse_single(c, source_label)
                _annotate(parsed)
            return result
        parsed = _parse_single(raw, source_label)
        _annotate(parsed)
    return result


def load_from_directory(
    directory: Optional[Path] = None,
    recursive: bool = True,
) -> List[Dict[str, Any]]:
    """从目录加载所有 Capsule 文件。"""
    directory = directory or DEFAULT_CAPSULES_DIR
    if not directory.exists():
        logger.debug(f"Capsules directory does not exist: {directory}")
        return []

    result: List[Dict[str, Any]] = []
    pattern = "**/*" if recursive else "*"
    for ext in ("*.json", "*.yaml", "*.yml"):
        for path in directory.glob(f"{pattern}{ext}"):
            if path.is_file():
                result.extend(load_from_file(path, source_label=f"local:{path.name}"))
    return result


async def load_from_url(url: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """从 URL（如 GitHub raw）拉取并解析为 Capsule 列表。"""
    result: List[Dict[str, Any]] = []
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return [], f"HTTP {resp.status}"
                body = await resp.text()
                ct = (resp.headers.get("Content-Type") or "").lower()
    except Exception as e:
        return [], str(e)

    raw = _parse_body(body, ct, url)
    if raw is None:
        return [], "Empty or unparseable content"

    def _collect(data):
        if isinstance(data, list):
            for item in data:
                parsed = _parse_single(item, f"url:{url[:80]}")
                if isinstance(parsed, dict):
                    parsed.setdefault("_source", "url")
                    parsed.setdefault("_url", url)
                    parsed.setdefault("source", "url")
                    result.append(parsed)
        elif isinstance(data, dict):
            if "capsules" in data:
                _collect(data.get("capsules", []))
            else:
                parsed = _parse_single(data, f"url:{url[:80]}")
                if isinstance(parsed, dict):
                    parsed.setdefault("_source", "url")
                    parsed.setdefault("_url", url)
                    parsed.setdefault("source", "url")
                    result.append(parsed)

    _collect(raw)
    return result, None


def _parse_body(body: str, ct: str, url: str) -> Any:
    """解析 HTTP 响应体为 JSON 或 YAML。"""
    if "json" in ct or url.endswith(".json"):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None
    if "yaml" in ct or url.endswith((".yaml", ".yml")):
        try:
            import yaml
            return yaml.safe_load(body)
        except Exception:
            return None
    # 自动检测
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        try:
            import yaml
            return yaml.safe_load(body)
        except Exception:
            return None


async def load_from_github_repo(
    owner: str,
    repo: str,
    path: str = "",
    branch: str = "main",
    token: str = "",
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    通过 GitHub API 递归扫描仓库目录，加载所有 Capsule 文件。
    支持 repos/contents API，自动递归子目录。
    """
    result: List[Dict[str, Any]] = []
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    if branch:
        api_url += f"?ref={branch}"

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            capsules, err = await _scan_github_dir(session, api_url, f"github:{owner}/{repo}")
            if err:
                return [], err
            result.extend(capsules)
    except Exception as e:
        return [], str(e)

    return result, None


async def _scan_github_dir(
    session: aiohttp.ClientSession,
    api_url: str,
    source_label: str,
    depth: int = 0,
    max_depth: int = 5,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """递归扫描 GitHub 目录。"""
    if depth > max_depth:
        return [], None

    try:
        async with session.get(api_url) as resp:
            if resp.status == 403:
                return [], "GitHub API rate limit exceeded"
            if resp.status != 200:
                return [], f"GitHub API HTTP {resp.status}"
            data = await resp.json()
    except Exception as e:
        return [], str(e)

    result: List[Dict[str, Any]] = []

    if isinstance(data, list):
        for item in data:
            name = item.get("name", "")
            item_type = item.get("type", "")
            download_url = item.get("download_url", "")

            if item_type == "dir":
                sub_url = item.get("url", "")
                if sub_url:
                    sub_caps, _ = await _scan_github_dir(
                        session, sub_url, source_label, depth + 1, max_depth
                    )
                    result.extend(sub_caps)
            elif item_type == "file" and _is_capsule_file(name):
                if download_url:
                    caps, err = await load_from_url(download_url)
                    if caps:
                        for c in caps:
                            c["source"] = f"github:{source_label}"
                        result.extend(caps)
                    elif err:
                        logger.debug(f"Failed to load {download_url}: {err}")
    elif isinstance(data, dict) and data.get("type") == "file":
        download_url = data.get("download_url", "")
        if download_url and _is_capsule_file(data.get("name", "")):
            caps, _ = await load_from_url(download_url)
            result.extend(caps)

    return result, None


def _is_capsule_file(name: str) -> bool:
    """判断文件名是否可能是 Capsule 文件。"""
    lower = name.lower()
    return lower.endswith((".json", ".yaml", ".yml"))


def parse_github_url(url: str) -> Optional[Dict[str, str]]:
    """
    解析 GitHub URL 为 owner/repo/path/branch。
    支持：
      - https://github.com/owner/repo/tree/branch/path
      - https://api.github.com/repos/owner/repo/contents/path
      - https://raw.githubusercontent.com/owner/repo/branch/path
    """
    url = url.strip()

    m = GITHUB_REPO_PATTERN.match(url)
    if m:
        return {"owner": m.group(1), "repo": m.group(2), "path": m.group(3), "branch": "main"}

    m = GITHUB_SHORTHAND.match(url)
    if m:
        return {
            "owner": m.group(1),
            "repo": m.group(2),
            "branch": m.group(3) or "main",
            "path": m.group(4) or "",
        }

    raw_match = re.match(
        r"^https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)$", url
    )
    if raw_match:
        return {
            "owner": raw_match.group(1),
            "repo": raw_match.group(2),
            "branch": raw_match.group(3),
            "path": raw_match.group(4),
        }

    return None


def is_github_raw_url(url: str) -> bool:
    return bool(GITHUB_RAW_PATTERN.match(url.strip()))


def is_github_repo_url(url: str) -> bool:
    return parse_github_url(url) is not None


def load_all_local(
    capsules_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    从默认 ./capsules/ 与 ./capsules_cache/ 加载所有本地/缓存 Capsule。
    去重按 id（后加载覆盖先加载）。
    """
    by_id: Dict[str, Dict[str, Any]] = {}
    for d in (capsules_dir or DEFAULT_CAPSULES_DIR, cache_dir or DEFAULT_CAPSULES_CACHE):
        if d and d.exists():
            for cap in load_from_directory(d, recursive=True):
                cid = cap.get("id") or cap.get("gene") or ""
                if cid:
                    by_id[cid] = cap
    return list(by_id.values())
