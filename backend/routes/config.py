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
    )

    # 持久化到磁盘，uvicorn reload 后自动恢复；远程回退由用户显式选择后传入
    try:
        from config.llm_config import save_llm_config
        save_llm_config(
            provider=new_config.provider,
            api_key=new_config.api_key,
            base_url=new_config.base_url,
            model=new_config.model,
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
    from config.github_config import save_github_config
    save_github_config(github_token=config.github_token)
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
