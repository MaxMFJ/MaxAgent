"""
Network Tool - 网络管理
"""

import asyncio
from typing import Optional
from .base import BaseTool, ToolResult, ToolCategory


class NetworkTool(BaseTool):
    """网络管理工具"""
    
    name = "network"
    description = "网络管理：WiFi控制、网络检测、端口扫描"
    category = ToolCategory.SYSTEM
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "status", "wifi_list", "wifi_connect", "wifi_disconnect",
                    "ping", "dns_lookup", "port_check", "ip_info",
                    "http_request", "speed_test"
                ],
                "description": "网络操作"
            },
            "host": {
                "type": "string",
                "description": "主机名或 IP 地址"
            },
            "port": {
                "type": "number",
                "description": "端口号"
            },
            "ssid": {
                "type": "string",
                "description": "WiFi 名称"
            },
            "password": {
                "type": "string",
                "description": "WiFi 密码"
            },
            "url": {
                "type": "string",
                "description": "HTTP 请求 URL"
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE"],
                "description": "HTTP 方法"
            }
        },
        "required": ["action"]
    }
    
    async def execute(
        self,
        action: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        ssid: Optional[str] = None,
        password: Optional[str] = None,
        url: Optional[str] = None,
        method: str = "GET"
    ) -> ToolResult:
        """执行网络操作"""
        
        actions = {
            "status": self._get_network_status,
            "wifi_list": self._list_wifi,
            "wifi_connect": lambda: self._connect_wifi(ssid, password),
            "wifi_disconnect": self._disconnect_wifi,
            "ping": lambda: self._ping(host),
            "dns_lookup": lambda: self._dns_lookup(host),
            "port_check": lambda: self._check_port(host, port),
            "ip_info": self._get_ip_info,
            "http_request": lambda: self._http_request(url, method),
            "speed_test": self._speed_test,
        }
        
        if action not in actions:
            return ToolResult(success=False, error=f"未知操作: {action}")
        
        return await actions[action]()
    
    async def _run_cmd(self, cmd: list) -> tuple[bool, str]:
        """执行命令"""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return False, stderr.decode().strip()
            return True, stdout.decode().strip()
        except Exception as e:
            return False, str(e)
    
    async def _get_network_status(self) -> ToolResult:
        """获取网络状态"""
        # 获取当前 WiFi 名称
        success, ssid = await self._run_cmd([
            "networksetup", "-getairportnetwork", "en0"
        ])
        
        # 获取 IP 地址
        _, ip_info = await self._run_cmd(["ifconfig", "en0"])
        
        # 提取 IP
        import re
        ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', ip_info)
        ip = ip_match.group(1) if ip_match else "未知"
        
        # 检查网络连接
        ping_success, _ = await self._run_cmd(["ping", "-c", "1", "-W", "2", "8.8.8.8"])
        
        return ToolResult(success=True, data={
            "wifi": ssid.replace("Current Wi-Fi Network: ", "") if success else "未连接",
            "ip_address": ip,
            "internet_connected": ping_success
        })
    
    async def _list_wifi(self) -> ToolResult:
        """列出可用 WiFi"""
        success, result = await self._run_cmd([
            "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport",
            "-s"
        ])
        
        if success:
            return ToolResult(success=True, data={"wifi_networks": result})
        return ToolResult(success=False, error=result)
    
    async def _connect_wifi(self, ssid: str, password: Optional[str]) -> ToolResult:
        """连接 WiFi"""
        if not ssid:
            return ToolResult(success=False, error="需要 WiFi 名称")
        
        cmd = ["networksetup", "-setairportnetwork", "en0", ssid]
        if password:
            cmd.append(password)
        
        success, result = await self._run_cmd(cmd)
        
        if success:
            return ToolResult(success=True, data={"message": f"已连接到 {ssid}"})
        return ToolResult(success=False, error=result)
    
    async def _disconnect_wifi(self) -> ToolResult:
        """断开 WiFi"""
        success, result = await self._run_cmd([
            "networksetup", "-setairportpower", "en0", "off"
        ])
        
        if success:
            # 重新打开 WiFi
            await self._run_cmd(["networksetup", "-setairportpower", "en0", "on"])
            return ToolResult(success=True, data={"message": "WiFi 已断开"})
        return ToolResult(success=False, error=result)
    
    async def _ping(self, host: str) -> ToolResult:
        """Ping 主机"""
        if not host:
            return ToolResult(success=False, error="需要主机名")
        
        success, result = await self._run_cmd(["ping", "-c", "4", host])
        
        if success:
            return ToolResult(success=True, data={"ping_result": result})
        return ToolResult(success=False, error=result)
    
    async def _dns_lookup(self, host: str) -> ToolResult:
        """DNS 查询"""
        if not host:
            return ToolResult(success=False, error="需要主机名")
        
        success, result = await self._run_cmd(["nslookup", host])
        
        if success:
            return ToolResult(success=True, data={"dns_result": result})
        return ToolResult(success=False, error=result)
    
    async def _check_port(self, host: str, port: int) -> ToolResult:
        """检查端口是否开放"""
        if not host or not port:
            return ToolResult(success=False, error="需要主机名和端口")
        
        success, result = await self._run_cmd([
            "nc", "-zv", "-w", "3", host, str(port)
        ])
        
        return ToolResult(success=True, data={
            "host": host,
            "port": port,
            "open": success,
            "result": result
        })
    
    async def _get_ip_info(self) -> ToolResult:
        """获取公网 IP 信息"""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get("https://ipinfo.io/json", timeout=5)
                data = response.json()
                return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def _http_request(self, url: str, method: str) -> ToolResult:
        """发送 HTTP 请求"""
        if not url:
            return ToolResult(success=False, error="需要 URL")
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                if method == "GET":
                    response = await client.get(url, timeout=10)
                elif method == "POST":
                    response = await client.post(url, timeout=10)
                elif method == "PUT":
                    response = await client.put(url, timeout=10)
                elif method == "DELETE":
                    response = await client.delete(url, timeout=10)
                else:
                    return ToolResult(success=False, error=f"不支持的方法: {method}")
                
                return ToolResult(success=True, data={
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.text[:2000] if len(response.text) > 2000 else response.text
                })
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def _speed_test(self) -> ToolResult:
        """简单的网速测试"""
        import time
        
        try:
            import httpx
            
            # 下载测试文件
            test_url = "http://speedtest.tele2.net/1MB.zip"
            
            start_time = time.time()
            async with httpx.AsyncClient() as client:
                response = await client.get(test_url, timeout=30)
                content = response.content
            
            elapsed = time.time() - start_time
            size_mb = len(content) / (1024 * 1024)
            speed_mbps = (size_mb * 8) / elapsed  # Mbps
            
            return ToolResult(success=True, data={
                "download_speed_mbps": round(speed_mbps, 2),
                "downloaded_mb": round(size_mb, 2),
                "elapsed_seconds": round(elapsed, 2)
            })
        except Exception as e:
            return ToolResult(success=False, error=str(e))
