"""
Cloudflare Tunnel 生命周期管理服务
负责隧道的自动启动、健康监控、断线重启、指数退避、邮件通知、局域网回退
"""
import asyncio
import json
import logging
import os
import platform
import smtplib
import socket
import ssl
import threading
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from tools.cloudflared_utils import (
    BACKEND_PORT,
    CLOUDFLARED_METRICS_PORT,
    get_cloudflared_path,
    get_cloudflared_restart_command,
)

logger = logging.getLogger(__name__)

# ── 退避策略常量 ─────────────────────────────────
BACKOFF_INITIAL = 30          # 首次退避 30s
BACKOFF_MULTIPLIER = 2        # 指数倍增
BACKOFF_MAX = 1800            # 最大退避 30 分钟
BACKOFF_RESET_AFTER = 300     # 连续正常 5 分钟后重置退避计数
HEALTH_CHECK_INTERVAL = 30    # 健康检查间隔 30s
MAX_FAILURES_BEFORE_LAN = 5   # 连续失败 5 次后切换仅局域网模式


class TunnelLifecycleService:
    """Cloudflare Tunnel 全生命周期管理"""

    _instance: Optional["TunnelLifecycleService"] = None
    _instance_lock = threading.Lock()

    def __init__(self):
        # 状态
        self.tunnel_url: str = ""
        self.is_running: bool = False
        self.is_lan_only: bool = False       # 切换到仅局域网模式
        self.last_healthy_at: float = 0
        self.started_at: float = 0

        # 退避
        self.consecutive_failures: int = 0
        self.current_backoff: float = BACKOFF_INITIAL
        self.backoff_until: float = 0        # 退避截止时间戳
        self.total_restarts: int = 0

        # 自动启动标记（由 API 或 config 控制）
        self._auto_start_enabled: bool = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._startup_task: Optional[asyncio.Task] = None

        # 最近错误日志（保留最近 20 条）
        self._recent_events: list[Dict[str, Any]] = []

    @classmethod
    def get_instance(cls) -> "TunnelLifecycleService":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 公共 API ────────────────────────────────
    def get_status(self) -> Dict[str, Any]:
        """返回当前 tunnel 状态摘要"""
        lan_info = self._get_lan_info()
        return {
            "is_running": self.is_running,
            "tunnel_url": self.tunnel_url,
            "is_lan_only": self.is_lan_only,
            "auto_start_enabled": self._auto_start_enabled,
            "consecutive_failures": self.consecutive_failures,
            "total_restarts": self.total_restarts,
            "current_backoff_seconds": self.current_backoff if self.consecutive_failures > 0 else 0,
            "backoff_until": datetime.fromtimestamp(self.backoff_until).isoformat() if self.backoff_until > time.time() else None,
            "last_healthy_at": datetime.fromtimestamp(self.last_healthy_at).isoformat() if self.last_healthy_at else None,
            "started_at": datetime.fromtimestamp(self.started_at).isoformat() if self.started_at else None,
            "lan_info": lan_info,
            "recent_events": self._recent_events[-20:],
        }

    async def start_tunnel(self) -> Dict[str, Any]:
        """启动 cloudflared tunnel"""
        if self.is_running and self.tunnel_url:
            return {"ok": True, "message": "Tunnel 已在运行中", "url": self.tunnel_url}

        cf_path = get_cloudflared_path()
        if not cf_path:
            self._add_event("error", "cloudflared 未安装，无法启动隧道")
            return {"ok": False, "error": "cloudflared 未安装，请执行 brew install cloudflared"}

        self._add_event("info", "正在启动 Cloudflare Tunnel...")
        cmd = get_cloudflared_restart_command()
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode and proc.returncode != 0 and stderr:
                err_msg = stderr.decode().strip()[:300]
                self._add_event("error", f"启动失败: {err_msg}")
                return {"ok": False, "error": err_msg}
        except asyncio.TimeoutError:
            self._add_event("warning", "启动命令超时，继续等待 tunnel 注册...")
        except Exception as e:
            self._add_event("error", f"启动异常: {e}")
            return {"ok": False, "error": str(e)}

        # 等待 tunnel 注册（最多 20 秒）
        url = await self._wait_for_tunnel_url(max_wait=20)
        if url:
            self.tunnel_url = url
            self.is_running = True
            self.is_lan_only = False
            self.started_at = time.time()
            self.last_healthy_at = time.time()
            self.consecutive_failures = 0
            self.current_backoff = BACKOFF_INITIAL
            self._add_event("info", f"Tunnel 已启动: {url}")

            # 发送邮件通知
            asyncio.create_task(self._notify_new_url(url))

            return {"ok": True, "url": url}
        else:
            self._add_event("warning", "Tunnel 进程已启动，但尚未获取到 URL（将继续监控）")
            self.is_running = True
            self.started_at = time.time()
            return {"ok": True, "url": "", "message": "进程已启动，等待 URL 注册"}

    async def stop_tunnel(self) -> Dict[str, Any]:
        """停止 cloudflared tunnel"""
        self._add_event("info", "正在停止 Tunnel...")
        plist_path = os.path.expanduser("~/Library/LaunchAgents/com.macagent.cloudflared.plist")
        cmd = f'launchctl unload "{plist_path}" 2>/dev/null; pkill -f cloudflared 2>/dev/null; true'
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
        except Exception as e:
            logger.warning(f"Stop tunnel error: {e}")

        self.is_running = False
        self.tunnel_url = ""
        self.is_lan_only = False
        self.backoff_until = 0
        self._add_event("info", "Tunnel 已停止")
        return {"ok": True}

    async def restart_tunnel(self) -> Dict[str, Any]:
        """重启 tunnel（停止后再启动）"""
        await self.stop_tunnel()
        await asyncio.sleep(2)
        return await self.start_tunnel()

    def set_auto_start(self, enabled: bool):
        """设置是否随后端自动启动 tunnel"""
        self._auto_start_enabled = enabled
        self._save_config()
        self._add_event("info", f"自动启动已{'开启' if enabled else '关闭'}")

    # ── 后台任务管理 ──────────────────────────────
    async def initialize(self):
        """在 lifespan 中调用：加载配置、按需自动启动、启动监控循环"""
        self._load_config()
        if self._auto_start_enabled:
            self._add_event("info", "检测到自动启动配置，将异步启动 Tunnel...")
            self._startup_task = asyncio.create_task(self._auto_start_tunnel())

        # 无论是否自动启动，都启动监控循环（检测外部启动的 tunnel）
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("TunnelLifecycleService initialized (auto_start=%s)", self._auto_start_enabled)

    async def shutdown(self):
        """在 lifespan 退出时调用"""
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None
        if self._startup_task:
            self._startup_task.cancel()
            self._startup_task = None

    # ── 内部：自动启动 ──────────────────────────────
    async def _auto_start_tunnel(self):
        """异步自动启动 tunnel（不阻塞后端启动）"""
        await asyncio.sleep(3)  # 让后端先完成初始化
        try:
            # 先检测是否已有外部 tunnel 在运行
            url = await self._fetch_tunnel_url()
            if url:
                self.tunnel_url = url
                self.is_running = True
                self.last_healthy_at = time.time()
                self.started_at = time.time()
                self._add_event("info", f"检测到已运行的 Tunnel: {url}")
                return

            result = await self.start_tunnel()
            if not result.get("ok"):
                self._add_event("error", f"自动启动失败: {result.get('error', '未知错误')}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._add_event("error", f"自动启动异常: {e}")
            logger.error("Auto start tunnel error: %s", e, exc_info=True)

    # ── 内部：监控循环 ──────────────────────────────
    async def _monitor_loop(self):
        """健康监控主循环"""
        while True:
            try:
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)
                await self._health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Tunnel monitor loop error: %s", e, exc_info=True)
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)

    async def _health_check(self):
        """单次健康检查"""
        url = await self._fetch_tunnel_url()

        if url:
            # ── 健康 ──
            old_url = self.tunnel_url
            self.tunnel_url = url
            self.is_running = True
            self.last_healthy_at = time.time()

            # 连续正常 > BACKOFF_RESET_AFTER → 重置退避
            if self.consecutive_failures > 0:
                self.consecutive_failures = 0
                self.current_backoff = BACKOFF_INITIAL
                self.is_lan_only = False
                self._add_event("info", "Tunnel 恢复正常，退避计数已重置")

            # URL 变化 → 通知
            if old_url and old_url != url:
                self._add_event("info", f"Tunnel URL 已变更: {url}")
                asyncio.create_task(self._notify_new_url(url))

            if not old_url and url:
                self.started_at = self.started_at or time.time()

        else:
            # ── 不健康 ──
            if not self.is_running and not self._auto_start_enabled:
                # 用户未启用自动启动且 tunnel 不在运行，仅检测
                return

            self.consecutive_failures += 1
            now = time.time()

            # 退避中则跳过
            if now < self.backoff_until:
                remaining = int(self.backoff_until - now)
                logger.debug("Tunnel backoff: %ds remaining", remaining)
                return

            # 达到阈值 → 仅局域网模式
            if self.consecutive_failures >= MAX_FAILURES_BEFORE_LAN:
                if not self.is_lan_only:
                    self.is_lan_only = True
                    self._add_event("warning",
                                    f"连续 {self.consecutive_failures} 次失败，已切换为仅局域网模式。"
                                    f"将在 {int(self.current_backoff)}s 后再次尝试。")
                    asyncio.create_task(self._notify_lan_fallback())

            # 尝试重启
            self._add_event("info", f"检测到 Tunnel 异常（第 {self.consecutive_failures} 次），尝试重启...")
            result = await self.start_tunnel()
            if result.get("ok") and result.get("url"):
                self._add_event("info", f"重启成功: {result['url']}")
                self.consecutive_failures = 0
                self.current_backoff = BACKOFF_INITIAL
                self.is_lan_only = False
            else:
                # 重启失败 → 设置退避
                self.total_restarts += 1
                self.backoff_until = now + self.current_backoff
                self._add_event("warning",
                                f"重启失败，退避 {int(self.current_backoff)}s 后重试")
                # 指数增长
                self.current_backoff = min(self.current_backoff * BACKOFF_MULTIPLIER, BACKOFF_MAX)

    # ── 内部：Tunnel URL 获取 ──────────────────────
    async def _fetch_tunnel_url(self) -> Optional[str]:
        """从 cloudflared Prometheus metrics 中解析 tunnel URL"""
        try:
            import aiohttp
        except ImportError:
            return await self._fetch_tunnel_url_curl()

        try:
            timeout = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"http://127.0.0.1:{CLOUDFLARED_METRICS_PORT}/metrics"
                ) as resp:
                    if resp.status != 200:
                        return None
                    text = await resp.text()
                    return self._parse_tunnel_url_from_metrics(text)
        except Exception:
            return None

    async def _fetch_tunnel_url_curl(self) -> Optional[str]:
        """无 aiohttp 时用 curl 获取 metrics"""
        try:
            proc = await asyncio.create_subprocess_shell(
                f"curl -s --connect-timeout 2 http://127.0.0.1:{CLOUDFLARED_METRICS_PORT}/metrics",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            if proc.returncode == 0 and stdout:
                return self._parse_tunnel_url_from_metrics(stdout.decode())
        except Exception:
            pass
        return None

    @staticmethod
    def _parse_tunnel_url_from_metrics(metrics_text: str) -> Optional[str]:
        """从 Prometheus metrics 文本中提取 trycloudflare.com URL"""
        import re
        # 匹配: cloudflared_tunnel_user_hostnames_counts{userHostname="https://xxx.trycloudflare.com"} 1
        pattern = r'cloudflared_tunnel_user_hostnames_counts\{userHostname="(https://[^"]*trycloudflare\.com[^"]*)"\}'
        match = re.search(pattern, metrics_text)
        if match:
            return match.group(1)
        return None

    async def _wait_for_tunnel_url(self, max_wait: float = 20) -> Optional[str]:
        """启动后轮询等待 tunnel URL"""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            url = await self._fetch_tunnel_url()
            if url:
                return url
            await asyncio.sleep(2)
        return None

    # ── 内部：邮件通知 ──────────────────────────────
    async def _notify_new_url(self, url: str):
        """tunnel 新 URL 邮件通知（仅在用户配置了 SMTP 时发送）"""
        try:
            from config.smtp_config import get_smtp_config
            server, port, user, password = get_smtp_config()
            if not all([server, user, password]):
                logger.debug("SMTP 未配置，跳过邮件通知")
                return

            subject = "🔗 MacAgent Tunnel 地址已更新"
            lan_info = self._get_lan_info()
            lan_addr = lan_info.get("ws_url", "N/A") if lan_info else "N/A"

            text_body = (
                f"MacAgent Cloudflare Tunnel 地址已更新！\n\n"
                f"新的隧道地址: {url}\n"
                f"WebSocket 地址: wss://{url.replace('https://', '')}/ws\n"
                f"局域网备用: {lan_addr}\n"
                f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"请在 iOS App 中更新连接地址，或扫描 Mac 端的二维码。"
            )

            html_body = f"""
            <html><body style="font-family: -apple-system, sans-serif; padding: 20px;">
            <h2 style="color: #0066cc;">🔗 MacAgent Tunnel 地址已更新</h2>
            <table style="border-collapse: collapse; margin: 16px 0;">
              <tr><td style="padding: 8px; color: #666;">隧道地址</td>
                  <td style="padding: 8px;"><a href="{url}">{url}</a></td></tr>
              <tr><td style="padding: 8px; color: #666;">WebSocket</td>
                  <td style="padding: 8px; font-family: monospace;">wss://{url.replace('https://', '')}/ws</td></tr>
              <tr><td style="padding: 8px; color: #666;">局域网备用</td>
                  <td style="padding: 8px; font-family: monospace;">{lan_addr}</td></tr>
              <tr><td style="padding: 8px; color: #666;">更新时间</td>
                  <td style="padding: 8px;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
            </table>
            <p style="color: #888; font-size: 13px;">请在 iOS App 中更新连接地址，或扫描 Mac 端的二维码。</p>
            </body></html>
            """

            await self._send_email(
                server=server, port=port, user=user, password=password,
                recipient=user,  # 发给自己
                subject=subject, text_body=text_body, html_body=html_body,
            )
            self._add_event("info", f"新地址邮件通知已发送到 {user}")

        except Exception as e:
            logger.warning("邮件通知发送失败: %s", e)
            self._add_event("warning", f"邮件通知发送失败: {e}")

    async def _notify_lan_fallback(self):
        """通知用户已切换为仅局域网模式"""
        try:
            from config.smtp_config import get_smtp_config
            server, port, user, password = get_smtp_config()
            if not all([server, user, password]):
                return

            lan_info = self._get_lan_info()
            lan_addr = lan_info.get("ws_url", "N/A") if lan_info else "N/A"

            text_body = (
                f"⚠️ MacAgent Cloudflare Tunnel 连续 {self.consecutive_failures} 次连接失败，\n"
                f"已切换为仅局域网模式。\n\n"
                f"局域网地址: {lan_addr}\n"
                f"下次重试: {datetime.fromtimestamp(self.backoff_until).strftime('%H:%M:%S')}\n\n"
                f"可能原因：IP 被 Cloudflare 暂时封禁、网络波动等。系统将自动重试。"
            )

            await self._send_email(
                server=server, port=port, user=user, password=password,
                recipient=user,
                subject="⚠️ MacAgent Tunnel 切换为仅局域网模式",
                text_body=text_body, html_body=None,
            )
        except Exception as e:
            logger.warning("LAN fallback notify failed: %s", e)

    async def _send_email(
        self,
        server: str, port: int, user: str, password: str,
        recipient: str, subject: str, text_body: str, html_body: Optional[str] = None,
    ):
        """发送邮件（同步 SMTP 包裹在线程中避免阻塞）"""
        def _sync_send():
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = user
            msg["To"] = recipient
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
            if html_body:
                msg.attach(MIMEText(html_body, "html", "utf-8"))

            ctx = ssl.create_default_context()
            if port == 465:
                with smtplib.SMTP_SSL(server, port, context=ctx, timeout=10) as srv:
                    srv.login(user, password)
                    srv.sendmail(user, [recipient], msg.as_string())
            else:
                with smtplib.SMTP(server, port, timeout=10) as srv:
                    srv.starttls(context=ctx)
                    srv.login(user, password)
                    srv.sendmail(user, [recipient], msg.as_string())

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _sync_send)

    # ── 内部：局域网信息 ──────────────────────────
    def _get_lan_info(self) -> Dict[str, str]:
        """获取本机局域网连接信息"""
        ip = self._get_local_ip()
        return {
            "ip": ip,
            "port": str(BACKEND_PORT),
            "http_url": f"http://{ip}:{BACKEND_PORT}",
            "ws_url": f"ws://{ip}:{BACKEND_PORT}/ws",
            "hostname": platform.node(),
        }

    @staticmethod
    def _get_local_ip() -> str:
        """获取本地局域网 IP（优先 192.168.x / 10.x / 172.16-31.x 私有网段）"""
        import subprocess
        try:
            result = subprocess.run(
                ["ifconfig", "-a"], capture_output=True, text=True, timeout=3
            )
            import re
            ips = re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", result.stdout)
            # 过滤：优先私有网段，排除 127.x 和 169.254.x
            private_ips = []
            for ip in ips:
                if ip.startswith("127.") or ip.startswith("169.254."):
                    continue
                parts = ip.split(".")
                first = int(parts[0])
                second = int(parts[1])
                # 私有网段判断
                if first == 192 and second == 168:
                    private_ips.insert(0, ip)  # 最高优先
                elif first == 10:
                    private_ips.insert(0, ip)
                elif first == 172 and 16 <= second <= 31:
                    private_ips.insert(0, ip)
                else:
                    private_ips.append(ip)  # 非私有，作为备选
            if private_ips:
                return private_ips[0]
        except Exception:
            pass
        # 回退方法
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    # ── 内部：事件日志 ──────────────────────────────
    def _add_event(self, level: str, message: str):
        """添加事件日志"""
        entry = {
            "time": datetime.now().isoformat(),
            "level": level,
            "message": message,
        }
        self._recent_events.append(entry)
        if len(self._recent_events) > 50:
            self._recent_events = self._recent_events[-50:]

        log_fn = getattr(logger, level, logger.info)
        log_fn("[TunnelLifecycle] %s", message)

    # ── 内部：配置持久化 ──────────────────────────
    def _load_config(self):
        """从文件加载 tunnel 配置"""
        path = self._config_path()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self._auto_start_enabled = cfg.get("auto_start", False)
            except Exception:
                pass

    def _save_config(self):
        """保存 tunnel 配置"""
        path = self._config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"auto_start": self._auto_start_enabled}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Save tunnel config failed: %s", e)

    @staticmethod
    def _config_path() -> str:
        from paths import DATA_DIR
        return os.path.join(DATA_DIR, "tunnel_config.json")


def get_tunnel_lifecycle() -> TunnelLifecycleService:
    """获取全局 TunnelLifecycleService 单例"""
    return TunnelLifecycleService.get_instance()
