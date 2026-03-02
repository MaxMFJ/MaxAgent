"""
ax_utils.py - macOS Accessibility API (AXUIElement) 工具模块
通过 AXUIElement API 实现：
  - UI 元素查找（按角色、标签、标题）
  - UI 树遍历
  - 元素操作（点击、设值、获取属性）
  - 权限检查与引导

依赖: pyobjc-framework-ApplicationServices
权限: 需要辅助功能权限 (Accessibility)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from ApplicationServices import (
        AXUIElementCreateApplication,
        AXUIElementCreateSystemWide,
        AXUIElementCopyAttributeValue,
        AXUIElementCopyAttributeNames,
        AXUIElementPerformAction,
        AXUIElementSetAttributeValue,
        AXUIElementCopyActionNames,
        AXIsProcessTrusted,
        kAXErrorSuccess,
    )
    from AppKit import NSWorkspace, NSRunningApplication
    from CoreFoundation import CFRange
    HAS_AX = True
except ImportError:
    HAS_AX = False
    logger.warning("ApplicationServices 不可用，AXUIElement 功能将不工作")


# ===================== 权限检查 =====================

def is_accessibility_enabled() -> bool:
    """检查辅助功能权限是否已授予"""
    if not HAS_AX:
        return False
    return AXIsProcessTrusted()


def check_accessibility() -> Tuple[bool, str]:
    """
    检查辅助功能权限状态
    返回 (enabled, message)
    """
    if not HAS_AX:
        return False, "pyobjc-framework-ApplicationServices 未安装"
    enabled = AXIsProcessTrusted()
    if enabled:
        return True, "辅助功能权限已授予"
    return False, (
        "辅助功能权限未授予。请前往 系统设置 > 隐私与安全 > 辅助功能，"
        "勾选当前应用（Terminal/Python/MacAgentApp）"
    )


# ===================== 进程查找 =====================

def get_pid_for_app(app_name: str) -> Optional[int]:
    """通过应用名获取 PID"""
    if not HAS_AX:
        return None
    workspace = NSWorkspace.sharedWorkspace()
    apps = workspace.runningApplications()
    app_name_lower = app_name.lower()
    for app in apps:
        name = app.localizedName()
        bundle = app.bundleIdentifier() or ""
        if name and name.lower() == app_name_lower:
            return app.processIdentifier()
        # 也匹配 bundle id 的最后一段
        if bundle:
            last_part = bundle.split(".")[-1].lower()
            if last_part == app_name_lower:
                return app.processIdentifier()
    return None


def get_running_apps() -> List[Dict[str, Any]]:
    """获取正在运行的应用列表（含 PID、名称、bundle）"""
    if not HAS_AX:
        return []
    workspace = NSWorkspace.sharedWorkspace()
    apps = workspace.runningApplications()
    result = []
    for app in apps:
        if app.activationPolicy() == 0:  # NSApplicationActivationPolicyRegular
            result.append({
                "name": app.localizedName() or "",
                "pid": app.processIdentifier(),
                "bundle_id": app.bundleIdentifier() or "",
                "active": app.isActive(),
            })
    return result


# ===================== AX 属性操作 =====================

def _ax_get_attr(element, attr_name: str) -> Tuple[bool, Any]:
    """获取 AX 属性值"""
    if not HAS_AX:
        return False, None
    err, value = AXUIElementCopyAttributeValue(element, attr_name, None)
    if err == kAXErrorSuccess:
        return True, value
    return False, None


def _ax_get_all_attrs(element) -> List[str]:
    """获取元素的所有属性名"""
    if not HAS_AX:
        return []
    err, attrs = AXUIElementCopyAttributeNames(element, None)
    if err == kAXErrorSuccess and attrs:
        return list(attrs)
    return []


def _ax_get_actions(element) -> List[str]:
    """获取元素支持的所有操作"""
    if not HAS_AX:
        return []
    err, actions = AXUIElementCopyActionNames(element, None)
    if err == kAXErrorSuccess and actions:
        return list(actions)
    return []


def _ax_perform_action(element, action: str) -> Tuple[bool, str]:
    """对元素执行操作（如 AXPress, AXClick）"""
    if not HAS_AX:
        return False, "AX 不可用"
    err = AXUIElementPerformAction(element, action)
    if err == kAXErrorSuccess:
        return True, ""
    return False, f"AX 操作 '{action}' 失败，错误码: {err}"


def _ax_set_attr(element, attr_name: str, value) -> Tuple[bool, str]:
    """设置 AX 属性值"""
    if not HAS_AX:
        return False, "AX 不可用"
    err = AXUIElementSetAttributeValue(element, attr_name, value)
    if err == kAXErrorSuccess:
        return True, ""
    return False, f"设置属性 '{attr_name}' 失败，错误码: {err}"


# ===================== 元素信息 =====================

def get_element_info(element) -> Dict[str, Any]:
    """获取元素的基本信息"""
    info = {}
    for attr in ["AXRole", "AXRoleDescription", "AXTitle", "AXDescription",
                  "AXValue", "AXIdentifier", "AXEnabled", "AXFocused",
                  "AXPosition", "AXSize"]:
        ok, val = _ax_get_attr(element, attr)
        if ok and val is not None:
            # 将 AXPosition/AXSize 转换为 dict
            if attr == "AXPosition":
                try:
                    from Quartz import CGPoint
                    info["position"] = {"x": int(val.x), "y": int(val.y)}
                except Exception:
                    info["position"] = str(val)
            elif attr == "AXSize":
                try:
                    info["size"] = {"width": int(val.width), "height": int(val.height)}
                except Exception:
                    info["size"] = str(val)
            else:
                info[attr.replace("AX", "").lower()] = _convert_value(val)
    info["actions"] = _ax_get_actions(element)
    return info


def _convert_value(val) -> Any:
    """将 AX 值转为 Python 原生类型"""
    if val is None:
        return None
    if isinstance(val, (bool, int, float, str)):
        return val
    # NSString, NSNumber 等
    try:
        if hasattr(val, "boolValue"):
            return bool(val.boolValue())
    except Exception:
        pass
    try:
        return str(val)
    except Exception:
        return repr(val)


# ===================== UI 树遍历 =====================

def get_app_element(pid: int):
    """获取应用的根 AX 元素"""
    if not HAS_AX:
        return None
    return AXUIElementCreateApplication(pid)


def get_system_wide_element():
    """获取系统级 AX 元素"""
    if not HAS_AX:
        return None
    return AXUIElementCreateSystemWide()


def get_children(element) -> list:
    """获取子元素"""
    ok, children = _ax_get_attr(element, "AXChildren")
    if ok and children:
        return list(children)
    return []


def get_focused_element(app_element) -> Optional[Any]:
    """获取应用中当前聚焦的元素"""
    ok, focused = _ax_get_attr(app_element, "AXFocusedUIElement")
    if ok:
        return focused
    return None


def find_elements(
    element,
    role: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    identifier: Optional[str] = None,
    value: Optional[str] = None,
    max_depth: int = 10,
    max_results: int = 50,
) -> List[Dict[str, Any]]:
    """
    在 UI 树中搜索匹配条件的元素
    
    参数:
        element: AX 根元素
        role: 角色过滤 (如 AXButton, AXTextField, AXStaticText)
        title: 标题匹配（包含）
        description: 描述匹配（包含）
        identifier: 标识符精确匹配
        value: 值匹配（包含）
        max_depth: 最大遍历深度
        max_results: 最大返回数量
    
    返回:
        匹配元素的信息列表，包含 element 引用
    """
    results = []
    _search_recursive(
        element, role, title, description, identifier, value,
        max_depth, max_results, results, depth=0
    )
    return results


def _search_recursive(
    element, role, title, description, identifier, value,
    max_depth, max_results, results, depth,
):
    """递归遍历 UI 树搜索"""
    if depth > max_depth or len(results) >= max_results:
        return

    # 检查当前元素是否匹配
    match = True

    if role:
        ok, elem_role = _ax_get_attr(element, "AXRole")
        if not ok or (elem_role and str(elem_role) != role):
            match = False

    if match and title is not None:
        ok, elem_title = _ax_get_attr(element, "AXTitle")
        if not ok or not elem_title or title.lower() not in str(elem_title).lower():
            match = False

    if match and description is not None:
        ok, elem_desc = _ax_get_attr(element, "AXDescription")
        if not ok or not elem_desc or description.lower() not in str(elem_desc).lower():
            match = False

    if match and identifier is not None:
        ok, elem_id = _ax_get_attr(element, "AXIdentifier")
        if not ok or str(elem_id) != identifier:
            match = False

    if match and value is not None:
        ok, elem_val = _ax_get_attr(element, "AXValue")
        if not ok or not elem_val or value.lower() not in str(elem_val).lower():
            match = False

    if match and (role or title or description or identifier or value):
        info = get_element_info(element)
        info["_element"] = element  # 保留引用以便后续操作
        info["_depth"] = depth
        results.append(info)

    # 递归子元素
    children = get_children(element)
    for child in children:
        if len(results) >= max_results:
            break
        _search_recursive(
            child, role, title, description, identifier, value,
            max_depth, max_results, results, depth + 1
        )


def get_ui_tree(element, max_depth: int = 3) -> Dict[str, Any]:
    """
    获取 UI 树的结构信息（用于调试/display）
    max_depth: 最大深度，避免过大
    """
    return _build_tree(element, max_depth, depth=0)


def _build_tree(element, max_depth: int, depth: int) -> Dict[str, Any]:
    """递归构建 UI 树"""
    if depth > max_depth:
        return {"_truncated": True}

    info = {}
    for attr in ["AXRole", "AXTitle", "AXDescription", "AXValue", "AXIdentifier"]:
        ok, val = _ax_get_attr(element, attr)
        if ok and val is not None:
            key = attr.replace("AX", "").lower()
            val_str = str(val)
            if len(val_str) > 100:
                val_str = val_str[:100] + "..."
            info[key] = val_str

    children = get_children(element)
    if children:
        info["children_count"] = len(children)
        info["children"] = []
        for child in children[:30]:  # 限制每层最多 30 个子元素
            info["children"].append(_build_tree(child, max_depth, depth + 1))
        if len(children) > 30:
            info["children"].append({"_truncated": f"还有 {len(children) - 30} 个子元素"})

    return info


# ===================== 高级操作 =====================

def click_element(element) -> Tuple[bool, str]:
    """点击一个 AX 元素（通过 AXPress 操作）"""
    actions = _ax_get_actions(element)
    if "AXPress" in actions:
        return _ax_perform_action(element, "AXPress")
    if "AXClick" in actions:
        return _ax_perform_action(element, "AXClick")
    # 回退：获取位置用 CGEvent 点击
    ok, pos = _ax_get_attr(element, "AXPosition")
    ok2, size = _ax_get_attr(element, "AXSize")
    if ok and ok2 and pos and size:
        try:
            from .cg_event import mouse_click
            cx = int(pos.x + size.width / 2)
            cy = int(pos.y + size.height / 2)
            return mouse_click(cx, cy)
        except Exception as e:
            return False, f"坐标点击失败: {e}"
    return False, "元素不支持点击操作，也没有有效的位置信息"


def set_element_value(element, value: str) -> Tuple[bool, str]:
    """设置文本框的值"""
    # 先尝试直接设值
    ok, err = _ax_set_attr(element, "AXValue", value)
    if ok:
        return True, ""
    # 尝试聚焦后输入
    _ax_set_attr(element, "AXFocused", True)
    return False, f"设值失败: {err}，可尝试聚焦后用键盘输入"


def focus_element(element) -> Tuple[bool, str]:
    """聚焦元素"""
    return _ax_set_attr(element, "AXFocused", True)


def find_and_click(
    pid: int, role: str = "AXButton", title: Optional[str] = None, **kwargs
) -> Tuple[bool, str]:
    """
    便捷方法：在应用中找到元素并点击
    示例: find_and_click(pid, role="AXButton", title="确定")
    """
    app = get_app_element(pid)
    if not app:
        return False, "无法获取应用 AX 元素"

    results = find_elements(app, role=role, title=title, **kwargs)
    if not results:
        return False, f"未找到匹配的元素 (role={role}, title={title})"

    element = results[0].get("_element")
    if not element:
        return False, "元素引用丢失"

    return click_element(element)


def find_and_set_value(
    pid: int, value: str, role: str = "AXTextField", title: Optional[str] = None, **kwargs
) -> Tuple[bool, str]:
    """
    便捷方法：在应用中找到输入框并设值
    """
    app = get_app_element(pid)
    if not app:
        return False, "无法获取应用 AX 元素"

    results = find_elements(app, role=role, title=title, **kwargs)
    if not results:
        return False, f"未找到匹配的输入框 (role={role}, title={title})"

    element = results[0].get("_element")
    if not element:
        return False, "元素引用丢失"

    return set_element_value(element, value)
