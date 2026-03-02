"""
Permission status API
提供辅助功能、屏幕录制等权限状态检测，供 Mac App 查询
"""
import os
import sys
import shutil
import logging
from fastapi import APIRouter

router = APIRouter(tags=["permissions"])
logger = logging.getLogger(__name__)


@router.get("/permissions/status")
async def permission_status():
    """返回当前 Python 进程的各项权限状态"""
    # 获取 venv 的 Python 路径（未解析符号链接，用户更易理解）
    venv_python = _get_venv_python_path()
    result = {
        "python_path": sys.executable,
        "python_path_venv": venv_python,
        "accessibility": _check_accessibility(),
        "screen_recording": _check_screen_recording(),
        "automation": _check_automation(),
        "cliclick": _check_cliclick(),
        "quartz": _check_quartz(),
        "osascript": _check_osascript(),
    }
    return result


def _get_venv_python_path() -> str:
    """获取 venv 的 Python 路径（未解析符号链接）"""
    # 尝试从 VIRTUAL_ENV 环境变量获取
    venv = os.environ.get("VIRTUAL_ENV", "")
    if venv:
        candidate = os.path.join(venv, "bin", "python3")
        if os.path.exists(candidate):
            return candidate
        candidate = os.path.join(venv, "bin", "python")
        if os.path.exists(candidate):
            return candidate
    # 回退到 sys.executable
    return sys.executable


def _check_accessibility() -> dict:
    """检查辅助功能权限"""
    try:
        from runtime.permission_checker import check_accessibility_permission
        trusted = check_accessibility_permission(prompt=False)
        return {
            "granted": trusted,
            "description": "辅助功能权限，用于模拟键鼠操作（CGEvent / AppleScript keystroke）",
            "settings_url": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            "guidance": (
                f"请在 系统设置 → 隐私与安全性 → 辅助功能 中添加：\n{sys.executable}"
                if not trusted else "已授权"
            ),
        }
    except Exception as e:
        return {
            "granted": False,
            "description": "辅助功能权限检测失败",
            "error": str(e),
            "guidance": f"检测失败: {e}，请手动在系统设置中添加 {sys.executable}",
        }


def _check_screen_recording() -> dict:
    """
    检查屏幕录制权限
    通过尝试截图到临时文件来检测
    """
    import tempfile
    import subprocess
    try:
        tmp = os.path.join(tempfile.gettempdir(), "macagent_screen_check.png")
        proc = subprocess.run(
            ["screencapture", "-x", "-c"],
            capture_output=True, timeout=5,
        )
        # screencapture 即使无权限也返回 0，但截图为空
        # 更可靠的方式：尝试 CGWindowListCreateImage
        try:
            import Quartz
            image = Quartz.CGWindowListCreateImage(
                Quartz.CGRectInfinite,
                Quartz.kCGWindowListOptionOnScreenOnly,
                Quartz.kCGNullWindowID,
                Quartz.kCGWindowImageDefault,
            )
            granted = image is not None
        except ImportError:
            # 无 Quartz，假设 screencapture 可用
            granted = proc.returncode == 0
        except Exception:
            granted = proc.returncode == 0

        return {
            "granted": granted,
            "description": "屏幕录制权限，用于截取屏幕内容",
            "settings_url": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
            "guidance": (
                f"请在 系统设置 → 隐私与安全性 → 屏幕录制 中添加：\n{sys.executable}"
                if not granted else "已授权"
            ),
        }
    except Exception as e:
        return {
            "granted": False,
            "description": "屏幕录制权限检测失败",
            "error": str(e),
            "guidance": f"检测失败: {e}",
        }


def _check_automation() -> dict:
    """
    检查自动化(Automation) 权限
    通过尝试执行一个简单的 AppleScript 来检测
    """
    import subprocess
    try:
        # 尝试通过 System Events 获取一个简单属性
        proc = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to return name of first process whose frontmost is true'],
            capture_output=True, timeout=5,
        )
        granted = proc.returncode == 0
        return {
            "granted": granted,
            "description": "自动化权限，允许通过 AppleScript 控制 System Events 等应用",
            "settings_url": "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
            "guidance": (
                "已授权" if granted
                else "Python 进程的自动化权限（System Events）未授权。请在 系统设置 → 隐私与安全性 → 自动化 中允许。"
            ),
        }
    except Exception as e:
        return {
            "granted": False,
            "description": "自动化权限检测失败",
            "error": str(e),
            "guidance": f"检测失败: {e}",
        }


def _check_cliclick() -> dict:
    """检查 cliclick 是否可用"""
    path = shutil.which("cliclick")
    return {
        "available": path is not None,
        "path": path or "",
        "description": "cliclick 命令行工具，用于鼠标/键盘模拟（CGEvent 不可用时的回退方案）",
        "guidance": "安装方式: brew install cliclick" if not path else f"已安装: {path}",
    }


def _check_quartz() -> dict:
    """检查 Quartz (pyobjc) 是否可用"""
    try:
        from runtime import cg_event
        return {
            "available": cg_event.HAS_QUARTZ,
            "description": "Quartz CGEvent API，用于进程内键鼠模拟（最快最可靠的方式）",
            "guidance": "已可用" if cg_event.HAS_QUARTZ else "未安装 pyobjc-framework-Quartz",
        }
    except Exception as e:
        return {
            "available": False,
            "description": "Quartz CGEvent API",
            "error": str(e),
            "guidance": f"检测失败: {e}",
        }


def _check_osascript() -> dict:
    """检查 osascript 是否可用"""
    path = shutil.which("osascript")
    return {
        "available": path is not None,
        "path": path or "",
        "description": "AppleScript 执行工具，用于应用控制和自动化",
        "guidance": "已可用" if path else "osascript 未找到（这不应该在 macOS 上发生）",
    }
