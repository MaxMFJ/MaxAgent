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


class SmtpConfigUpdate(BaseModel):
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None


class GitHubConfigUpdate(BaseModel):
    github_token: Optional[str] = None


@router.get("/config")
async def get_config():
    llm = get_llm_client()
    if not llm:
        raise HTTPException(status_code=500, detail="LLM client not initialized")
    return {
        "provider": llm.config.provider,
        "model": llm.config.model,
        "base_url": llm.config.base_url,
        "has_api_key": bool(llm.config.api_key),
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
    )

    # 持久化到磁盘，uvicorn reload 后自动恢复
    try:
        from llm_config import save_llm_config
        save_llm_config(
            provider=new_config.provider,
            api_key=new_config.api_key,
            base_url=new_config.base_url,
            model=new_config.model,
        )
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
    from smtp_config import load_smtp_config
    cfg = load_smtp_config()
    return {
        "smtp_server": cfg.get("smtp_server", ""),
        "smtp_port": cfg.get("smtp_port", 465),
        "smtp_user": cfg.get("smtp_user", ""),
        "configured": bool(cfg.get("smtp_server") and cfg.get("smtp_user") and cfg.get("smtp_password")),
    }


@router.post("/config/smtp")
async def update_smtp_config_endpoint(config: SmtpConfigUpdate):
    from smtp_config import update_smtp_config
    result = update_smtp_config(
        smtp_server=config.smtp_server,
        smtp_port=config.smtp_port,
        smtp_user=config.smtp_user,
        smtp_password=config.smtp_password,
    )
    return {"status": "updated", **result}


@router.get("/config/github")
async def get_github_config_endpoint():
    from github_config import load_github_config
    cfg = load_github_config()
    token = (cfg.get("github_token") or "").strip()
    return {"configured": bool(token)}


@router.post("/config/github")
async def update_github_config_endpoint(config: GitHubConfigUpdate):
    from github_config import save_github_config
    save_github_config(github_token=config.github_token)
    return {"status": "updated", "configured": bool((config.github_token or "").strip())}
