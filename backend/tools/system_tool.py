"""
System Information Tool
Get CPU, memory, disk, network and other system information
"""

import os
import platform
import asyncio
from datetime import datetime
from typing import Any, Dict

import psutil

from .base import BaseTool, ToolResult, ToolCategory


class SystemTool(BaseTool):
    """Tool for getting system information"""
    
    name = "system_info"
    description = """系统信息获取工具，支持以下信息类型：
- overview: 系统概览（OS、CPU、内存、磁盘基本信息）
- cpu: CPU 详细信息（核心数、使用率、频率）
- memory: 内存使用情况
- disk: 磁盘使用情况
- network: 网络接口和连接信息
- battery: 电池状态（笔记本电脑）
- processes: 进程列表（可按 CPU/内存排序）"""
    
    parameters = {
        "type": "object",
        "properties": {
            "info_type": {
                "type": "string",
                "enum": ["overview", "cpu", "memory", "disk", "network", "battery", "processes"],
                "description": "要获取的信息类型"
            },
            "sort_by": {
                "type": "string",
                "enum": ["cpu", "memory", "name"],
                "description": "进程排序方式（仅用于 processes）",
                "default": "cpu"
            },
            "limit": {
                "type": "integer",
                "description": "返回的进程数量限制（仅用于 processes）",
                "default": 10
            }
        },
        "required": ["info_type"]
    }
    
    category = ToolCategory.SYSTEM
    
    async def execute(self, **kwargs) -> ToolResult:
        info_type = kwargs.get("info_type")
        
        try:
            if info_type == "overview":
                return await self._get_overview()
            elif info_type == "cpu":
                return await self._get_cpu()
            elif info_type == "memory":
                return await self._get_memory()
            elif info_type == "disk":
                return await self._get_disk()
            elif info_type == "network":
                return await self._get_network()
            elif info_type == "battery":
                return await self._get_battery()
            elif info_type == "processes":
                sort_by = kwargs.get("sort_by", "cpu")
                limit = kwargs.get("limit", 10)
                return await self._get_processes(sort_by, limit)
            else:
                return ToolResult(success=False, error=f"未知信息类型: {info_type}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def _get_overview(self) -> ToolResult:
        """Get system overview"""
        uname = platform.uname()
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        
        data = {
            "system": uname.system,
            "node_name": uname.node,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
            "processor": uname.processor,
            "boot_time": boot_time.isoformat(),
            "uptime_seconds": (datetime.now() - boot_time).total_seconds(),
            "cpu_count": psutil.cpu_count(),
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "memory_total_gb": round(memory.total / (1024**3), 2),
            "memory_used_percent": memory.percent,
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "disk_used_percent": disk.percent
        }
        
        return ToolResult(success=True, data=data)
    
    async def _get_cpu(self) -> ToolResult:
        """Get CPU information"""
        cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
        cpu_freq = psutil.cpu_freq()
        
        data = {
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "usage_per_core": cpu_percent,
            "usage_average": sum(cpu_percent) / len(cpu_percent),
            "frequency_current_mhz": cpu_freq.current if cpu_freq else None,
            "frequency_min_mhz": cpu_freq.min if cpu_freq else None,
            "frequency_max_mhz": cpu_freq.max if cpu_freq else None
        }
        
        return ToolResult(success=True, data=data)
    
    async def _get_memory(self) -> ToolResult:
        """Get memory information"""
        virtual = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        data = {
            "virtual": {
                "total_gb": round(virtual.total / (1024**3), 2),
                "available_gb": round(virtual.available / (1024**3), 2),
                "used_gb": round(virtual.used / (1024**3), 2),
                "percent": virtual.percent
            },
            "swap": {
                "total_gb": round(swap.total / (1024**3), 2),
                "used_gb": round(swap.used / (1024**3), 2),
                "free_gb": round(swap.free / (1024**3), 2),
                "percent": swap.percent
            }
        }
        
        return ToolResult(success=True, data=data)
    
    async def _get_disk(self) -> ToolResult:
        """Get disk information"""
        partitions = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                partitions.append({
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "percent": usage.percent
                })
            except PermissionError:
                continue
        
        io_counters = psutil.disk_io_counters()
        
        data = {
            "partitions": partitions,
            "io": {
                "read_bytes": io_counters.read_bytes if io_counters else 0,
                "write_bytes": io_counters.write_bytes if io_counters else 0,
                "read_count": io_counters.read_count if io_counters else 0,
                "write_count": io_counters.write_count if io_counters else 0
            }
        }
        
        return ToolResult(success=True, data=data)
    
    async def _get_network(self) -> ToolResult:
        """Get network information"""
        interfaces = {}
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        
        for name, addresses in addrs.items():
            interfaces[name] = {
                "addresses": [],
                "is_up": stats[name].isup if name in stats else False,
                "speed_mbps": stats[name].speed if name in stats else 0
            }
            for addr in addresses:
                interfaces[name]["addresses"].append({
                    "family": str(addr.family),
                    "address": addr.address,
                    "netmask": addr.netmask
                })
        
        io_counters = psutil.net_io_counters()
        
        data = {
            "interfaces": interfaces,
            "io": {
                "bytes_sent": io_counters.bytes_sent,
                "bytes_recv": io_counters.bytes_recv,
                "packets_sent": io_counters.packets_sent,
                "packets_recv": io_counters.packets_recv
            }
        }
        
        return ToolResult(success=True, data=data)
    
    async def _get_battery(self) -> ToolResult:
        """Get battery information"""
        battery = psutil.sensors_battery()
        
        if battery is None:
            return ToolResult(success=True, data={"available": False, "message": "没有检测到电池"})
        
        data = {
            "available": True,
            "percent": battery.percent,
            "power_plugged": battery.power_plugged,
            "seconds_left": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else None,
            "status": "充电中" if battery.power_plugged else "使用电池"
        }
        
        return ToolResult(success=True, data=data)
    
    async def _get_processes(self, sort_by: str, limit: int) -> ToolResult:
        """Get running processes"""
        processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
            try:
                info = proc.info
                processes.append({
                    "pid": info['pid'],
                    "name": info['name'],
                    "cpu_percent": info['cpu_percent'] or 0,
                    "memory_percent": round(info['memory_percent'] or 0, 2),
                    "status": info['status']
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if sort_by == "cpu":
            processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
        elif sort_by == "memory":
            processes.sort(key=lambda x: x['memory_percent'], reverse=True)
        else:
            processes.sort(key=lambda x: x['name'].lower())
        
        return ToolResult(success=True, data={
            "processes": processes[:limit],
            "total_count": len(processes)
        })
