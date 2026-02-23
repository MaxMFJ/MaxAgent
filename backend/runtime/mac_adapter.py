"""
MacRuntimeAdapter - macOS 运行时适配器
使用 AppleScript、pbcopy/pbpaste、screencapture、cliclick 等实现
"""

import asyncio
import logging
import platform
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from .base import (
    RuntimeAdapter, ScriptResult,
    CAP_APP_CONTROL, CAP_CLIPBOARD, CAP_SCREENSHOT, CAP_GUI_INPUT,
    CAP_NOTIFICATION, CAP_SCRIPT, CAP_BROWSER, CAP_WINDOW_INFO,
)

logger = logging.getLogger(__name__)

# System Events 进程名映射：显示名/中文名 -> 实际进程名
# macOS 中 "tell process" 需要使用进程名，不是应用显示名
PROCESS_NAME_MAP = {
    "微信": "WeChat",
    "WeChat": "WeChat",
    "钉钉": "DingTalk",
    "DingTalk": "DingTalk",
    "飞书": "Lark",
    "Lark": "Lark",
}


class MacRuntimeAdapter(RuntimeAdapter):
    """macOS 平台运行时适配器"""
    
    @property
    def platform(self) -> str:
        return "mac"
    
    @property
    def is_available(self) -> bool:
        return platform.system() == "Darwin"
    
    def capabilities(self):
        return {
            CAP_APP_CONTROL, CAP_CLIPBOARD, CAP_SCREENSHOT, CAP_GUI_INPUT,
            CAP_NOTIFICATION, CAP_SCRIPT, CAP_BROWSER, CAP_WINDOW_INFO,
        }
    
    async def _run_applescript(self, script: str) -> ScriptResult:
        """执行 AppleScript"""
        try:
            process = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            out = stdout.decode().strip()
            err = stderr.decode().strip()
            return ScriptResult(success=process.returncode == 0, output=out, error=err)
        except Exception as e:
            return ScriptResult(success=False, error=str(e))
    
    # ---------- 应用控制 ----------
    
    async def open_app(
        self,
        app_name: Optional[str] = None,
        app_path: Optional[str] = None,
        url: Optional[str] = None,
        file_path: Optional[str] = None
    ) -> Tuple[bool, str]:
        cmd = ["open"]
        if url:
            cmd.append(url)
        elif file_path:
            cmd.extend([file_path])
            if app_name:
                cmd.extend(["-a", app_name])
        elif app_path:
            cmd.append(app_path)
        elif app_name:
            cmd.extend(["-a", app_name])
        else:
            return False, "需要指定 app_name、app_path、url 或 file 之一"
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                return False, stderr.decode().strip()
            return True, ""
        except Exception as e:
            return False, str(e)
    
    async def close_app(self, app_name: str) -> Tuple[bool, str]:
        script = f'tell application "{app_name}" to quit'
        r = await self._run_applescript(script)
        return r.success, r.error
    
    async def activate_app(self, app_name: str) -> Tuple[bool, str]:
        script = f'tell application "{app_name}" to activate'
        r = await self._run_applescript(script)
        return r.success, r.error
    
    async def list_apps(self) -> Tuple[bool, List[str], str]:
        script = '''
        tell application "System Events"
            set appList to name of every process whose background only is false
        end tell
        return appList
        '''
        r = await self._run_applescript(script)
        if not r.success:
            return False, [], r.error
        apps = [a.strip() for a in r.output.split(",")]
        return True, apps, ""
    
    async def get_frontmost_app(self) -> Tuple[bool, str, str]:
        script = '''
        tell application "System Events"
            set frontApp to name of first process whose frontmost is true
        end tell
        return frontApp
        '''
        r = await self._run_applescript(script)
        return r.success, r.output.strip(), r.error
    
    async def hide_app(self, app_name: str) -> Tuple[bool, str]:
        script = f'''
        tell application "System Events"
            set visible of process "{app_name}" to false
        end tell
        '''
        r = await self._run_applescript(script)
        return r.success, r.error
    
    # ---------- 剪贴板 ----------
    
    async def clipboard_read(self) -> Tuple[bool, str, str]:
        try:
            process = await asyncio.create_subprocess_exec(
                "pbpaste",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                return False, "", stderr.decode()
            return True, stdout.decode("utf-8"), ""
        except Exception as e:
            return False, "", str(e)
    
    async def clipboard_write(self, content: str) -> Tuple[bool, str]:
        try:
            process = await asyncio.create_subprocess_exec(
                "pbcopy",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate(input=content.encode("utf-8"))
            if process.returncode != 0:
                return False, stderr.decode()
            return True, ""
        except Exception as e:
            return False, str(e)
    
    # ---------- 截图 ----------
    
    async def screenshot_full(self, path: str) -> Tuple[bool, str]:
        try:
            process = await asyncio.create_subprocess_exec(
                "screencapture", "-x", path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                return False, stderr.decode()
            return True, ""
        except Exception as e:
            return False, str(e)
    
    async def screenshot_region(
        self, path: str, x: int, y: int, width: int, height: int
    ) -> Tuple[bool, str]:
        try:
            region = f"{x},{y},{width},{height}"
            process = await asyncio.create_subprocess_exec(
                "screencapture", "-x", "-R", region, path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                return False, stderr.decode()
            return True, ""
        except Exception as e:
            return False, str(e)
    
    async def screenshot_interactive(self, path: str) -> Tuple[bool, str]:
        """交互式区域选择 (screencapture -i)"""
        try:
            process = await asyncio.create_subprocess_exec(
                "screencapture", "-x", "-i", path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                return False, stderr.decode() or "用户取消或失败"
            return True, ""
        except Exception as e:
            return False, str(e)
    
    async def screenshot_pick_window(self, path: str) -> Tuple[bool, str]:
        """交互式窗口选择 (screencapture -w)"""
        try:
            process = await asyncio.create_subprocess_exec(
                "screencapture", "-x", "-w", path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                return False, stderr.decode() or "用户取消或失败"
            return True, ""
        except Exception as e:
            return False, str(e)
    
    def _resolve_process_name(self, app_name: str) -> List[str]:
        """解析进程名：返回要尝试的进程名列表（含回退）"""
        names = [app_name.strip()]
        mapped = PROCESS_NAME_MAP.get(app_name.strip())
        if mapped and mapped not in names:
            names.insert(0, mapped)
        return names

    def _parse_window_bounds(self, output: str) -> Optional[Tuple[int, int, int, int]]:
        """解析 AppleScript 返回的 x,y,w,h 坐标"""
        output = output.strip()
        # 可能包含错误信息或多余字符，提取所有整数
        numbers = re.findall(r"-?\d+", output)
        if len(numbers) >= 4:
            try:
                return (
                    int(numbers[0]),
                    int(numbers[1]),
                    int(numbers[2]),
                    int(numbers[3]),
                )
            except ValueError:
                pass
        # 尝试按逗号分割
        parts = [p.strip() for p in output.split(",")]
        if len(parts) == 4:
            try:
                return int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
            except ValueError:
                pass
        logger.warning("screenshot_window 解析失败, output=%r", output)
        return None

    async def screenshot_window(self, app_name: str, path: str) -> Tuple[bool, str]:
        """使用 screencapture -R 区域截取应用窗口"""
        last_error = "无法获取窗口"
        for process_name in self._resolve_process_name(app_name):
            script = f'''
            tell application "System Events"
                tell process "{process_name}"
                    if (count of windows) > 0 then
                        set w to window 1
                        set pos to position of w
                        set sz to size of w
                        return (item 1 of pos) & "," & (item 2 of pos) & "," & (item 1 of sz) & "," & (item 2 of sz)
                    end if
                end tell
            end tell
            '''
            r = await self._run_applescript(script)
            if not r.success:
                last_error = r.error or "AppleScript 执行失败"
                continue
            if not r.output:
                last_error = "应用无窗口或窗口未就绪"
                continue
            bounds = self._parse_window_bounds(r.output)
            if bounds:
                x, y, w, h = bounds
                return await self.screenshot_region(path, x, y, w, h)
            last_error = f"解析窗口信息失败 (output={r.output[:80]!r})"
        return False, last_error
    
    # ---------- GUI 输入 ----------
    
    async def mouse_move(self, x: int, y: int) -> Tuple[bool, str]:
        try:
            process = await asyncio.create_subprocess_exec(
                "cliclick", f"m:{x},{y}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                script = f'''
                do shell script "python3 -c \\"
                import Quartz
                e = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, ({x}, {y}), 0)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)
                \\""
                '''
                r = await self._run_applescript(script)
                return r.success, r.error
            return True, ""
        except FileNotFoundError:
            script = f'''
            do shell script "python3 -c \\"
            import Quartz
            e = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, ({x}, {y}), 0)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)
            \\""
            '''
            r = await self._run_applescript(script)
            return r.success, r.error
    
    async def mouse_click(self, x: Optional[int] = None, y: Optional[int] = None) -> Tuple[bool, str]:
        if x is not None and y is not None:
            cmd = f"c:{x},{y}"
        else:
            cmd = "c:."
        try:
            process = await asyncio.create_subprocess_exec(
                "cliclick", cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                return False, stderr.decode()
            return True, ""
        except FileNotFoundError:
            if x is not None and y is not None:
                script = f'''
                tell application "System Events"
                    click at {{{x}, {y}}}
                end tell
                '''
            else:
                return False, "cliclick 未安装且未提供坐标，请安装: brew install cliclick"
            r = await self._run_applescript(script)
            return r.success, r.error
    
    async def type_text(self, text: str) -> Tuple[bool, str]:
        script = f'''
        tell application "System Events"
            keystroke "{text.replace('"', '\\"')}"
        end tell
        '''
        r = await self._run_applescript(script)
        return r.success, r.error
    
    async def get_window_info(self, app_name: str) -> Tuple[bool, Dict, str]:
        script = f'''
        tell application "System Events"
            tell process "{app_name}"
                if (count of windows) > 0 then
                    set w to window 1
                    set winName to name of w
                    set winPos to position of w
                    set winSize to size of w
                    return "name:" & winName & "|pos:" & (item 1 of winPos) & "," & (item 2 of winPos) & "|size:" & (item 1 of winSize) & "," & (item 2 of winSize)
                else
                    return "no_window"
                end if
            end tell
        end tell
        '''
        r = await self._run_applescript(script)
        if not r.success:
            return False, {}, r.error
        if r.output.strip() == "no_window":
            return False, {}, f"应用 {app_name} 没有打开的窗口"
        info = {}
        for part in r.output.strip().split("|"):
            if ":" in part:
                k, v = part.split(":", 1)
                if k in ("pos", "size"):
                    a, b = v.split(",")
                    info[k] = {"x": int(a), "y": int(b)} if k == "pos" else {"width": int(a), "height": int(b)}
                else:
                    info[k] = v
        return True, info, ""
    
    # ---------- 脚本执行 ----------
    
    async def run_script(self, script: str, lang: str = "applescript") -> ScriptResult:
        if lang == "applescript":
            return await self._run_applescript(script)
        if lang == "bash" or lang == "sh":
            try:
                process = await asyncio.create_subprocess_shell(
                    script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                return ScriptResult(
                    success=process.returncode == 0,
                    output=stdout.decode(),
                    error=stderr.decode()
                )
            except Exception as e:
                return ScriptResult(success=False, error=str(e))
        return ScriptResult(success=False, error=f"不支持的脚本类型: {lang}")
    
    # ---------- 通知 ----------
    
    async def show_notification(
        self, title: str, body: str,
        subtitle: Optional[str] = None,
        sound: Optional[str] = None
    ) -> Tuple[bool, str]:
        t = title.replace('"', '\\"')
        b = body.replace('"', '\\"')
        script = f'display notification "{b}" with title "{t}"'
        if subtitle:
            s = subtitle.replace('"', '\\"')
            script += f' subtitle "{s}"'
        if sound:
            script += f' sound name "{sound}"'
        r = await self._run_applescript(script)
        return r.success, r.error
    
    async def speak(self, text: str) -> Tuple[bool, str]:
        """语音朗读 (say)"""
        try:
            escaped = text.replace('"', '\\"')
            process = await asyncio.create_subprocess_exec(
                "say", escaped,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                return False, stderr.decode()
            return True, ""
        except Exception as e:
            return False, str(e)
