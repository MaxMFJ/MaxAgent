"""
SMTP 配置存储：支持环境变量 + 文件持久化
Mac App 设置页填写后通过 API 写入，mail_tool 从此模块读取
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
        from paths import DATA_DIR
        _config_path = Path(DATA_DIR) / "smtp_config.json"
    return _config_path


def load_smtp_config() -> dict:
    """从文件加载 SMTP 配置（启动时或 API 更新后调用）"""
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


def save_smtp_config(config: dict) -> None:
    """保存 SMTP 配置到文件"""
    global _cached
    path = _get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    _cached = config


# 常见邮箱域名 → SMTP 服务器
_DOMAIN_SMTP = {
    "qq.com": ("smtp.qq.com", 465),
    "163.com": ("smtp.163.com", 465),
    "126.com": ("smtp.126.com", 465),
    "gmail.com": ("smtp.gmail.com", 587),
    "outlook.com": ("smtp.office365.com", 587),
    "hotmail.com": ("smtp.office365.com", 587),
    "icloud.com": ("smtp.mail.me.com", 587),
    "me.com": ("smtp.mail.me.com", 587),
}


def _infer_smtp_from_email(email: str) -> tuple:
    """根据邮箱地址推断 SMTP 服务器"""
    if not email or "@" not in email:
        return None, 465
    domain = email.strip().split("@")[-1].lower()
    return _DOMAIN_SMTP.get(domain, (None, 465))


def get_smtp_config() -> tuple:
    """
    获取 SMTP 配置：优先环境变量，其次文件，最后根据邮箱域名推断
    返回 (server, port, user, password)
    """
    server = os.environ.get("MACAGENT_SMTP_SERVER") or ""
    port_str = os.environ.get("MACAGENT_SMTP_PORT", "465")
    user = os.environ.get("MACAGENT_SMTP_USER") or ""
    password = os.environ.get("MACAGENT_SMTP_PASSWORD") or ""

    if not all([server.strip(), user, password]):
        cfg = load_smtp_config()
        server = (server or cfg.get("smtp_server") or "").strip()
        user = user or cfg.get("smtp_user") or ""
        password = password or cfg.get("smtp_password") or ""
        if "smtp_port" in cfg and cfg["smtp_port"] is not None:
            port_str = str(cfg["smtp_port"])
        # 若 server 仍为空但有邮箱和密码，根据邮箱域名推断
        if not server and user:
            server, port_str = _infer_smtp_from_email(user)
            port_str = str(port_str) if server else "465"

    try:
        port = int(port_str)
    except (ValueError, TypeError):
        port = 465

    return (server or None, port, user or None, password or None)


def update_smtp_config(
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> dict:
    """
    更新 SMTP 配置（API 调用），未提供的字段保留原值
    """
    cfg = load_smtp_config()
    if smtp_server is not None:
        cfg["smtp_server"] = smtp_server
    if smtp_port is not None:
        cfg["smtp_port"] = smtp_port
    if smtp_user is not None:
        cfg["smtp_user"] = smtp_user
    if smtp_password is not None:
        cfg["smtp_password"] = smtp_password
    save_smtp_config(cfg)
    return {k: v for k, v in cfg.items() if k != "smtp_password"}
