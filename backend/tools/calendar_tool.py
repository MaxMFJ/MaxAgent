"""
Calendar Tool - 日历管理
使用 macOS Calendar.app 管理日历事件
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
from .base import BaseTool, ToolResult, ToolCategory


class CalendarTool(BaseTool):
    """日历工具，支持创建、查看、删除日历事件"""
    
    name = "calendar"
    description = "日历管理：创建事件、查看日程、设置提醒"
    category = ToolCategory.APPLICATION
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create_event", "list_events", "delete_event", "today_events", "search"],
                "description": "操作类型"
            },
            "title": {
                "type": "string",
                "description": "事件标题"
            },
            "start_date": {
                "type": "string",
                "description": "开始日期时间 (YYYY-MM-DD HH:MM)"
            },
            "end_date": {
                "type": "string",
                "description": "结束日期时间 (YYYY-MM-DD HH:MM)"
            },
            "location": {
                "type": "string",
                "description": "地点"
            },
            "notes": {
                "type": "string",
                "description": "备注"
            },
            "all_day": {
                "type": "boolean",
                "description": "是否全天事件"
            },
            "reminder_minutes": {
                "type": "number",
                "description": "提前提醒分钟数"
            },
            "calendar_name": {
                "type": "string",
                "description": "日历名称，默认使用默认日历"
            },
            "days": {
                "type": "number",
                "description": "查看未来几天的事件"
            },
            "search_query": {
                "type": "string",
                "description": "搜索关键词"
            }
        },
        "required": ["action"]
    }
    
    async def execute(
        self,
        action: str,
        title: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
        all_day: bool = False,
        reminder_minutes: Optional[int] = None,
        calendar_name: Optional[str] = None,
        days: int = 7,
        search_query: Optional[str] = None
    ) -> ToolResult:
        """执行日历操作"""
        
        if action == "create_event":
            return await self._create_event(
                title, start_date, end_date, location, notes,
                all_day, reminder_minutes, calendar_name
            )
        elif action == "list_events":
            return await self._list_events(days)
        elif action == "today_events":
            return await self._today_events()
        elif action == "search":
            return await self._search_events(search_query)
        elif action == "delete_event":
            return await self._delete_event(title)
        else:
            return ToolResult(success=False, error=f"未知操作: {action}")
    
    async def _run_applescript(self, script: str) -> tuple[bool, str]:
        """执行 AppleScript（通过 runtime adapter）"""
        if not self.runtime_adapter:
            return False, "当前平台不支持 AppleScript"
        r = await self.runtime_adapter.run_script(script, lang="applescript")
        return r.success, r.output if r.success else r.error
    
    async def _create_event(
        self,
        title: str,
        start_date: str,
        end_date: Optional[str],
        location: Optional[str],
        notes: Optional[str],
        all_day: bool,
        reminder_minutes: Optional[int],
        calendar_name: Optional[str]
    ) -> ToolResult:
        """创建日历事件"""
        if not title or not start_date:
            return ToolResult(success=False, error="需要提供事件标题和开始时间")
        
        # 解析日期
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d %H:%M")
            start_str = start.strftime("%B %d, %Y %I:%M:%S %p")
        except ValueError:
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                start_str = start.strftime("%B %d, %Y 12:00:00 AM")
                all_day = True
            except ValueError:
                return ToolResult(success=False, error="日期格式错误，使用 YYYY-MM-DD HH:MM")
        
        if end_date:
            try:
                end = datetime.strptime(end_date, "%Y-%m-%d %H:%M")
                end_str = end.strftime("%B %d, %Y %I:%M:%S %p")
            except ValueError:
                end = start + timedelta(hours=1)
                end_str = end.strftime("%B %d, %Y %I:%M:%S %p")
        else:
            end = start + timedelta(hours=1)
            end_str = end.strftime("%B %d, %Y %I:%M:%S %p")
        
        title_escaped = title.replace('"', '\\"')
        
        script = f'''
        tell application "Calendar"
            tell calendar "{calendar_name or 'Calendar'}"
                set newEvent to make new event with properties {{summary:"{title_escaped}", start date:date "{start_str}", end date:date "{end_str}"'''
        
        if all_day:
            script += ', allday event:true'
        
        if location:
            location_escaped = location.replace('"', '\\"')
            script += f', location:"{location_escaped}"'
        
        if notes:
            notes_escaped = notes.replace('"', '\\"')
            script += f', description:"{notes_escaped}"'
        
        script += '}'
        
        if reminder_minutes:
            script += f'''
                tell newEvent
                    make new display alarm at end with properties {{trigger interval:-{reminder_minutes}}}
                end tell
            '''
        
        script += '''
            end tell
        end tell
        '''
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={
                "message": f"事件已创建: {title}",
                "start": start_date,
                "end": end_date or "1小时后"
            })
        return ToolResult(success=False, error=result)
    
    async def _list_events(self, days: int) -> ToolResult:
        """列出未来几天的事件"""
        script = f'''
        set eventList to {{}}
        set today to current date
        set endDay to today + ({days} * days)
        
        tell application "Calendar"
            repeat with cal in calendars
                set calEvents to (every event of cal whose start date >= today and start date <= endDay)
                repeat with evt in calEvents
                    set eventInfo to (summary of evt) & " | " & (start date of evt as string)
                    set end of eventList to eventInfo
                end repeat
            end repeat
        end tell
        
        return eventList
        '''
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={"events": result, "days": days})
        return ToolResult(success=False, error=result)
    
    async def _today_events(self) -> ToolResult:
        """获取今天的事件"""
        script = '''
        set eventList to {}
        set today to current date
        set tomorrow to today + (1 * days)
        
        tell application "Calendar"
            repeat with cal in calendars
                set calEvents to (every event of cal whose start date >= today and start date < tomorrow)
                repeat with evt in calEvents
                    set eventInfo to (summary of evt) & " | " & (start date of evt as string)
                    set end of eventList to eventInfo
                end repeat
            end repeat
        end tell
        
        return eventList
        '''
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={"today_events": result})
        return ToolResult(success=False, error=result)
    
    async def _search_events(self, query: str) -> ToolResult:
        """搜索事件"""
        if not query:
            return ToolResult(success=False, error="需要提供搜索关键词")
        
        query_escaped = query.replace('"', '\\"')
        
        script = f'''
        set eventList to {{}}
        
        tell application "Calendar"
            repeat with cal in calendars
                set calEvents to (every event of cal whose summary contains "{query_escaped}")
                repeat with evt in calEvents
                    set eventInfo to (summary of evt) & " | " & (start date of evt as string)
                    set end of eventList to eventInfo
                end repeat
            end repeat
        end tell
        
        return eventList
        '''
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={"search_results": result, "query": query})
        return ToolResult(success=False, error=result)
    
    async def _delete_event(self, title: str) -> ToolResult:
        """删除事件（按标题）"""
        if not title:
            return ToolResult(success=False, error="需要提供事件标题")
        
        title_escaped = title.replace('"', '\\"')
        
        script = f'''
        tell application "Calendar"
            repeat with cal in calendars
                set eventsToDelete to (every event of cal whose summary is "{title_escaped}")
                repeat with evt in eventsToDelete
                    delete evt
                end repeat
            end repeat
        end tell
        '''
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={"message": f"事件已删除: {title}"})
        return ToolResult(success=False, error=result)
