"""
Browser Tool - 浏览器自动化
支持打开网页、获取内容、执行 JavaScript、截图等
"""

import os
import json
import asyncio
from typing import Optional, List, Dict, Any
from .base import BaseTool, ToolResult, ToolCategory


class BrowserTool(BaseTool):
    """浏览器自动化工具"""
    
    name = "browser"
    description = "浏览器自动化：打开网页、获取内容、执行操作"
    category = ToolCategory.BROWSER
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "open", "get_url", "get_title", "get_content",
                    "execute_js", "screenshot", "search", "click",
                    "type_text", "scroll", "get_tabs", "close_tab"
                ],
                "description": "浏览器操作类型"
            },
            "url": {
                "type": "string",
                "description": "要打开的 URL"
            },
            "query": {
                "type": "string",
                "description": "搜索关键词"
            },
            "javascript": {
                "type": "string",
                "description": "要执行的 JavaScript 代码"
            },
            "selector": {
                "type": "string",
                "description": "CSS 选择器（用于 click、type_text）"
            },
            "text": {
                "type": "string",
                "description": "要输入的文本"
            },
            "browser": {
                "type": "string",
                "enum": ["safari", "chrome", "firefox"],
                "description": "浏览器类型，默认 Safari"
            },
            "save_path": {
                "type": "string",
                "description": "截图保存路径"
            }
        },
        "required": ["action"]
    }
    
    async def execute(
        self,
        action: str,
        url: Optional[str] = None,
        query: Optional[str] = None,
        javascript: Optional[str] = None,
        selector: Optional[str] = None,
        text: Optional[str] = None,
        browser: str = "safari",
        save_path: Optional[str] = None
    ) -> ToolResult:
        """执行浏览器操作"""
        
        actions = {
            "open": lambda: self._open_url(url, browser),
            "get_url": lambda: self._get_current_url(browser),
            "get_title": lambda: self._get_title(browser),
            "get_content": lambda: self._get_content(browser),
            "execute_js": lambda: self._execute_js(javascript, browser),
            "screenshot": lambda: self._screenshot(save_path, browser),
            "search": lambda: self._search(query, browser),
            "click": lambda: self._click(selector, browser),
            "type_text": lambda: self._type_text(selector, text, browser),
            "scroll": lambda: self._scroll(browser),
            "get_tabs": lambda: self._get_tabs(browser),
            "close_tab": lambda: self._close_tab(browser),
        }
        
        if action not in actions:
            return ToolResult(success=False, error=f"未知操作: {action}")
        
        return await actions[action]()
    
    async def _run_applescript(self, script: str) -> tuple[bool, str]:
        """执行 AppleScript（通过 runtime adapter）"""
        if not self.runtime_adapter:
            return False, "当前平台不支持 AppleScript"
        r = await self.runtime_adapter.run_script(script, lang="applescript")
        return r.success, r.output if r.success else r.error
    
    async def _open_url(self, url: str, browser: str) -> ToolResult:
        """打开 URL"""
        if not url:
            return ToolResult(success=False, error="需要提供 URL")
        
        if browser == "safari":
            script = f'''
            tell application "Safari"
                activate
                open location "{url}"
            end tell
            '''
        elif browser == "chrome":
            script = f'''
            tell application "Google Chrome"
                activate
                open location "{url}"
            end tell
            '''
        else:
            # 使用系统默认浏览器
            script = f'open "{url}"'
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={"url": url, "browser": browser})
        return ToolResult(success=False, error=result)
    
    async def _get_current_url(self, browser: str) -> ToolResult:
        """获取当前页面 URL"""
        if browser == "safari":
            script = '''
            tell application "Safari"
                set currentURL to URL of current tab of front window
                return currentURL
            end tell
            '''
        elif browser == "chrome":
            script = '''
            tell application "Google Chrome"
                set currentURL to URL of active tab of front window
                return currentURL
            end tell
            '''
        else:
            return ToolResult(success=False, error="不支持的浏览器")
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={"url": result})
        return ToolResult(success=False, error=result)
    
    async def _get_title(self, browser: str) -> ToolResult:
        """获取当前页面标题"""
        if browser == "safari":
            script = '''
            tell application "Safari"
                set pageTitle to name of current tab of front window
                return pageTitle
            end tell
            '''
        elif browser == "chrome":
            script = '''
            tell application "Google Chrome"
                set pageTitle to title of active tab of front window
                return pageTitle
            end tell
            '''
        else:
            return ToolResult(success=False, error="不支持的浏览器")
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={"title": result})
        return ToolResult(success=False, error=result)
    
    async def _get_content(self, browser: str) -> ToolResult:
        """获取页面文本内容"""
        if browser == "safari":
            script = '''
            tell application "Safari"
                set pageContent to do JavaScript "document.body.innerText" in current tab of front window
                return pageContent
            end tell
            '''
        elif browser == "chrome":
            script = '''
            tell application "Google Chrome"
                set pageContent to execute active tab of front window javascript "document.body.innerText"
                return pageContent
            end tell
            '''
        else:
            return ToolResult(success=False, error="不支持的浏览器")
        
        success, result = await self._run_applescript(script)
        
        if success:
            # 限制返回长度
            content = result[:5000] if len(result) > 5000 else result
            return ToolResult(success=True, data={
                "content": content,
                "truncated": len(result) > 5000,
                "total_length": len(result)
            })
        return ToolResult(success=False, error=result)
    
    async def _execute_js(self, javascript: str, browser: str) -> ToolResult:
        """执行 JavaScript"""
        if not javascript:
            return ToolResult(success=False, error="需要提供 JavaScript 代码")
        
        # 转义 JavaScript 代码
        escaped_js = javascript.replace('"', '\\"').replace('\n', '\\n')
        
        if browser == "safari":
            script = f'''
            tell application "Safari"
                set jsResult to do JavaScript "{escaped_js}" in current tab of front window
                return jsResult
            end tell
            '''
        elif browser == "chrome":
            script = f'''
            tell application "Google Chrome"
                set jsResult to execute active tab of front window javascript "{escaped_js}"
                return jsResult
            end tell
            '''
        else:
            return ToolResult(success=False, error="不支持的浏览器")
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={"result": result})
        return ToolResult(success=False, error=result)
    
    async def _screenshot(self, save_path: Optional[str], browser: str) -> ToolResult:
        """截取浏览器窗口"""
        import time
        
        if not save_path:
            save_path = f"/tmp/browser_screenshot_{int(time.time())}.png"
        
        # 先激活浏览器窗口
        if browser == "safari":
            await self._run_applescript('tell application "Safari" to activate')
        elif browser == "chrome":
            await self._run_applescript('tell application "Google Chrome" to activate')
        
        await asyncio.sleep(0.5)  # 等待窗口激活
        
        # 截取当前窗口（通过 adapter）
        if not self.runtime_adapter:
            return ToolResult(success=False, error="当前平台不支持截图")
        ok, err = await self.runtime_adapter.screenshot_pick_window(save_path)
        if not ok:
            return ToolResult(success=False, error=err)
        
        if os.path.exists(save_path):
            return ToolResult(success=True, data={"path": save_path})
        return ToolResult(success=False, error="截图失败")
    
    async def _search(self, query: str, browser: str) -> ToolResult:
        """搜索"""
        if not query:
            return ToolResult(success=False, error="需要提供搜索关键词")
        
        import urllib.parse
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        
        return await self._open_url(search_url, browser)
    
    async def _click(self, selector: str, browser: str) -> ToolResult:
        """点击元素"""
        if not selector:
            return ToolResult(success=False, error="需要提供 CSS 选择器")
        
        js = f'document.querySelector("{selector}").click()'
        return await self._execute_js(js, browser)
    
    async def _type_text(self, selector: str, text: str, browser: str) -> ToolResult:
        """在输入框输入文本"""
        if not selector or not text:
            return ToolResult(success=False, error="需要提供选择器和文本")
        
        escaped_text = text.replace('"', '\\"')
        js = f'''
        var el = document.querySelector("{selector}");
        el.focus();
        el.value = "{escaped_text}";
        el.dispatchEvent(new Event("input", {{ bubbles: true }}));
        '''
        return await self._execute_js(js, browser)
    
    async def _scroll(self, browser: str) -> ToolResult:
        """向下滚动页面"""
        js = 'window.scrollBy(0, window.innerHeight)'
        return await self._execute_js(js, browser)
    
    async def _get_tabs(self, browser: str) -> ToolResult:
        """获取所有标签页"""
        if browser == "safari":
            script = '''
            tell application "Safari"
                set tabList to {}
                repeat with w in windows
                    repeat with t in tabs of w
                        set end of tabList to {name of t, URL of t}
                    end repeat
                end repeat
                return tabList
            end tell
            '''
        elif browser == "chrome":
            script = '''
            tell application "Google Chrome"
                set tabList to {}
                repeat with w in windows
                    repeat with t in tabs of w
                        set end of tabList to {title of t, URL of t}
                    end repeat
                end repeat
                return tabList
            end tell
            '''
        else:
            return ToolResult(success=False, error="不支持的浏览器")
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={"tabs": result})
        return ToolResult(success=False, error=result)
    
    async def _close_tab(self, browser: str) -> ToolResult:
        """关闭当前标签页"""
        if browser == "safari":
            script = '''
            tell application "Safari"
                close current tab of front window
            end tell
            '''
        elif browser == "chrome":
            script = '''
            tell application "Google Chrome"
                close active tab of front window
            end tell
            '''
        else:
            return ToolResult(success=False, error="不支持的浏览器")
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={"message": "标签页已关闭"})
        return ToolResult(success=False, error=result)
