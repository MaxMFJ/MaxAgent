"""
Shared Rules Module — Single source of truth for autonomous (autonomous_agent) and chat (prompt_loader) flows.
Changes here automatically sync to both prompt systems.
"""

# ============================================================================
# GUI Interaction Rules
# ============================================================================
GUI_RULES = """
## GUI Interaction Rules (⚠️ HIGHEST PRIORITY — violation = task failure)

### 🔴 Absolutely Forbidden
- ❌ NEVER use `input_control(mouse_click)` to click a UI element with a known name — use `gui_automation(click_element)` instead
- ❌ NEVER use `input_control(keyboard_type)` to type text — try `gui_automation(type_text)` first; use keyboard_type ONLY when type_text returns failure
- ❌ NEVER use the pattern: screenshot → read coordinates → mouse_click
- ❌ NEVER skip `click_element` and click by coordinates directly

### 🟢 Mandatory Usage
- ✅ Click element → `gui_automation(click_element, element_name="...")`  (no need to specify element_type; auto-matching)
- ✅ Type text → `gui_automation(type_text, text="...")`  (AXSetValue native input)
- ✅ Find element → `gui_automation(find_elements, element_name="...")`
- ✅ Get state → `gui_automation(get_gui_state)`

### Workflow (execute steps in strict order)
```
Step 1: gui_automation(get_gui_state, app_name="AppName")              → get UI state
Step 2: gui_automation(find_elements, app_name="AppName", element_name="target")  → find element
Step 3: gui_automation(click_element, app_name="AppName", element_name="target")  → AXPress click
Step 4: gui_automation(type_text, app_name="AppName", text="content")             → AXSetValue input
Step 5: Success confirmed automatically via AX events; no screenshot needed
Step 6: screenshot → ONLY for final verification or when AX events time out
```

### `input_control` — Allowed ONLY for:
- `keyboard_key` — Single key presses (Enter, Tab, Esc)
- `keyboard_shortcut` — Key combos with modifiers (Cmd+F, Cmd+V)
- `mouse_click` — ONLY as fallback when BOTH find_elements and click_element fail; use OCR coordinates

### Important Notes
- **WeChat sending messages**: Use `keyboard_key(key="return")`; NEVER use keyboard_shortcut
- **Sending files**: osascript → copy to clipboard → Cmd+V → Return
- **Before finish, take a screenshot** to confirm task completion
""".strip()

# ============================================================================
# Tool Upgrade Rules
# ============================================================================
TOOL_UPGRADE_RULES = """
## Tool Upgrade (request_tool_upgrade)
- When user needs a new Agent tool/capability, **must call** request_tool_upgrade and wait for completion before invoking the new tool
- Generated tool files **must only** be placed in the tools/generated/ directory
- NEVER use file_operations to create scripts in ~/ or ~/Desktop/ as substitutes for Agent tools
- Only use file_operations for one-off scripts (output to ~/Desktop/) when user explicitly wants a disposable script, not an Agent tool
""".strip()

# ============================================================================
# Email Rules
# ============================================================================
MAIL_RULES = """
## Email (mail tool, direct SMTP sending, no Mail.app dependency)
- Call the mail tool directly. On failure: "not configured" → guide user to settings; "connection failed" → explain network issue, suggest retry
- NEVER ask for passwords; NEVER use input_control to open Mail.app
""".strip()

# ============================================================================
# File Output Rules
# ============================================================================
FILE_OUTPUT_RULES = """
## File Output Path Rules
- User documents (proposals, reports, notes) → default save to ~/Desktop/
- Agent tools/skill extensions → must only go to tools/generated/
- Code projects → ~/Desktop/<project_name>/ or user-specified path
- NEVER save user documents to ~/ (home directory root)
""".strip()

# ============================================================================
# Safety Rules
# ============================================================================
SAFETY_RULES = """
## Security Restrictions
- Never execute `rm -rf /` or similar destructive commands
- Never modify critical system files
- All operations are logged
""".strip()

# ============================================================================
# Combined Export — for convenient one-shot injection
# ============================================================================
ALL_SHARED_RULES = f"""
{GUI_RULES}

{MAIL_RULES}

{TOOL_UPGRADE_RULES}

{FILE_OUTPUT_RULES}

{SAFETY_RULES}
""".strip()
