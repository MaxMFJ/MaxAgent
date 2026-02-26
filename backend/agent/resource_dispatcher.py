"""
Resource Dispatcher - 资源调度器
调度 Cursor、终端等系统资源执行升级任务
沙箱：cwd 限制、命令黑名单、超时
支持：CLI 自动执行、GUI 键盘模拟（Mac 专用）
"""

import os
import asyncio
import logging
import platform
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# MacAgent backend 根目录
MACAGENT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(MACAGENT_ROOT)

# 沙箱：允许的 cwd 路径前缀
def _norm(p: str) -> str:
    return os.path.normpath(os.path.abspath(p))

ALLOWED_CWD_PREFIXES = [
    _norm(MACAGENT_ROOT),
    _norm(os.path.join(MACAGENT_ROOT, "tools", "generated")),
    _norm(os.path.join(MACAGENT_ROOT, "data")),
    _norm(PROJECT_ROOT),
]

# 命令黑名单（子串匹配）
COMMAND_BLACKLIST = [
    "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf $HOME",
    "mkfs", "dd if=", ":(){:|:&};:", "chmod -R 777", "chown -R",
    "> /dev/sda", "mv /* ", "> /etc/", ">> /etc/",
    "curl | bash", "wget | sh", "curl | sh",
]

# 默认超时上限（秒）
MAX_TERMINAL_TIMEOUT = int(os.environ.get("MACAGENT_TERMINAL_MAX_TIMEOUT", "300"))

# Cursor CLI 执行升级任务的超时（LLM 生成代码较慢）
CURSOR_CLI_UPGRADE_TIMEOUT = int(os.environ.get("MACAGENT_CURSOR_CLI_TIMEOUT", "600"))


class DispatchTarget(str, Enum):
    """调度目标"""
    CURSOR = "cursor"      # 打开 Cursor 编辑代码
    TERMINAL = "terminal"  # 终端执行命令
    APPLESCRIPT = "applescript"  # AppleScript 控制


@dataclass
class DispatchResult:
    """调度结果"""
    success: bool
    target: DispatchTarget
    output: Optional[str] = None
    error: Optional[str] = None
    pid: Optional[int] = None


def _check_command_safety(command: str) -> Tuple[bool, str]:
    """检查命令是否在黑名单中"""
    cmd_lower = command.lower().strip()
    for pattern in COMMAND_BLACKLIST:
        if pattern.lower() in cmd_lower:
            return False, f"命令被拒绝（黑名单）: 包含 '{pattern}'"
    return True, ""


def _check_cwd_allowed(cwd: str) -> Tuple[bool, str]:
    """检查 cwd 是否在允许范围内"""
    cwd_real = os.path.abspath(os.path.expanduser(cwd))
    for prefix in ALLOWED_CWD_PREFIXES:
        if cwd_real == prefix or cwd_real.startswith(prefix + os.sep):
            return True, ""
    return False, f"cwd 不在允许范围: {cwd}"


class ResourceDispatcher:
    """
    资源调度器 - 调度电脑资源完成升级任务
    
    沙箱：
    - cwd 仅允许 backend/、tools/generated/、data/、项目根
    - 命令黑名单：rm -rf /、dd、mkfs 等
    - 超时限制
    """
    
    def __init__(self):
        self._cursor_path = self._find_cursor_app()
    
    def _find_cursor_app(self) -> Optional[str]:
        """查找 Cursor 应用路径"""
        candidates = [
            "/Applications/Cursor.app",
            os.path.expanduser("~/Applications/Cursor.app"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None
    
    def _find_agent_cli(self) -> Optional[str]:
        """查找 Cursor agent CLI（需先安装：curl https://cursor.com/install -fsSL | bash）"""
        import shutil
        agent_path = shutil.which("agent")
        if agent_path:
            return agent_path
        # 尝试从 Cursor.app 内查找
        for app_path in ["/Applications/Cursor.app", os.path.expanduser("~/Applications/Cursor.app")]:
            if os.path.exists(app_path):
                cli = os.path.join(app_path, "Contents", "Resources", "app", "bin", "agent")
                if os.path.isfile(cli):
                    return cli
        return None
    
    async def dispatch_to_cursor_cli(
        self,
        project_path: str,
        task_prompt: str,
        timeout: int = CURSOR_CLI_UPGRADE_TIMEOUT
    ) -> Tuple[DispatchResult, bool]:
        """
        通过 Cursor CLI 自动执行升级任务（无交互）
        成功时返回 (result, True)，CLI 不可用时返回 (fallback_result, False)
        """
        # 1. 写入 upgrade.md
        prompts_dir = os.path.join(project_path, ".cursor", "prompts")
        os.makedirs(prompts_dir, exist_ok=True)
        upgrade_file = os.path.join(prompts_dir, "upgrade.md")
        content = f"""# Chow Duck 工具自我升级任务

**请在本次对话中完成此任务，创建/修改文件后保存。**

**⚠️ 输出位置**：新工具必须创建在 Chow Duck 项目 `tools/generated/` 目录（相对于当前 workspace），禁止创建在 ~/ 或用户主目录。

---

{task_prompt}

---

## 完成后
1. 保存所有文件
2. 新工具将自动加载，用户可立即在 Chat 中调用
"""
        with open(upgrade_file, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Wrote upgrade task to {upgrade_file}")
        
        agent_path = self._find_agent_cli()
        if not agent_path:
            logger.info("Cursor agent CLI not found, will fall back to GUI")
            return (
                DispatchResult(
                    success=False,
                    target=DispatchTarget.CURSOR,
                    error="未找到 Cursor agent CLI，请安装: curl https://cursor.com/install -fsSL | bash"
                ),
                False
            )
        
        prompt = (
            "Read the task in .cursor/prompts/upgrade.md and execute it completely. "
            "Create the required tool file in tools/generated/ as specified. "
            "Apply all file changes. Do not ask for confirmation."
        )
        
        try:
            process = await asyncio.create_subprocess_exec(
                agent_path, "-p", "--force", prompt,
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return (
                    DispatchResult(
                        success=False,
                        target=DispatchTarget.CURSOR,
                        error=f"Cursor CLI 执行超时 ({timeout}s)"
                    ),
                    True
                )
            out = stdout.decode().strip() or stderr.decode().strip()
            return (
                DispatchResult(
                    success=(process.returncode == 0),
                    target=DispatchTarget.CURSOR,
                    output=out[:3000] if out else None,
                    error=None if process.returncode == 0 else stderr.decode()[:500],
                    pid=process.pid
                ),
                True
            )
        except Exception as e:
            logger.error(f"Cursor CLI execution failed: {e}")
            return (
                DispatchResult(
                    success=False,
                    target=DispatchTarget.CURSOR,
                    error=str(e)
                ),
                True
            )
    
    async def dispatch_to_cursor_gui_auto(
        self,
        project_path: str,
        task_prompt: str,
    ) -> Tuple[DispatchResult, bool]:
        """
        通过 Mac 键盘模拟：打开 Cursor → 聚焦 Chat → 粘贴任务 → 发送
        无需安装 Cursor CLI，直接使用已安装的 Cursor.app
        成功返回 (result, True)，不可用时返回 (result, False)
        """
        if platform.system() != "Darwin":
            return (
                DispatchResult(
                    success=False,
                    target=DispatchTarget.CURSOR,
                    error="GUI 键盘模拟仅支持 macOS"
                ),
                False
            )
        if not self._cursor_path:
            return (
                DispatchResult(
                    success=False,
                    target=DispatchTarget.CURSOR,
                    error="未找到 Cursor 应用"
                ),
                False
            )
        
        prompts_dir = os.path.join(project_path, ".cursor", "prompts")
        os.makedirs(prompts_dir, exist_ok=True)
        upgrade_file = os.path.join(prompts_dir, "upgrade.md")
        content = f"""# Chow Duck 工具自我升级任务

**请在本次对话中完成此任务，创建/修改文件后保存。**

**⚠️ 输出位置**：新工具必须创建在 Chow Duck 项目 `tools/generated/` 目录（相对于当前 workspace），禁止创建在 ~/ 或用户主目录。

---

{task_prompt}

---

## 完成后
1. 保存所有文件
2. 新工具将自动加载，用户可立即在 Chat 中调用
"""
        with open(upgrade_file, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Wrote upgrade task to {upgrade_file}")
        
        # 剪贴板写入简短指令（让 Cursor AI 读取 upgrade.md 执行）
        instruction = (
            "请根据 .cursor/prompts/upgrade.md 中的任务说明，创建 tools/generated/ 下的工具文件并保存。"
        )
        
        try:
            from runtime import get_runtime_adapter
            adapter = get_runtime_adapter()
            ok, err = await adapter.clipboard_write(instruction)
            if not ok:
                logger.warning(f"Clipboard write failed: {err}")
                return (
                    DispatchResult(success=False, target=DispatchTarget.CURSOR, error=f"剪贴板写入失败: {err}"),
                    False
                )
            
            # 打开 Cursor，优先打开项目目录（确保 workspace 正确），再定位到 upgrade.md
            proc = await asyncio.create_subprocess_exec(
                "open", "-a", "Cursor", project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            await asyncio.sleep(2.5)  # 等待 Cursor 完全启动
            
            # 使用 Cmd+I 打开 Composer（更适合执行任务），也可用 Cmd+L 打开 Chat
            use_composer = os.environ.get("MACAGENT_CURSOR_USE_COMPOSER", "true").lower() == "true"
            shortcut_key = "i" if use_composer else "l"
            
            # AppleScript：激活 Cursor → Cmd+I/L 打开面板 → 延时 → 粘贴 → 回车发送
            # 注意：需在 系统设置→隐私与安全性→辅助功能 中授予运行后端的应用（如 Terminal）权限
            script = f'''
            tell application "Cursor" to activate
            delay 1.5
            tell application "System Events"
                keystroke "{shortcut_key}" using command down
            end tell
            delay 3
            tell application "System Events"
                keystroke "v" using command down
            end tell
            delay 0.8
            tell application "System Events"
                key code 36
            end tell
            '''
            r = await adapter.run_script(script, "applescript")
            if not r.success:
                err = r.error or ""
                hint = ""
                if "不允许发送按键" in err or "1002" in err or "not allowed" in err.lower():
                    hint = "请在 系统设置→隐私与安全性→辅助功能 中，添加运行后端的应用（如 Terminal、Chow Duck 应用或 Python），并重启后端。"
                logger.warning(f"AppleScript keystroke failed: {r.error}")
                return (
                    DispatchResult(
                        success=False,
                        target=DispatchTarget.CURSOR,
                        error=f"键盘模拟失败: {err} {hint}".strip(),
                        output="Cursor 已打开，请手动在 Chat 中粘贴并发送任务"
                    ),
                    True
                )
            return (
                DispatchResult(
                    success=True,
                    target=DispatchTarget.CURSOR,
                    output="已通过键盘模拟将任务发送到 Cursor Chat，请等待 AI 执行完成"
                ),
                True
            )
        except ImportError:
            return (
                DispatchResult(
                    success=False,
                    target=DispatchTarget.CURSOR,
                    error="无法加载 runtime adapter"
                ),
                False
            )
        except Exception as e:
            logger.error(f"Cursor GUI auto failed: {e}")
            return (
                DispatchResult(success=False, target=DispatchTarget.CURSOR, error=str(e)),
                False
            )
    
    async def dispatch_to_cursor(
        self,
        project_path: Optional[str] = None,
        file_path: Optional[str] = None,
        task_prompt: Optional[str] = None
    ) -> DispatchResult:
        """
        调度 Cursor 打开项目/文件
        
        Args:
            project_path: 项目路径，默认 Chow Duck 项目根目录
            file_path: 要打开的具体文件
            task_prompt: 任务描述，写入 .cursor/prompts/upgrade.md 供 AI 参考
        """
        if not self._cursor_path:
            return DispatchResult(
                success=False,
                target=DispatchTarget.CURSOR,
                error="未找到 Cursor 应用，请确认已安装 Cursor"
            )
        
        path = project_path or MACAGENT_ROOT
        open_path = file_path or path
        
        try:
            # 如提供任务描述，写入 .cursor/prompts/
            if task_prompt:
                prompts_dir = os.path.join(path, ".cursor", "prompts")
                os.makedirs(prompts_dir, exist_ok=True)
                upgrade_file = os.path.join(prompts_dir, "upgrade.md")
                content = f"""# Chow Duck 工具自我升级任务

**请在本次对话中完成此任务，创建/修改文件后保存。**

**⚠️ 输出位置**：新工具必须创建在 Chow Duck 项目 `tools/generated/` 目录（相对于当前 workspace），禁止创建在 ~/ 或用户主目录。

---

{task_prompt}

---

## 完成后
1. 保存所有文件
2. 新工具将自动加载，用户可立即在 Chat 中调用
"""
                with open(upgrade_file, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"Wrote upgrade task to {upgrade_file}")
                # 直接打开任务文件，便于用户看到并让 Cursor AI 完成
                open_path = upgrade_file
            
            cmd = ["open", "-a", "Cursor", open_path]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return DispatchResult(
                    success=True,
                    target=DispatchTarget.CURSOR,
                    output=f"已打开 Cursor: {open_path}",
                    pid=process.pid
                )
            return DispatchResult(
                success=False,
                target=DispatchTarget.CURSOR,
                error=stderr.decode() or f"exit code {process.returncode}"
            )
            
        except Exception as e:
            logger.error(f"Dispatch to Cursor failed: {e}")
            return DispatchResult(
                success=False,
                target=DispatchTarget.CURSOR,
                error=str(e)
            )
    
    async def dispatch_to_terminal(
        self,
        command: str,
        working_dir: Optional[str] = None,
        timeout: int = 60
    ) -> DispatchResult:
        """
        调度终端执行命令（沙箱）
        
        Args:
            command: shell 命令
            working_dir: 工作目录（必须在允许范围内）
            timeout: 超时秒数（不超过 MAX_TERMINAL_TIMEOUT）
        """
        cwd = working_dir or MACAGENT_ROOT
        
        # 沙箱：命令黑名单
        ok, err = _check_command_safety(command)
        if not ok:
            return DispatchResult(
                success=False,
                target=DispatchTarget.TERMINAL,
                error=err
            )
        
        # 沙箱：cwd 限制
        ok, err = _check_cwd_allowed(cwd)
        if not ok:
            return DispatchResult(
                success=False,
                target=DispatchTarget.TERMINAL,
                error=err
            )
        
        # 超时上限
        timeout = min(timeout, MAX_TERMINAL_TIMEOUT)
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return DispatchResult(
                    success=False,
                    target=DispatchTarget.TERMINAL,
                    error=f"命令执行超时 ({timeout}s)"
                )
            
            output = stdout.decode().strip() or stderr.decode().strip()
            return DispatchResult(
                success=(process.returncode == 0),
                target=DispatchTarget.TERMINAL,
                output=output[:2000] if output else None,
                error=None if process.returncode == 0 else stderr.decode()[:500],
                pid=process.pid
            )
            
        except Exception as e:
            logger.error(f"Dispatch to terminal failed: {e}")
            return DispatchResult(
                success=False,
                target=DispatchTarget.TERMINAL,
                error=str(e)
            )
    
    async def run_pip_install(self, package: str) -> DispatchResult:
        """安装 Python 包"""
        venv_pip = os.path.join(MACAGENT_ROOT, "venv", "bin", "pip")
        pip_cmd = venv_pip if os.path.exists(venv_pip) else "pip3"
        return await self.dispatch_to_terminal(
            f"{pip_cmd} install {package}",
            working_dir=MACAGENT_ROOT,
            timeout=120
        )


# 单例
_dispatcher: Optional[ResourceDispatcher] = None


def get_resource_dispatcher() -> ResourceDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = ResourceDispatcher()
    return _dispatcher
