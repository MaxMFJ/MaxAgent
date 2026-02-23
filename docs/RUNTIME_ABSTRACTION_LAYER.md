# Runtime Abstraction Layer - 运行时抽象层

## 一、架构

```
Core Agent (agent/core.py, tools/*)
        ↓
RuntimeAdapter (runtime/base.py)
        ↓
MacAdapter | LinuxAdapter | WindowsAdapter
```

平台无关的 Agent 通过 `get_runtime_adapter()` 获取当前平台适配器，调用统一接口。

## 二、目录结构

```
backend/runtime/
├── __init__.py       # 导出 get_runtime_adapter, current_platform
├── base.py           # RuntimeAdapter 抽象基类
├── mac_adapter.py    # macOS 实现 ✅
├── linux_adapter.py  # Linux 占位（待实现）
├── windows_adapter.py# Windows 占位（待实现）
└── registry.py       # 平台检测与适配器注册
```

## 三、接口说明

| 能力 | 方法 | Mac 实现 |
|------|------|----------|
| 应用控制 | open_app, close_app, activate_app, list_apps, get_frontmost_app | open, osascript |
| 剪贴板 | clipboard_read, clipboard_write | pbcopy, pbpaste |
| 截图 | screenshot_full, screenshot_region, screenshot_window | screencapture |
| GUI 输入 | mouse_move, mouse_click, type_text | cliclick, AppleScript |
| 窗口信息 | get_window_info | AppleScript System Events |
| 脚本执行 | run_script(script, lang) | osascript (applescript), bash |
| 通知 | show_notification | AppleScript display notification |

## 四、已接入工具

| 工具 | 使用方式 |
|------|----------|
| app_tool | adapter.open_app, close_app, activate_app, list_apps, get_frontmost_app, hide_app |
| clipboard_tool | adapter.clipboard_read, clipboard_write |
| notification_tool | adapter.show_notification |
| input_control_tool | adapter.mouse_move, adapter.run_script (applescript) |

## 五、扩展新平台

### 5.1 实现 Adapter

复制 `linux_adapter.py` 或 `windows_adapter.py`，实现抽象方法：

```python
# runtime/linux_adapter.py
class LinuxRuntimeAdapter(RuntimeAdapter):
    @property
    def platform(self) -> str:
        return "linux"
    
    async def clipboard_read(self) -> Tuple[bool, str, str]:
        # 使用 xclip 或 xsel
        ...
```

### 5.2 注册

```python
# runtime/registry.py
from .linux_adapter import LinuxRuntimeAdapter
_ADAPTER_REGISTRY["Linux"] = LinuxRuntimeAdapter
```

或运行时注册：

```python
from runtime import register_adapter
from my_linux_adapter import LinuxRuntimeAdapter
register_adapter("Linux", LinuxRuntimeAdapter)
```

## 六、Linux 参考实现

| 能力 | 推荐实现 |
|------|----------|
| 应用控制 | xdotool, wmctrl |
| 剪贴板 | xclip, xsel |
| 截图 | scrot, gnome-screenshot |
| GUI 输入 | xdotool |
| 通知 | notify-send |

## 七、Windows 参考实现

| 能力 | 推荐实现 |
|------|----------|
| 应用控制 | pywin32, ctypes |
| 剪贴板 | pyperclip |
| 截图 | pyautogui, mss |
| GUI 输入 | pyautogui |
| 通知 | win10toast |
