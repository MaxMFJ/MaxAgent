"""
Permission Checker - macOS 辅助功能权限检测与引导
直接调用 ApplicationServices 框架，无需外部工具
"""

import logging
import subprocess
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 权限状态缓存
_cached_trusted: Optional[bool] = None


def check_accessibility_permission(prompt: bool = False) -> bool:
    """
    检查当前进程是否拥有辅助功能权限
    
    Args:
        prompt: 如果为 True，macOS 会弹出权限请求对话框
    
    Returns:
        True 表示已授权
    """
    global _cached_trusted
    try:
        import ApplicationServices
        if prompt:
            # AXIsProcessTrustedWithOptions 可以弹出系统权限对话框
            options = {ApplicationServices.kAXTrustedCheckOptionPrompt: True}
            trusted = ApplicationServices.AXIsProcessTrustedWithOptions(options)
        else:
            trusted = ApplicationServices.AXIsProcessTrusted()
        _cached_trusted = trusted
        return trusted
    except ImportError:
        logger.warning("ApplicationServices 未安装，尝试 ctypes 方式检测")
        return _check_via_ctypes(prompt)
    except Exception as e:
        logger.error(f"权限检测失败: {e}")
        return False


def _check_via_ctypes(prompt: bool = False) -> bool:
    """通过 ctypes 调用 CoreFoundation/ApplicationServices 检测权限"""
    global _cached_trusted
    try:
        import ctypes
        import ctypes.util

        # 加载 ApplicationServices 框架
        app_services = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        
        if prompt:
            # 加载 CoreFoundation
            cf = ctypes.cdll.LoadLibrary(
                ctypes.util.find_library("CoreFoundation")
            )
            # 创建 CFDictionary with kAXTrustedCheckOptionPrompt = True
            cf.CFStringCreateWithCString.restype = ctypes.c_void_p
            cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
            cf.CFBooleanGetValue.restype = ctypes.c_bool
            cf.CFDictionaryCreate.restype = ctypes.c_void_p
            
            key = cf.CFStringCreateWithCString(None, b"AXTrustedCheckOptionPrompt", 0)
            # kCFBooleanTrue
            cf.CFRelease.argtypes = [ctypes.c_void_p]
            
            # 使用 AXIsProcessTrustedWithOptions
            app_services.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
            app_services.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
            
            # 创建字典 {kAXTrustedCheckOptionPrompt: kCFBooleanTrue}
            kCFBooleanTrue = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
            keys = (ctypes.c_void_p * 1)(key)
            values = (ctypes.c_void_p * 1)(kCFBooleanTrue)
            cf.CFDictionaryCreate.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                ctypes.POINTER(ctypes.c_void_p), ctypes.c_long,
                ctypes.c_void_p, ctypes.c_void_p
            ]
            options = cf.CFDictionaryCreate(None, keys, values, 1, None, None)
            
            trusted = app_services.AXIsProcessTrustedWithOptions(options)
            cf.CFRelease(options)
            cf.CFRelease(key)
        else:
            app_services.AXIsProcessTrusted.restype = ctypes.c_bool
            trusted = app_services.AXIsProcessTrusted()
        
        _cached_trusted = trusted
        return trusted
    except Exception as e:
        logger.error(f"ctypes 权限检测失败: {e}")
        return False


def get_permission_status() -> dict:
    """
    获取详细的权限状态信息
    
    Returns:
        dict 包含:
        - trusted: bool 是否已授权
        - process_path: str 当前进程路径
        - guidance: str 用户引导文字
    """
    import sys
    import os
    
    trusted = check_accessibility_permission(prompt=False)
    process_path = sys.executable
    
    guidance = ""
    if not trusted:
        guidance = (
            "辅助功能权限未授予，所有键鼠模拟操作将会失败。\n"
            "请按以下步骤授权：\n"
            "1. 打开 系统设置 → 隐私与安全性 → 辅助功能\n"
            f"2. 点击 '+' 添加: {process_path}\n"
            "3. 如果使用终端运行，也需要添加终端应用（Terminal/iTerm2/VS Code 等）\n"
            "4. 添加后可能需要重启应用才能生效"
        )
    
    return {
        "trusted": trusted,
        "process_path": process_path,
        "terminal_app": os.environ.get("TERM_PROGRAM", "未知"),
        "guidance": guidance,
    }


def request_permission() -> bool:
    """
    请求辅助功能权限（弹出系统对话框）
    
    Returns:
        True 表示已经有权限，False 表示需要用户手动授权
    """
    return check_accessibility_permission(prompt=True)


def open_accessibility_settings():
    """打开系统设置的辅助功能页面"""
    try:
        subprocess.Popen([
            "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        ])
        return True
    except Exception as e:
        logger.error(f"无法打开系统设置: {e}")
        return False
