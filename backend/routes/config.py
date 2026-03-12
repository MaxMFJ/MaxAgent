"""LLM / SMTP / GitHub 配置路由"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app_state import (
    get_llm_client, set_llm_client,
    get_cloud_llm_client, set_cloud_llm_client,
    get_agent_core, set_agent_core,
    get_autonomous_agent,
    CLOUD_PROVIDERS,
)
from agent.llm_client import LLMClient, LLMConfig
from agent.core import AgentCore

router = APIRouter()


class ConfigUpdate(BaseModel):
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = None  # 输出最大 token 数，避免复杂生成被截断；默认 4096，建议 8192 或 16384
    langchain_compat: Optional[bool] = None  # 是否启用 LangChain 兼容（Chat）；未安装依赖时自动用原生
    remote_fallback_provider: Optional[str] = None  # 模型页“远程回退策略”：当使用远程时调用该提供商（newapi/deepseek/openai），空则用默认 DeepSeek


class SmtpConfigUpdate(BaseModel):
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None


class GitHubConfigUpdate(BaseModel):
    github_token: Optional[str] = None


def _langchain_installed() -> bool:
    """动态检查当前环境是否已安装 langchain（不依赖启动时缓存，便于安装后立即生效）"""
    try:
        import langchain_core  # noqa: F401
        import langchain  # noqa: F401
        return True
    except ImportError:
        return False


@router.get("/config")
async def get_config():
    llm = get_llm_client()
    if not llm:
        raise HTTPException(status_code=500, detail="LLM client not initialized")
    from app_state import get_langchain_compat_enabled
    from config.llm_config import load_llm_config, get_cloud_providers_configured
    cfg = load_llm_config()
    return {
        "provider": llm.config.provider,
        "model": llm.config.model,
        "base_url": llm.config.base_url,
        "max_tokens": llm.config.max_tokens,
        "has_api_key": bool(llm.config.api_key),
        "langchain_compat": get_langchain_compat_enabled(),
        "langchain_installed": _langchain_installed(),
        "remote_fallback_provider": (cfg.get("remote_fallback_provider") or "").strip() or None,
        "cloud_providers_configured": get_cloud_providers_configured(),
    }


@router.post("/config")
async def update_config(config: ConfigUpdate):
    llm = get_llm_client()
    current_config = llm.config if llm else LLMConfig()

    new_config = LLMConfig(
        provider=config.provider or current_config.provider,
        api_key=config.api_key or current_config.api_key,
        base_url=config.base_url or current_config.base_url,
        model=config.model or current_config.model,
        max_tokens=config.max_tokens if config.max_tokens is not None else current_config.max_tokens,
    )

    # 持久化到磁盘，uvicorn reload 后自动恢复；远程回退由用户显式选择后传入
    try:
        from config.llm_config import save_llm_config
        save_llm_config(
            provider=new_config.provider,
            api_key=new_config.api_key,
            base_url=new_config.base_url,
            model=new_config.model,
            max_tokens=new_config.max_tokens,
            remote_fallback_provider=config.remote_fallback_provider,
        )
    except Exception:
        pass

    if config.langchain_compat is not None:
        try:
            from config.agent_config import save_agent_config
            save_agent_config({"langchain_compat": config.langchain_compat})
        except Exception:
            pass

    new_llm_client = LLMClient(new_config)
    provider = (new_config.provider or "").lower()

    agent_core = get_agent_core()
    if agent_core:
        agent_core.llm = new_llm_client
        set_llm_client(new_llm_client)
    else:
        set_llm_client(new_llm_client)
        from runtime import get_runtime_adapter
        new_core = AgentCore(new_llm_client, runtime_adapter=get_runtime_adapter())
        set_agent_core(new_core)

    if provider in CLOUD_PROVIDERS:
        set_cloud_llm_client(new_llm_client)
        autonomous = get_autonomous_agent()
        if autonomous:
            autonomous.update_llm(new_llm_client)

    return {"status": "updated", "provider": new_config.provider, "model": new_config.model}


@router.get("/config/smtp")
async def get_smtp_config_endpoint():
    from config.smtp_config import load_smtp_config
    cfg = load_smtp_config()
    return {
        "smtp_server": cfg.get("smtp_server", ""),
        "smtp_port": cfg.get("smtp_port", 465),
        "smtp_user": cfg.get("smtp_user", ""),
        "configured": bool(cfg.get("smtp_server") and cfg.get("smtp_user") and cfg.get("smtp_password")),
    }


@router.post("/config/smtp")
async def update_smtp_config_endpoint(config: SmtpConfigUpdate):
    from config.smtp_config import update_smtp_config
    result = update_smtp_config(
        smtp_server=config.smtp_server,
        smtp_port=config.smtp_port,
        smtp_user=config.smtp_user,
        smtp_password=config.smtp_password,
    )
    return {"status": "updated", **result}


@router.get("/config/github")
async def get_github_config_endpoint():
    from config.github_config import load_github_config
    cfg = load_github_config()
    token = (cfg.get("github_token") or "").strip()
    return {"configured": bool(token)}


@router.post("/config/github")
async def update_github_config_endpoint(config: GitHubConfigUpdate):
    from config.github_config import save_github_config, apply_github_config
    save_github_config(github_token=config.github_token)
    apply_github_config()  # 立即生效，供后续 open_skills sync 使用
    return {"status": "updated", "configured": bool((config.github_token or "").strip())}


@router.post("/config/install-langchain")
async def install_langchain_dependencies():
    """
    尝试安装 LangChain 可选依赖（pip install -r requirements-langchain.txt）。
    供客户端在用户开启「使用 LangChain 进行对话」时调用；失败时客户端提示用户自行安装。
    """
    import subprocess
    import sys
    import os

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    req_file = os.path.join(backend_dir, "requirements-langchain.txt")
    if not os.path.isfile(req_file):
        return {
            "success": False,
            "message": f"未找到 {req_file}，请确认后端目录正确。",
            "stderr": "",
        }
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=backend_dir,
        )
        if result.returncode == 0:
            return {"success": True, "message": "LangChain 依赖安装成功。", "stderr": result.stderr or ""}
        return {
            "success": False,
            "message": result.stderr or result.stdout or f"pip 退出码 {result.returncode}",
            "stderr": result.stderr or "",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "安装超时（120 秒）。请在后端目录自行执行: pip install -r requirements-langchain.txt", "stderr": ""}
    except Exception as e:
        return {"success": False, "message": str(e), "stderr": ""}


# ─────────────────────────────────────────────
# 多自定义模型提供商 CRUD
# ─────────────────────────────────────────────

class CustomProviderUpdate(BaseModel):
    id: Optional[str] = None          # 留空时后端自动生成 UUID 短串
    name: str                          # 厂商/模型别名，用于 UI 展示
    api_key: Optional[str] = ""
    base_url: Optional[str] = ""
    model: Optional[str] = ""


@router.get("/config/custom-providers")
async def list_custom_providers():
    """返回所有用户自定义模型提供商列表（api_key 脱敏）。"""
    from config.llm_config import get_custom_providers
    providers = get_custom_providers()
    return {
        "providers": [
            {
                "id": p.get("id"),
                "name": p.get("name") or "",
                "base_url": p.get("base_url") or "",
                "model": p.get("model") or "",
                "has_api_key": bool((p.get("api_key") or "").strip()),
            }
            for p in providers
        ]
    }


@router.post("/config/custom-providers")
async def upsert_custom_provider(body: CustomProviderUpdate):
    """新建或更新自定义模型提供商。id 不存在时自动新建。"""
    import uuid as _uuid
    from config.llm_config import save_custom_provider
    provider_id = (body.id or "").strip() or str(_uuid.uuid4())[:8]
    result = save_custom_provider(
        provider_id=provider_id,
        name=body.name.strip(),
        api_key=(body.api_key or "").strip(),
        base_url=(body.base_url or "").strip(),
        model=(body.model or "").strip(),
    )
    return {
        "status": "ok",
        "id": result.get("id"),
        "name": result.get("name"),
        "base_url": result.get("base_url"),
        "model": result.get("model"),
        "has_api_key": bool((result.get("api_key") or "").strip()),
    }


@router.delete("/config/custom-providers/{provider_id}")
async def remove_custom_provider(provider_id: str):
    """删除指定 ID 的自定义模型提供商。"""
    from config.llm_config import delete_custom_provider
    deleted = delete_custom_provider(provider_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Custom provider '{provider_id}' not found")
    return {"status": "deleted", "id": provider_id}


@router.get("/config/llm-providers-for-import")
async def get_llm_providers_for_import():
    """
    返回主 Agent 已配置的在线 LLM 列表，供子 Duck 配置时一键导入。
    包含：当前主模型、云端提供商（DeepSeek/OpenAI/Gemini 等）、自定义提供商。
    每个条目含 provider/name, api_key, base_url, model。
    """
    from config.llm_config import (
        load_llm_config,
        get_persisted_api_key,
        get_custom_providers,
        CLOUD_PROVIDERS,
    )
    cfg = load_llm_config()
    persisted_key = get_persisted_api_key() or ""
    providers: list[dict] = []

    # 1. 当前主模型（主 Agent 正在使用的配置，仅在线 LLM）
    main_provider = (cfg.get("provider") or "deepseek").strip().lower()
    if main_provider not in ("ollama", "lmstudio"):
        main_base = (cfg.get("base_url") or "").strip()
        main_model = (cfg.get("model") or "").strip()
        main_key = (cfg.get("api_key") or "").strip() or persisted_key
        if main_base and main_model:
            providers.append({
                "provider": main_provider,
                "provider_ref": "main",
                "name": f"主模型 ({main_provider})",
                "api_key": main_key,
                "base_url": main_base,
                "model": main_model,
            })

    # 2. 云端提供商（providers 中已配置的）
    slots = cfg.get("providers") or {}
    for p in CLOUD_PROVIDERS:
        slot = slots.get(p) if isinstance(slots, dict) else None
        if not slot or not isinstance(slot, dict):
            continue
        base_url = (slot.get("base_url") or "").strip()
        model = (slot.get("model") or "").strip()
        api_key = (slot.get("api_key") or "").strip() or persisted_key
        if base_url and model:
            providers.append({
                "provider": p,
                "provider_ref": p,
                "name": p,
                "api_key": api_key,
                "base_url": base_url,
                "model": model,
            })

    # 3. 自定义提供商
    for p in get_custom_providers():
        if not isinstance(p, dict):
            continue
        base_url = (p.get("base_url") or "").strip()
        model = (p.get("model") or "").strip()
        custom_id = (p.get("id") or "").strip()
        if base_url and model:
            providers.append({
                "provider": "custom",
                "provider_ref": f"custom:{custom_id}" if custom_id else "custom",
                "name": (p.get("name") or custom_id or "自定义").strip(),
                "api_key": (p.get("api_key") or "").strip(),
                "base_url": base_url,
                "model": model,
            })

    return {"providers": providers}


# ─────────────────────────────────────────────
# TuriX Actor 视觉模型配置
# ─────────────────────────────────────────────

class TurixConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    force_vision: Optional[bool] = None  # 强制视觉模式（跳过 AX），用于测试


@router.get("/config/turix")
async def get_turix_config():
    """获取 TuriX Actor 视觉模型配置（api_key 脱敏）。"""
    from config.agent_config import load_agent_config
    cfg = load_agent_config()
    return {
        "enabled": cfg.get("turix_enabled", False),
        "has_api_key": bool((cfg.get("turix_api_key") or "").strip()),
        "base_url": cfg.get("turix_base_url", "https://turixapi.io/v1"),
        "model": cfg.get("turix_model", "turix-actor"),
        "force_vision": cfg.get("turix_force_vision", False),
    }


@router.post("/config/turix")
async def update_turix_config(body: TurixConfigUpdate):
    """更新 TuriX Actor 视觉模型配置。"""
    from config.agent_config import save_agent_config
    updates = {}
    if body.enabled is not None:
        updates["turix_enabled"] = body.enabled
    if body.api_key is not None:
        updates["turix_api_key"] = body.api_key.strip()
    if body.base_url is not None:
        updates["turix_base_url"] = body.base_url.strip()
    if body.model is not None:
        updates["turix_model"] = body.model.strip()
    if body.force_vision is not None:
        updates["turix_force_vision"] = body.force_vision
    if updates:
        save_agent_config(updates)
        # 重置 TuriX Actor 单例以加载新配置
        try:
            from runtime.turix_actor import get_turix_actor
            actor = get_turix_actor()
            actor._config = None
            actor._client = None
        except Exception:
            pass
    return {"status": "updated"}
