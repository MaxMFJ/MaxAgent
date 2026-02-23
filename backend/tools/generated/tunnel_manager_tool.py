"""
Tunnel Manager Tool - 隧道管理工具
隧道控制、配置管理、连接控制、服务管理
作为 tunnel_monitor 的补充，提供隧道管理功能
"""
import asyncio
import json
import os
import shutil
from typing import Any, Dict, Optional

from tools.base import BaseTool, ToolResult, ToolCategory
from tools.cloudflared_utils import (
    BACKEND_PORT,
    get_cloudflared_path,
    get_cloudflared_restart_command,
)

# 配置存储目录（项目内，避免写入用户主目录）
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "tunnel_configs")
STATE_FILE = os.path.join(CONFIG_DIR, "tunnel_state.json")
ROLLBACK_FILE = os.path.join(CONFIG_DIR, "rollback_state.json")


def _ensure_config_dir() -> None:
    """确保配置目录存在"""
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _load_state() -> Dict[str, Any]:
    """加载隧道状态"""
    _ensure_config_dir()
    if not os.path.isfile(STATE_FILE):
        return {"tunnels": {}, "connections": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"tunnels": {}, "connections": {}}


def _save_state(state: Dict[str, Any]) -> bool:
    """保存隧道状态"""
    _ensure_config_dir()
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except IOError:
        return False


def _save_rollback(state: Dict[str, Any]) -> bool:
    """保存回滚点"""
    _ensure_config_dir()
    try:
        with open(ROLLBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except IOError:
        return False


def _load_rollback() -> Optional[Dict[str, Any]]:
    """加载回滚点"""
    if not os.path.isfile(ROLLBACK_FILE):
        return None
    try:
        with open(ROLLBACK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _validate_tunnel_name(name: str) -> Optional[str]:
    """验证隧道名称：只允许字母数字下划线横杠"""
    if not name or len(name) > 64:
        return "隧道名称无效：长度需在 1-64 之间"
    if not all(c.isalnum() or c in "_-" for c in name):
        return "隧道名称只能包含字母、数字、下划线和横杠"
    return None


def _check_sudo_available() -> bool:
    """检查是否有 sudo 权限（不实际执行 sudo）"""
    return shutil.which("sudo") is not None


class TunnelManagerTool(BaseTool):
    """隧道管理：启动、停止、重启、创建配置、断开连接、服务管理"""

    name = "tunnel_manager"
    description = """隧道管理工具。提供隧道控制、配置管理、连接控制、服务管理功能。

支持操作：
- start: 启动指定隧道。tunnel_name="cloudflared" 时启动 Cloudflare 快速隧道（与 Mac 客户端一致，供用户连接）
- stop: 停止指定隧道
- restart: 重启指定隧道
- create: 根据配置创建新隧道
- disconnect: 断开指定客户端连接
- service: 管理隧道相关系统服务（start/stop/restart）

cloudflared 隧道与 Mac 客户端、tunnel_monitor 使用相同配置（端口 8765）。"""
    category = ToolCategory.SYSTEM
    requires_confirmation = True  # 管理操作需要确认
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "stop", "restart", "create", "disconnect", "service", "rollback"],
                "description": "操作：start 启动 / stop 停止 / restart 重启 / create 创建 / disconnect 断开连接 / service 服务管理 / rollback 回滚到上一状态"
            },
            "tunnel_name": {
                "type": "string",
                "description": "隧道名称。start/stop/restart 时可用 cloudflared 表示 Cloudflare 快速隧道（与 Mac 客户端一致）"
            },
            "client_id": {
                "type": "string",
                "description": " disconnect 时指定要断开的客户端 ID"
            },
            "config": {
                "type": "object",
                "description": "create 时的隧道配置：type(ssh/openvpn/wireguard)、host、port、extra 等",
                "properties": {
                    "type": {"type": "string", "description": "隧道类型"},
                    "host": {"type": "string", "description": "主机地址"},
                    "port": {"type": "integer", "description": "端口"},
                    "extra": {"type": "object", "description": "额外配置"}
                }
            },
            "service_action": {
                "type": "string",
                "enum": ["start", "stop", "restart", "status"],
                "description": "service 操作时：start/stop/restart/status"
            },
            "service_name": {
                "type": "string",
                "description": "服务名称，如 com.user.tunnel"
            },
            "confirm": {
                "type": "boolean",
                "description": "是否确认执行（危险操作需确认）",
                "default": False
            }
        },
        "required": ["action"]
    }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        if action not in ("start", "stop", "restart", "create", "disconnect", "service", "rollback"):
            return ToolResult(success=False, error=f"无效操作: {action}")

        if action == "rollback":
            return await self._rollback()
        if action == "start":
            return await self._start_tunnel(kwargs.get("tunnel_name"))
        elif action == "stop":
            return await self._stop_tunnel(kwargs.get("tunnel_name"))
        elif action == "restart":
            return await self._restart_tunnel(kwargs.get("tunnel_name"))
        elif action == "create":
            return await self._create_tunnel(kwargs.get("config", {}))
        elif action == "disconnect":
            return await self._disconnect_client(
                kwargs.get("tunnel_name"),
                kwargs.get("client_id")
            )
        elif action == "service":
            return await self._service_manage(
                kwargs.get("service_action"),
                kwargs.get("service_name")
            )
        return ToolResult(success=False, error="未知操作")

    def _run_cmd(self, cmd: str, timeout: int = 30, use_sudo: bool = False) -> tuple[int, str, str]:
        """同步执行命令（在 asyncio 中 run_in_executor）"""
        import subprocess
        if use_sudo and _check_sudo_available():
            cmd = f"sudo {cmd}"
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "", "执行超时"
        except Exception as e:
            return -1, "", str(e)

    async def _run_cmd_async(self, cmd: str, timeout: int = 30, use_sudo: bool = False) -> tuple[int, str, str]:
        """异步执行命令"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._run_cmd(cmd, timeout, use_sudo)
        )

    async def _start_cloudflared(self) -> ToolResult:
        """启动 Cloudflare 快速隧道（使用 launchd 持久运行，避免 Agent 子进程退出时被终止）"""
        cf = get_cloudflared_path()
        if not cf:
            return ToolResult(success=False, error="未找到 cloudflared，请安装: brew install cloudflared 或下载到 ~/bin/")
        log_path = os.path.expanduser("~/cloudflared.log")
        cmd = get_cloudflared_restart_command()
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        await asyncio.sleep(3)  # 等待 launchd 启动 cloudflared
        if proc.returncode != 0 and stderr:
            return ToolResult(
                success=False,
                error=f"launchd 加载失败: {stderr.decode().strip()}"
            )
        return ToolResult(
            success=True,
            data={
                "message": "Cloudflare 隧道已通过 launchd 启动（持久运行），公网链接可从 http://127.0.0.1:4040/api/tunnels 获取",
                "tunnel_name": "cloudflared",
                "log_path": log_path
            }
        )

    async def _stop_cloudflared(self) -> ToolResult:
        """停止 Cloudflare 隧道（unload launchd + pkill）"""
        plist_path = os.path.expanduser("~/Library/LaunchAgents/com.macagent.cloudflared.plist")
        proc = await asyncio.create_subprocess_shell(
            f'launchctl unload "{plist_path}" 2>/dev/null; pkill -f cloudflared 2>/dev/null; true',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return ToolResult(
            success=True,
            data={"message": "Cloudflare 隧道已停止", "tunnel_name": "cloudflared"}
        )

    async def _start_tunnel(self, tunnel_name: Optional[str]) -> ToolResult:
        """启动指定隧道"""
        if not tunnel_name:
            return ToolResult(success=False, error="需要提供 tunnel_name")
        if tunnel_name == "cloudflared":
            return await self._start_cloudflared()
        err = _validate_tunnel_name(tunnel_name)
        if err:
            return ToolResult(success=False, error=err)

        state = _load_state()
        tunnel = state.get("tunnels", {}).get(tunnel_name)
        if not tunnel:
            return ToolResult(
                success=False,
                error=f"隧道 '{tunnel_name}' 未配置。请先使用 create 创建隧道配置。"
            )

        # 保存回滚点
        _save_rollback(state)

        t_type = tunnel.get("type", "ssh")
        if t_type == "ssh":
            host = tunnel.get("host", "")
            port = tunnel.get("port", 22)
            if not host:
                return ToolResult(success=False, error="隧道配置缺少 host")
            cmd = f"ssh -f -N -D 1080 -p {port} {host}"
            code, out, err = await self._run_cmd_async(cmd, timeout=15)
        else:
            # 通用：通过 launchctl 或 openvpn/wg 命令
            svc = tunnel.get("service_name") or f"tunnel.{tunnel_name}"
            code, out, err = await self._run_cmd_async(
                f"launchctl load ~/Library/LaunchAgents/{svc}.plist 2>/dev/null || true",
                use_sudo=False
            )

        if code == 0 or "already loaded" in (out + err).lower():
            state["tunnels"][tunnel_name]["status"] = "running"
            _save_state(state)
            return ToolResult(
                success=True,
                data={"message": f"隧道 '{tunnel_name}' 已启动", "tunnel_name": tunnel_name}
            )
        return ToolResult(success=False, error=f"启动失败: {err or out}")

    async def _stop_tunnel(self, tunnel_name: Optional[str]) -> ToolResult:
        """停止指定隧道"""
        if not tunnel_name:
            return ToolResult(success=False, error="需要提供 tunnel_name")
        if tunnel_name == "cloudflared":
            return await self._stop_cloudflared()
        err = _validate_tunnel_name(tunnel_name)
        if err:
            return ToolResult(success=False, error=err)

        state = _load_state()
        _save_rollback(state)
        tunnel = state.get("tunnels", {}).get(tunnel_name)

        if tunnel:
            svc = tunnel.get("service_name") or f"tunnel.{tunnel_name}"
            await self._run_cmd_async(
                f"launchctl unload ~/Library/LaunchAgents/{svc}.plist 2>/dev/null; pkill -f '{tunnel_name}' 2>/dev/null; true"
            )
            state["tunnels"][tunnel_name]["status"] = "stopped"
            _save_state(state)

        return ToolResult(
            success=True,
            data={"message": f"隧道 '{tunnel_name}' 已停止", "tunnel_name": tunnel_name}
        )

    async def _restart_tunnel(self, tunnel_name: Optional[str]) -> ToolResult:
        """重启指定隧道"""
        if not tunnel_name:
            return ToolResult(success=False, error="需要提供 tunnel_name")
        stop_result = await self._stop_tunnel(tunnel_name)
        if not stop_result.success:
            return stop_result
        await asyncio.sleep(0.5)
        start_result = await self._start_tunnel(tunnel_name)
        if start_result.success:
            return ToolResult(
                success=True,
                data={"message": f"隧道 '{tunnel_name}' 已重启", "tunnel_name": tunnel_name}
            )
        return start_result

    async def _create_tunnel(self, config: Dict[str, Any]) -> ToolResult:
        """根据配置创建新隧道"""
        if not isinstance(config, dict):
            return ToolResult(success=False, error="config 必须为对象")

        t_type = config.get("type") or "ssh"
        name = config.get("name") or config.get("tunnel_name")
        if not name:
            return ToolResult(success=False, error="config 需包含 name 或 tunnel_name")
        err = _validate_tunnel_name(str(name))
        if err:
            return ToolResult(success=False, error=err)

        state = _load_state()
        _save_rollback(state)
        state.setdefault("tunnels", {})[str(name)] = {
            "type": t_type,
            "host": config.get("host", ""),
            "port": config.get("port", 22 if t_type == "ssh" else 1194),
            "extra": config.get("extra", {}),
            "status": "created",
        }
        if not _save_state(state):
            return ToolResult(success=False, error="保存配置失败")
        return ToolResult(
            success=True,
            data={"message": f"隧道 '{name}' 已创建", "tunnel_name": str(name)}
        )

    async def _disconnect_client(
        self, tunnel_name: Optional[str], client_id: Optional[str]
    ) -> ToolResult:
        """断开特定客户端连接"""
        if not tunnel_name and not client_id:
            return ToolResult(success=False, error="需要提供 tunnel_name 或 client_id")
        if tunnel_name:
            err = _validate_tunnel_name(tunnel_name)
            if err:
                return ToolResult(success=False, error=err)

        state = _load_state()
        conns = state.get("connections", {})
        key = client_id or tunnel_name
        if key and key in conns:
            _save_rollback(state)
            del conns[key]
            _save_state(state)
            return ToolResult(
                success=True,
                data={"message": f"已断开连接 '{key}'", "disconnected": key}
            )
        return ToolResult(
            success=True,
            data={"message": f"未找到连接 '{key}' 或已断开", "disconnected": None}
        )

    async def _service_manage(
        self, service_action: Optional[str], service_name: Optional[str]
    ) -> ToolResult:
        """管理隧道相关系统服务"""
        if not service_action:
            return ToolResult(success=False, error="需要提供 service_action")
        if not service_name:
            return ToolResult(success=False, error="需要提供 service_name")

        # 安全验证：服务名只允许安全字符
        safe = "".join(c for c in service_name if c.isalnum() or c in ".-_")
        if safe != service_name:
            return ToolResult(success=False, error="service_name 包含非法字符")

        use_sudo = service_action in ("start", "stop", "restart")
        if use_sudo and not _check_sudo_available():
            return ToolResult(
                success=False,
                error="需要 sudo 权限执行服务操作，但系统未找到 sudo"
            )

        if service_action == "status":
            cmd = f"launchctl list {service_name} 2>&1 || systemctl status {service_name} 2>&1 || true"
            use_sudo = False
        else:
            cmd = f"launchctl {service_action} {service_name} 2>&1 || systemctl {service_action} {service_name} 2>&1 || true"

        code, out, err = await self._run_cmd_async(cmd, use_sudo=use_sudo)
        return ToolResult(
            success=code == 0,
            data={"action": service_action, "service": service_name, "output": out or err}
        )

    async def _rollback(self) -> ToolResult:
        """回滚到上一操作前的状态"""
        prev = _load_rollback()
        if not prev:
            return ToolResult(
                success=False,
                error="无可用的回滚点，请先执行 start/stop/create/disconnect 等操作"
            )
        if not _save_state(prev):
            return ToolResult(success=False, error="回滚保存失败")
        return ToolResult(success=True, data={"message": "已回滚到上一状态"})
