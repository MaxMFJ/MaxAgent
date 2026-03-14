"""
UserContextMixin — Layer 1: User environment context collection.
Extracted from autonomous_agent.py.
"""

import asyncio
import getpass
import json
import logging
import os
import time
from datetime import datetime
from typing import List

logger = logging.getLogger(__name__)


class UserContextMixin:
    """Mixin providing user environment context collection for AutonomousAgent."""

    async def _collect_user_context(self) -> str:
        """Collect user environment context (locale, timezone, path, approximate location).
        LEGACY PATH (DO NOT EXTEND) — 基础部分与 ContextBuilder.collect_user_context 重叠，
        但此版本含 _get_approximate_location 等增强。待后续统一。
        """
        parts: List[str] = []

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parts.append(f"- Current Time: {now_str}")

        # 实际路径（保存文件、向用户报告时必须用此，禁止用 xxx 或 $(whoami)）
        try:
            username = getpass.getuser()
            desktop = os.path.realpath(os.path.expanduser("~/Desktop"))
            parts.append(f"- Current User: {username}")
            # Duck 沙箱模式：将桌面路径提示替换为沙箱工作区，防止文件写入桌面
            try:
                from app_state import get_duck_context as _get_dc
                _dc = _get_dc()
                _sandbox_dir = (_dc or {}).get("sandbox_dir")
            except Exception:
                _sandbox_dir = None
            if _sandbox_dir:
                # Duck 沙箱模式：完全隐藏桌面路径，只暴露沙箱工作区，防止 LLM 误用
                parts.append(f"- Workspace: {_sandbox_dir} (Save ALL output files here. Do NOT use Desktop.)")
            else:
                parts.append(f"- Desktop Path: {desktop} (Use this exact path when saving files to Desktop or reporting to the user. NEVER use /Users/xxx/ or $(whoami).)")
        except Exception:
            pass

        # System locale
        try:
            proc = await asyncio.create_subprocess_shell(
                "defaults read NSGlobalDomain AppleLocale 2>/dev/null || echo unknown",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            locale_str = stdout.decode().strip()
            if locale_str and locale_str != "unknown":
                parts.append(f"- System Locale: {locale_str}")
        except Exception:
            pass

        # Timezone
        try:
            tz = time.tzname[0] if time.tzname else "unknown"
            try:
                tz_full = datetime.now().astimezone().tzinfo
                parts.append(f"- Timezone: {tz_full}")
            except Exception:
                parts.append(f"- Timezone: {tz}")
        except Exception:
            pass

        # Approximate location via macOS system or IP geolocation
        city = await self._get_approximate_location()
        if city:
            parts.append(f"- Approximate Location: {city}")

        if not parts:
            return ""

        return "## User Environment\n" + "\n".join(parts)

    async def _get_approximate_location(self) -> str:
        """Best-effort approximate city via system timezone or IP geolocation."""
        # Strategy 1: derive city from macOS timezone setting
        try:
            proc = await asyncio.create_subprocess_shell(
                "readlink /etc/localtime 2>/dev/null || echo ''",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
            tz_path = stdout.decode().strip()
            # e.g. /var/db/timezone/zoneinfo/Asia/Shanghai -> Shanghai
            if "/" in tz_path:
                city_part = tz_path.rsplit("/", 1)[-1]
                if city_part and city_part not in ("UTC", "GMT", "localtime"):
                    return city_part
        except Exception:
            pass

        # Strategy 2: lightweight IP geolocation (timeout 3s)
        try:
            proc = await asyncio.create_subprocess_shell(
                'curl -s --max-time 3 "http://ip-api.com/json/?fields=city,country" 2>/dev/null',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            data = json.loads(stdout.decode().strip())
            city = data.get("city", "")
            country = data.get("country", "")
            if city:
                return f"{city}, {country}" if country else city
        except Exception:
            pass

        return ""
