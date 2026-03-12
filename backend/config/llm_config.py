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

from paths import DATA_DIR

CONFIG_FILE = os.path.join(DATA_DIR, "llm_config.json")
# 与 app_state.CLOUD_PROVIDERS 一致，用于持久化“远程回退”配置（当前为本地时，选“远程”用此配置）
CLOUD_PROVIDERS = {"deepseek", "openai", "newapi", "gemini", "anthropic"}


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
    max_tokens: Optional[int] = None,
    remote_fallback_provider: Optional[str] = None,
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
    if max_tokens is not None and max_tokens > 0:
        cfg["max_tokens"] = max_tokens
    # 持久化 LM Studio 的 base_url，供本地检测多端口时使用
    if (provider or cfg.get("provider")) == "lmstudio" and (base_url is not None or cfg.get("base_url")):
        cfg["lm_studio_base_url"] = base_url or cfg.get("base_url", "")
    # 每个云端提供商单独存一份，供“远程回退”按用户选择读取（不再用“最后一次保存”）
    current_provider = (provider or cfg.get("provider") or "").strip().lower()
    if current_provider in CLOUD_PROVIDERS:
        providers = cfg.get("providers") or {}
        providers[current_provider] = {
            "base_url": cfg.get("base_url", ""),
            "model": cfg.get("model", ""),
            "api_key": cfg.get("api_key", ""),
        }
        cfg["providers"] = providers
    # 远程回退：由 Mac 模型页“远程回退策略”显式选择；传空表示默认(DeepSeek)
    if remote_fallback_provider is not None:
        v = (remote_fallback_provider or "").strip().lower()
        cfg["remote_fallback_provider"] = v if v in CLOUD_PROVIDERS else ""
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


def get_lm_studio_base_url() -> str:
    """
    返回 LM Studio 的 base URL（不含 /v1），用于本地多端口检测。
    支持持久化的 lm_studio_base_url 或仅端口；未配置时默认 1234。
    统一使用 localhost，避免 127.0.0.1 与 localhost 行为差异。
    注意：仅当 provider 为 lmstudio 时 base_url 才是 LM Studio 地址；否则 base_url 可能是云端 API，不能用于本地检测。
    """
    cfg = load_llm_config()
    provider = (cfg.get("provider") or "").strip().lower()
    # 仅当 provider 为 lmstudio 时，base_url 才可能是 LM Studio 的地址
    if provider == "lmstudio":
        raw = (cfg.get("lm_studio_base_url") or cfg.get("base_url") or "").strip()
    else:
        raw = (cfg.get("lm_studio_base_url") or "").strip()
    if not raw:
        return "http://localhost:1234"
    # 若为纯数字，视为端口
    if raw.isdigit():
        return f"http://localhost:{raw}"
    # 若为完整 URL 且以 /v1 结尾，去掉 /v1 以便 check_lm_studio 拼 path
    if raw.endswith("/v1"):
        raw = raw[:-3].rstrip("/") or "http://localhost:1234"
    if raw.endswith("/"):
        raw = raw.rstrip("/")
    # 统一为 localhost，避免 127.0.0.1 导致部分环境 502
    if raw.startswith("http://127.0.0.1:") or raw.startswith("https://127.0.0.1:"):
        raw = raw.replace("127.0.0.1", "localhost", 1)
    return raw or "http://localhost:1234"


def get_remote_fallback_config() -> Optional[dict]:
    """
    返回“远程回退”配置（由用户在模型页显式选择的远程提供商）。
    若用户未选择或该提供商未配置，返回 None，由调用方使用默认 DeepSeek。
    兼容旧配置：若无 remote_fallback_provider 但有 remote_fallback_base_url，则用旧扁平键。
    """
    cfg = load_llm_config()
    provider = (cfg.get("remote_fallback_provider") or "").strip().lower()
    # 兼容：旧版只存了扁平键，用主配置 provider 推断（若主配置为云端则即回退）
    if not provider and (cfg.get("remote_fallback_base_url") or cfg.get("remote_fallback_model")):
        provider = (cfg.get("provider") or "").strip().lower()
    if provider not in CLOUD_PROVIDERS:
        return None
    providers = cfg.get("providers") or {}
    slot = providers.get(provider) if isinstance(providers, dict) else None
    if slot and isinstance(slot, dict):
        base_url = (slot.get("base_url") or "").strip()
        model = (slot.get("model") or "").strip()
        api_key = (slot.get("api_key") or "").strip() or get_persisted_api_key() or ""
    else:
        base_url = (cfg.get("remote_fallback_base_url") or "").strip()
        model = (cfg.get("remote_fallback_model") or "").strip()
        api_key = (cfg.get("remote_fallback_api_key") or "").strip() or get_persisted_api_key() or ""
    if not base_url or not model:
        return None
    return {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
    }


def get_cloud_providers_configured() -> list:
    """返回已配置的云端提供商列表，供 Mac 端“远程回退策略”下拉展示。"""
    cfg = load_llm_config()
    providers = cfg.get("providers") or {}
    out = []
    for p in CLOUD_PROVIDERS:
        slot = providers.get(p)
        if not slot or not isinstance(slot, dict):
            continue
        base_url = (slot.get("base_url") or "").strip()
        model = (slot.get("model") or "").strip()
        if base_url and model:
            out.append({
                "provider": p,
                "base_url": base_url,
                "model": model,
                "has_api_key": bool((slot.get("api_key") or "").strip()),
            })
    return out


# ─────────────────────────────────────────────
# 多自定义模型管理
# ─────────────────────────────────────────────

def get_custom_providers() -> list:
    """返回所有用户配置的自定义模型提供商列表。"""
    cfg = load_llm_config()
    return cfg.get("custom_providers") or []


def save_custom_provider(
    provider_id: str,
    name: str,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
) -> dict:
    """新建或更新一个自定义提供商。provider_id 为唯一标识符（如 'glm5' 或 UUID）。"""
    import uuid as _uuid
    cfg = load_llm_config()
    providers: list = cfg.get("custom_providers") or []
    # 查找已存在的
    for i, p in enumerate(providers):
        if p.get("id") == provider_id:
            providers[i] = {
                "id": provider_id,
                "name": name,
                "api_key": api_key,
                "base_url": base_url,
                "model": model,
            }
            break
    else:
        # 新增
        providers.append({
            "id": provider_id or str(_uuid.uuid4())[:8],
            "name": name,
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
        })
    cfg["custom_providers"] = providers
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save custom provider: {e}")
    return next((p for p in providers if p.get("id") == provider_id), {})


def delete_custom_provider(provider_id: str) -> bool:
    """删除指定 ID 的自定义提供商，返回是否成功找到并删除。"""
    cfg = load_llm_config()
    providers: list = cfg.get("custom_providers") or []
    new_providers = [p for p in providers if p.get("id") != provider_id]
    if len(new_providers) == len(providers):
        return False
    cfg["custom_providers"] = new_providers
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to delete custom provider: {e}")
    return True


def get_custom_provider_by_id(provider_id: str) -> Optional[dict]:
    """根据 ID 返回自定义提供商配置，找不到返回 None。"""
    for p in get_custom_providers():
        if p.get("id") == provider_id:
            return p
    return None


def resolve_provider_config(provider_ref: str) -> Optional[dict]:
    """
    根据 provider_ref 解析出完整的 LLM 配置 (api_key, base_url, model)。
    provider_ref 格式:
      - "main"           → 当前主模型
      - "deepseek"       → 云端提供商
      - "openai"         → 云端提供商
      - "custom:{id}"    → 自定义提供商 (按 id 查找)
    返回 {"api_key": ..., "base_url": ..., "model": ...} 或 None。
    """
    if not provider_ref:
        return None
    cfg = load_llm_config()
    persisted_key = get_persisted_api_key() or ""

    # 自定义提供商: "custom:{id}"
    if provider_ref.startswith("custom:"):
        custom_id = provider_ref[7:]
        p = get_custom_provider_by_id(custom_id)
        if p and (p.get("base_url") or "").strip() and (p.get("model") or "").strip():
            return {
                "api_key": (p.get("api_key") or "").strip(),
                "base_url": (p.get("base_url") or "").strip(),
                "model": (p.get("model") or "").strip(),
            }
        return None

    # 主模型
    if provider_ref == "main":
        main_provider = (cfg.get("provider") or "").strip().lower()
        if main_provider in ("ollama", "lmstudio"):
            return None  # 本地模型不支持分身
        base_url = (cfg.get("base_url") or "").strip()
        model = (cfg.get("model") or "").strip()
        api_key = (cfg.get("api_key") or "").strip() or persisted_key
        if base_url and model:
            return {"api_key": api_key, "base_url": base_url, "model": model}
        return None

    # 云端提供商 (deepseek, openai, newapi, gemini, anthropic)
    providers = cfg.get("providers") or {}
    slot = providers.get(provider_ref) if isinstance(providers, dict) else None
    if slot and isinstance(slot, dict):
        base_url = (slot.get("base_url") or "").strip()
        model = (slot.get("model") or "").strip()
        api_key = (slot.get("api_key") or "").strip() or persisted_key
        if base_url and model:
            return {"api_key": api_key, "base_url": base_url, "model": model}

    return None
