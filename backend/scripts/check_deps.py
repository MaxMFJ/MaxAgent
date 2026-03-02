#!/usr/bin/env python3
"""验证 pyobjc 依赖可用性"""
import sys

checks = []

try:
    import Quartz
    from Quartz import (
        CGEventCreateMouseEvent, CGEventPost, kCGHIDEventTap,
        kCGEventMouseMoved, kCGEventLeftMouseDown, kCGEventLeftMouseUp,
        kCGEventRightMouseDown, kCGEventRightMouseUp,
        CGEventCreateScrollWheelEvent, CGEventCreateKeyboardEvent,
        CGEventSetFlags, kCGEventFlagMaskCommand, kCGEventFlagMaskShift,
        kCGEventFlagMaskAlternate, kCGEventFlagMaskControl,
        CGDisplayPixelsWide, CGDisplayPixelsHigh, CGMainDisplayID,
    )
    checks.append("Quartz CGEvent: OK")
except Exception as e:
    checks.append(f"Quartz CGEvent: FAIL - {e}")

try:
    from ApplicationServices import (
        AXUIElementCreateApplication,
        AXUIElementCreateSystemWide,
        AXUIElementCopyAttributeValue,
        AXUIElementCopyAttributeNames,
        AXUIElementPerformAction,
        AXUIElementSetAttributeValue,
        AXIsProcessTrusted,
    )
    checks.append("AXUIElement: OK")
    checks.append(f"AXIsProcessTrusted: {AXIsProcessTrusted()}")
except Exception as e:
    checks.append(f"AXUIElement: FAIL - {e}")

try:
    from AppKit import NSWorkspace, NSRunningApplication, NSEvent
    checks.append("AppKit: OK")
except Exception as e:
    checks.append(f"AppKit: FAIL - {e}")

try:
    from AppKit import NSEvent
    from Quartz import CGDisplayPixelsHigh, CGMainDisplayID
    loc = NSEvent.mouseLocation()
    sh = CGDisplayPixelsHigh(CGMainDisplayID())
    checks.append(f"Mouse at: ({int(loc.x)}, {int(sh - loc.y)})")
    checks.append(f"Screen: {CGDisplayPixelsWide(CGMainDisplayID())}x{sh}")
except Exception as e:
    checks.append(f"Mouse/Screen: FAIL - {e}")

for c in checks:
    print(c)
