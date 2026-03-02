#!/usr/bin/env python3
"""快速探测应用的 Accessibility 元素树"""
import sys
from ApplicationServices import (
    AXUIElementCreateApplication,
    AXUIElementCopyAttributeValue,
    AXUIElementCopyAttributeNames,
    AXUIElementPerformAction,
)
from AppKit import NSWorkspace


def find_app_pid(name_hint: str) -> int:
    """根据名称找到应用 PID（精确匹配优先）"""
    ws = NSWorkspace.sharedWorkspace()
    candidates = []
    for app in ws.runningApplications():
        n = app.localizedName() or ""
        bid = app.bundleIdentifier() or ""
        if "Helper" in n or "Networking" in n or "Graphics" in n or "网页内容" in n or "自动填充" in n:
            continue
        # 精确匹配优先
        if n == name_hint or bid.lower() == name_hint.lower():
            return app.processIdentifier(), n
        if name_hint.lower() in n.lower() or name_hint.lower() in bid.lower():
            candidates.append((app.processIdentifier(), n))
    if candidates:
        return candidates[0]
    return None, None


def get_attr(elem, attr):
    """安全获取 AX 属性"""
    err, val = AXUIElementCopyAttributeValue(elem, attr, None)
    return val if err == 0 else None


def dump_tree(elem, depth=0, max_depth=3, prefix=""):
    """递归打印元素树"""
    if depth > max_depth:
        return
    
    role = get_attr(elem, "AXRole") or "?"
    title = get_attr(elem, "AXTitle") or ""
    value = get_attr(elem, "AXValue")
    desc = get_attr(elem, "AXDescription") or ""
    identifier = get_attr(elem, "AXIdentifier") or ""
    subrole = get_attr(elem, "AXSubrole") or ""
    
    # Get position and size
    pos = get_attr(elem, "AXPosition")
    size = get_attr(elem, "AXSize")
    pos_str = ""
    if pos:
        try:
            import Quartz
            p = Quartz.CGPoint()
            Quartz.AXValueGetValue(pos, Quartz.kAXValueCGPointType, p)
            s = Quartz.CGSize()
            if size:
                Quartz.AXValueGetValue(size, Quartz.kAXValueCGSizeType, s)
            pos_str = f" @({int(p.x)},{int(p.y)} {int(s.width)}x{int(s.height)})"
        except:
            pass
    
    # Get actions
    err, actions = AXUIElementCopyAttributeNames(elem, None)
    action_list = []
    if err == 0 and actions:
        for attr_name in actions:
            if attr_name.startswith("AXAction"):
                action_list.append(attr_name)
    
    # Build display line
    indent = "  " * depth
    info_parts = []
    if title:
        info_parts.append(f'title="{title}"')
    if value is not None:
        val_str = str(value)[:50]
        info_parts.append(f'value="{val_str}"')
    if desc:
        info_parts.append(f'desc="{desc}"')
    if identifier:
        info_parts.append(f'id="{identifier}"')
    if subrole:
        info_parts.append(f'sub={subrole}')
    
    info = ", ".join(info_parts)
    print(f"{indent}{role}{pos_str} {info}")
    
    # Recurse into children
    children = get_attr(elem, "AXChildren")
    if children:
        for i, child in enumerate(children):
            if i >= 20:  # Limit children per level
                print(f"{indent}  ... ({len(children) - 20} more children)")
                break
            dump_tree(child, depth + 1, max_depth)


def main():
    app_name = sys.argv[1] if len(sys.argv) > 1 else "微信"
    max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    
    pid, found_name = find_app_pid(app_name)
    if not pid:
        print(f"找不到应用: {app_name}")
        sys.exit(1)
    
    print(f"=== {found_name} (pid={pid}) ===")
    
    app_elem = AXUIElementCreateApplication(pid)
    
    # Get app-level info
    role = get_attr(app_elem, "AXRole")
    title = get_attr(app_elem, "AXTitle")
    print(f"App: role={role}, title={title}")
    
    # Get windows
    windows = get_attr(app_elem, "AXWindows")
    print(f"Windows: {len(windows) if windows else 0}")
    
    if windows:
        for wi, win in enumerate(windows):
            wtitle = get_attr(win, "AXTitle")
            print(f"\n--- Window {wi}: {wtitle} ---")
            dump_tree(win, depth=0, max_depth=max_depth)
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
