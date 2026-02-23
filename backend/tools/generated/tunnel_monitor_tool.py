"""
Tunnel Monitor Tool - 隧道监控工具
包装用户目录下的 tunnel_monitor_v3.sh，供 Agent 调用
若脚本不存在，引导用户或通过升级流程创建
"""
import asyncio
import os
from tools.base import BaseTool, ToolResult, ToolCategory


# 默认脚本路径（用户目录）
DEFAULT_SCRIPT = os.path.expanduser("~/tunnel_monitor_v3.sh")
START_SCRIPT = os.path.expanduser("~/start_tunnel_monitor.sh")
LOG_FILE = os.path.expanduser("~/tunnel_monitor_v3.log")
URL_FILE = os.path.expanduser("~/tunnel_url_v3.txt")
PID_FILE = os.path.expanduser("~/tunnel_v3.pid")


class TunnelMonitorTool(BaseTool):
    """隧道监控：启动、停止、查看状态、获取 URL"""

    name = "tunnel_monitor"
    description = """隧道监控工具。监控 tunnel 连接状态，中断后自动重启并发送邮件通知。

支持操作：
- start: 启动监控
- stop: 停止监控  
- status: 查看运行状态
- url: 获取当前隧道 URL
- log: 查看最近日志"""
    category = ToolCategory.SYSTEM
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "stop", "status", "url", "log"],
                "description": "操作：start 启动 / stop 停止 / status 状态 / url 获取链接 / log 查看日志"
            }
        },
        "required": ["action"]
    }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "status")
        if action not in ("start", "stop", "status", "url", "log"):
            return ToolResult(success=False, error=f"无效操作: {action}")

        if action == "start":
            return await self._start()
        elif action == "stop":
            return await self._stop()
        elif action == "status":
            return await self._status()
        elif action == "url":
            return await self._get_url()
        elif action == "log":
            return await self._get_log()
        return ToolResult(success=False, error="未知操作")

    async def _run_cmd(self, cmd: str, timeout: int = 30) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return -1, "", "执行超时"
        return proc.returncode, stdout.decode().strip(), stderr.decode().strip()

    async def _start(self) -> ToolResult:
        script = START_SCRIPT if os.path.isfile(START_SCRIPT) else DEFAULT_SCRIPT
        if not os.path.isfile(script):
            return ToolResult(
                success=False,
                error=f"监控脚本不存在: {script}。请通过 request_tool_upgrade 创建隧道监控工具，或手动创建脚本。"
            )
        if not os.access(script, os.X_OK):
            return ToolResult(success=False, error=f"脚本无执行权限: {script}")

        code, out, err = await self._run_cmd(
            f"nohup {script} > /dev/null 2>&1 &",
            timeout=5
        )
        await asyncio.sleep(0.5)
        status = await self._status_internal()
        if status.get("running"):
            return ToolResult(
                success=True,
                data={"message": "隧道监控已启动", "pid": status.get("pid"), "log": LOG_FILE}
            )
        return ToolResult(success=False, error=f"启动失败: {err or out}")

    async def _stop(self) -> ToolResult:
        script = DEFAULT_SCRIPT
        if not os.path.isfile(script):
            return ToolResult(success=False, error=f"监控脚本不存在: {script}")

        # 通过 kill 监控脚本进程停止
        code, out, err = await self._run_cmd(
            f"pkill -f tunnel_monitor_v3.sh 2>/dev/null; sleep 0.5; echo done",
            timeout=10
        )
        return ToolResult(
            success=True,
            data={"message": "已发送停止信号，监控将在检测周期内退出"}
        )

    async def _status_internal(self) -> dict:
        result = {"running": False, "pid": None, "script": DEFAULT_SCRIPT}
        if not os.path.isfile(DEFAULT_SCRIPT):
            result["error"] = "脚本不存在"
            return result
        code, out, _ = await self._run_cmd(
            f"pgrep -f tunnel_monitor_v3.sh || true",
            timeout=5
        )
        pids = [p.strip() for p in out.splitlines() if p.strip().isdigit()]
        result["running"] = len(pids) > 0
        result["pid"] = int(pids[0]) if pids else None
        return result

    async def _status(self) -> ToolResult:
        s = await self._status_internal()
        if s.get("error"):
            return ToolResult(success=False, error=s["error"])
        return ToolResult(
            success=True,
            data={
                "running": s["running"],
                "pid": s["pid"],
                "script": s["script"],
                "log_file": LOG_FILE,
                "url_file": URL_FILE
            }
        )

    async def _get_url(self) -> ToolResult:
        if not os.path.isfile(URL_FILE):
            return ToolResult(
                success=True,
                data={"url": None, "message": "URL 文件不存在，隧道可能尚未生成链接"}
            )
        try:
            with open(URL_FILE, "r", encoding="utf-8") as f:
                url = f.read().strip()
            return ToolResult(success=True, data={"url": url or None})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _get_log(self, lines: int = 30) -> ToolResult:
        if not os.path.isfile(LOG_FILE):
            return ToolResult(success=True, data={"log": "", "message": "日志文件不存在"})
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            tail = "\n".join(content.strip().split("\n")[-lines:])
            return ToolResult(success=True, data={"log": tail, "file": LOG_FILE})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
