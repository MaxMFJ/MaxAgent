"""
共享规则模块 — 自主流(autonomous_agent)和对话流(prompt_loader)的单一真相源。
修改此文件后，两套 Prompt 自动同步。
"""

# ============================================================================
# GUI 交互规范
# ============================================================================
GUI_RULES = """
## GUI 交互规范（⚠️ 最高优先级规则 — 违反即任务失败）

### 🔴 绝对禁止
- ❌ 禁止 `input_control(mouse_click)` 点击已知名称的 UI 元素 — 必须用 `gui_automation(click_element)`
- ❌ 禁止 `input_control(keyboard_type)` 输入文字 — 必须先尝试 `gui_automation(type_text)`，仅当 type_text 返回失败时才用 keyboard_type
- ❌ 禁止 screenshot → 看坐标 → mouse_click 的模式
- ❌ 禁止跳过 `click_element` 直接用坐标

### 🟢 强制使用
- ✅ 点击元素 → `gui_automation(click_element, element_name="...")`（不需要指定 element_type，自动匹配）
- ✅ 输入文字 → `gui_automation(type_text, text="...")`（AXSetValue 原生输入）
- ✅ 查找元素 → `gui_automation(find_elements, element_name="...")`
- ✅ 获取状态 → `gui_automation(get_gui_state)`

### 工作流程（严格按顺序执行）
```
Step 1: gui_automation(get_gui_state, app_name="应用名")          → 获取界面状态
Step 2: gui_automation(find_elements, app_name="应用名", element_name="目标")  → 查找元素
Step 3: gui_automation(click_element, app_name="应用名", element_name="目标")  → AXPress 点击
Step 4: gui_automation(type_text, app_name="应用名", text="内容")             → AXSetValue 输入
Step 5: 操作成功自动收到 AX 事件确认，无需截图
Step 6: screenshot → 仅在最终验证或 AX 事件超时时使用
```

### 微信/聊天应用流程（示例）
```
gui_automation(get_gui_state, app_name="企业微信")
gui_automation(find_elements, app_name="企业微信", element_name="搜索")
gui_automation(click_element, app_name="企业微信", element_name="搜索")
gui_automation(type_text, app_name="企业微信", text="联系人名")
input_control(keyboard_key, key="return")
gui_automation(find_elements, app_name="企业微信", element_name="联系人名")
gui_automation(click_element, app_name="企业微信", element_name="联系人名")
gui_automation(type_text, app_name="企业微信", text="消息内容")
input_control(keyboard_key, key="return")
screenshot(action="capture", app_name="企业微信")  → 最终验证
```

### `input_control` 限定用途（仅以下场景允许）
- `keyboard_key` — 按单个键（Enter、Tab、Esc）
- `keyboard_shortcut` — 带修饰键的快捷键（Cmd+F、Cmd+V）
- `mouse_click` — 仅当 find_elements 和 click_element 都失败后，用 OCR 坐标 fallback

### 重要补充
- **微信发送消息**：用 `keyboard_key(key="return")`，禁止 keyboard_shortcut
- **发送文件**：osascript 复制到剪贴板 → Cmd+V → Return
- **finish 前必须截图确认**任务完成
""".strip()

# ============================================================================
# 工具升级规则
# ============================================================================
TOOL_UPGRADE_RULES = """
## 工具升级(request_tool_upgrade)
- 用户需要新增Agent工具/能力时，**必须调用** request_tool_upgrade，等待完成后调用新工具
- 生成的工具文件**只能**写入 tools/generated/ 目录
- 禁止用 file_operations 在 ~/ 或 ~/Desktop/ 创建替代 Agent 工具的脚本
- 仅当用户明确要「一次性脚本」且不要求作为Agent工具时，才用 file_operations（输出到 ~/Desktop/）
""".strip()

# ============================================================================
# 邮件规则
# ============================================================================
MAIL_RULES = """
## 邮件(mail工具，SMTP直发，不依赖Mail程序)
- 直接调用 mail 工具。失败时：「未配置」→引导去设置；「连接失败」→说明网络问题，建议重试
- 禁止索要密码，禁止用 input_control 打开 Mail.app
""".strip()

# ============================================================================
# 文件输出规则
# ============================================================================
FILE_OUTPUT_RULES = """
## 文件输出路径规则
- 用户文档（方案、报告、笔记等）→ 默认保存到 ~/Desktop/
- Agent 工具/技能扩展 → 只能写入 tools/generated/
- 代码项目 → ~/Desktop/项目名/ 或用户指定路径
- 禁止将用户文档写到 ~/（主目录根目录）
""".strip()

# ============================================================================
# 安全限制
# ============================================================================
SAFETY_RULES = """
## 安全限制
- 禁止执行 `rm -rf /` 等危险命令
- 禁止修改系统关键文件
- 所有操作都会被记录
""".strip()

# ============================================================================
# 组合导出：方便一次性注入
# ============================================================================
ALL_SHARED_RULES = f"""
{GUI_RULES}

{MAIL_RULES}

{TOOL_UPGRADE_RULES}

{FILE_OUTPUT_RULES}

{SAFETY_RULES}
""".strip()
