"""
Cloudflare 隧道共享配置 - 与 Mac 客户端、tunnel_manager、tunnel_monitor 保持一致
三者共用同一套 cloudflared 隧道（用户客户端连接）
"""
import os
import shutil
from typing import Optional

# 与 Mac 客户端 TunnelManager 一致
BACKEND_PORT = 8765
CLOUDFLARED_METRICS_PORT = 4040

# 按优先级搜索 cloudflared 的路径（含用户自定义安装位置）
_CLOUDFLARED_SEARCH_PATHS = [
    "/opt/homebrew/bin/cloudflared",
    "/usr/local/bin/cloudflared",
    os.path.expanduser("~/bin/cloudflared"),
    os.path.expanduser("~/.local/bin/cloudflared"),
]


def get_cloudflared_path() -> Optional[str]:
    """获取 cloudflared 可执行路径（与 Mac 客户端一致，含 ~/bin）"""
    for path in _CLOUDFLARED_SEARCH_PATHS:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return shutil.which("cloudflared")


def get_cloudflared_restart_command() -> str:
    """生成 cloudflared 重启命令（使用 launchd 以持久运行，避免 Agent 子进程退出时被终止）"""
    cf = get_cloudflared_path()
    if cf:
        log_path = os.path.expanduser("~/cloudflared.log")
        plist_path = os.path.expanduser("~/Library/LaunchAgents/com.macagent.cloudflared.plist")
        # 只杀 quick tunnel（--url 参数），不影响 named tunnel（--config）
        return (
            f"pkill -f 'cloudflared tunnel --url' 2>/dev/null; sleep 2; "
            f"mkdir -p ~/Library/LaunchAgents; "
            f'cf="{cf}"; log="{log_path}"; plist="{plist_path}"; '
            f'cat > "$plist" << "PLIST_END"\n'
            f'<?xml version="1.0"?>\n'
            f'<plist version="1.0">\n'
            f'<dict>\n'
            f'  <key>Label</key><string>com.macagent.cloudflared</string>\n'
            f'  <key>ProgramArguments</key>\n'
            f'  <array>\n'
            f'    <string>{cf}</string>\n'
            f'    <string>tunnel</string>\n'
            f'    <string>--url</string>\n'
            f'    <string>http://localhost:{BACKEND_PORT}</string>\n'
            f'    <string>--metrics</string>\n'
            f'    <string>127.0.0.1:{CLOUDFLARED_METRICS_PORT}</string>\n'
            f'  </array>\n'
            f'  <key>RunAtLoad</key><true/>\n'
            f'  <key>KeepAlive</key><true/>\n'
            f'  <key>StandardOutPath</key><string>{log_path}</string>\n'
            f'  <key>StandardErrorPath</key><string>{log_path}</string>\n'
            f'  <key>EnvironmentVariables</key>\n'
            f'  <dict><key>PATH</key><string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string></dict>\n'
            f'</dict>\n'
            f'</plist>\n'
            f'PLIST_END\n'
            f'launchctl unload "$plist" 2>/dev/null; launchctl load "$plist"'
        )
    return "pkill -f 'cloudflared tunnel --url' 2>/dev/null; sleep 2; nohup cloudflared tunnel --url http://localhost:8765 --metrics 127.0.0.1:4040 >> ~/cloudflared.log 2>&1 &"


# LaunchAgent 标识，供 tunnel_manager 使用
CLOUDFLARED_LAUNCHD_LABEL = "com.macagent.cloudflared"
