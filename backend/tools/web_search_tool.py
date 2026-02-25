"""
Web Search Tool - 联网搜索能力
为本地模型提供获取实时信息的"眼睛"

支持多种搜索引擎和信息来源：
- DuckDuckGo (免费，无需 API Key)
- Google Custom Search (需要 API Key)
- Bing Search (需要 API Key)
- 网页内容抓取
- 新闻搜索
- 学术搜索
"""

import os
import re
import json
import asyncio
import urllib.parse
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from .base import BaseTool, ToolResult, ToolCategory

import logging
logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """搜索结果"""
    title: str
    url: str
    snippet: str
    source: str = ""
    published_date: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
            "published_date": self.published_date
        }


class WebSearchTool(BaseTool):
    """
    联网搜索工具
    为 Agent 提供获取实时信息的能力
    """
    
    name = "web_search"
    description = "联网搜索：搜索网页、新闻、获取实时信息"
    category = ToolCategory.BROWSER
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "search",           # 通用搜索
                    "news",             # 新闻搜索
                    "fetch_page",       # 获取网页内容
                    "extract_text",     # 提取网页文本
                    "summarize_url",    # 总结网页内容
                    "search_images",    # 图片搜索
                    "answer_question",  # 直接回答问题
                    "get_weather",      # 获取天气
                    "get_stock",        # 获取股票信息
                    "translate"         # 翻译
                ],
                "description": "搜索操作类型"
            },
            "query": {
                "type": "string",
                "description": "搜索关键词或问题。get_stock 时请传入股票代码（如 002195、AAPL）或中文名称（如 上证指数）"
            },
            "url": {
                "type": "string",
                "description": "要获取的网页 URL"
            },
            "num_results": {
                "type": "number",
                "description": "返回结果数量，默认 5"
            },
            "language": {
                "type": "string",
                "description": "搜索语言 (zh-CN, en-US)"
            },
            "region": {
                "type": "string",
                "description": "搜索区域"
            },
            "time_range": {
                "type": "string",
                "enum": ["day", "week", "month", "year"],
                "description": "时间范围"
            },
            "source_lang": {
                "type": "string",
                "description": "翻译源语言"
            },
            "target_lang": {
                "type": "string",
                "description": "翻译目标语言"
            }
        },
        "required": ["action"]
    }
    
    def __init__(self, runtime_adapter=None):
        super().__init__(runtime_adapter)
        # API Keys from environment
        self.google_api_key = os.getenv("GOOGLE_API_KEY", "")
        self.google_cx = os.getenv("GOOGLE_CX", "")
        self.bing_api_key = os.getenv("BING_API_KEY", "")
        
    async def execute(
        self,
        action: str,
        query: Optional[str] = None,
        url: Optional[str] = None,
        num_results: int = 5,
        language: str = "zh-CN",
        region: str = "cn",
        time_range: Optional[str] = None,
        source_lang: str = "auto",
        target_lang: str = "zh-CN"
    ) -> ToolResult:
        """执行搜索操作"""
        
        actions = {
            "search": lambda: self._search(query, num_results, language, region, time_range),
            "news": lambda: self._search_news(query, num_results, language),
            "fetch_page": lambda: self._fetch_page(url),
            "extract_text": lambda: self._extract_text(url),
            "summarize_url": lambda: self._summarize_url(url),
            "search_images": lambda: self._search_images(query, num_results),
            "answer_question": lambda: self._answer_question(query),
            "get_weather": lambda: self._get_weather(query),
            "get_stock": lambda: self._get_stock(query),
            "translate": lambda: self._translate(query, source_lang, target_lang),
        }
        
        if action not in actions:
            return ToolResult(success=False, error=f"未知操作: {action}")
        
        return await actions[action]()
    
    async def _search(
        self,
        query: str,
        num_results: int,
        language: str,
        region: str,
        time_range: Optional[str]
    ) -> ToolResult:
        """通用搜索（使用 DuckDuckGo）"""
        if not query:
            return ToolResult(success=False, error="需要搜索关键词")
        
        try:
            # 尝试使用 duckduckgo_search 库
            results = await self._duckduckgo_search(query, num_results, region)
            
            if results:
                return ToolResult(success=True, data={
                    "query": query,
                    "results": [r.to_dict() for r in results],
                    "count": len(results),
                    "source": "DuckDuckGo"
                })
            
            # 备用：使用网页抓取方式
            return await self._fallback_search(query, num_results)
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return await self._fallback_search(query, num_results)
    
    async def _duckduckgo_search(
        self,
        query: str,
        num_results: int,
        region: str
    ) -> List[SearchResult]:
        """使用 DuckDuckGo 搜索"""
        try:
            from duckduckgo_search import DDGS
            
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, region=region, max_results=num_results):
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        url=r.get("href", ""),
                        snippet=r.get("body", ""),
                        source="DuckDuckGo"
                    ))
            return results
            
        except ImportError:
            logger.warning("duckduckgo_search not installed, using fallback")
            return []
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return []
    
    async def _fallback_search(self, query: str, num_results: int) -> ToolResult:
        """备用搜索方法：使用 curl 抓取搜索结果页"""
        try:
            import httpx
            
            # 使用 DuckDuckGo HTML 版本
            encoded_query = urllib.parse.quote(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=10)
                html = response.text
            
            # 简单解析结果
            results = self._parse_ddg_html(html, num_results)
            
            return ToolResult(success=True, data={
                "query": query,
                "results": [r.to_dict() for r in results],
                "count": len(results),
                "source": "DuckDuckGo (HTML)"
            })
            
        except Exception as e:
            return ToolResult(success=False, error=f"搜索失败: {str(e)}")
    
    def _parse_ddg_html(self, html: str, max_results: int) -> List[SearchResult]:
        """解析 DuckDuckGo HTML 结果"""
        results = []
        
        # 简单的正则匹配
        pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>([^<]+)</a>'
        matches = re.findall(pattern, html)
        
        for url, title in matches[:max_results]:
            # 提取摘要
            snippet_pattern = rf'{re.escape(title)}.*?<a class="result__snippet"[^>]*>([^<]+)</a>'
            snippet_match = re.search(snippet_pattern, html, re.DOTALL)
            snippet = snippet_match.group(1) if snippet_match else ""
            
            results.append(SearchResult(
                title=title.strip(),
                url=url,
                snippet=snippet.strip(),
                source="DuckDuckGo"
            ))
        
        return results
    
    async def _search_news(
        self,
        query: str,
        num_results: int,
        language: str
    ) -> ToolResult:
        """新闻搜索"""
        if not query:
            return ToolResult(success=False, error="需要搜索关键词")
        
        try:
            from duckduckgo_search import DDGS
            
            results = []
            with DDGS() as ddgs:
                for r in ddgs.news(query, max_results=num_results):
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        snippet=r.get("body", ""),
                        source=r.get("source", ""),
                        published_date=r.get("date", "")
                    ))
            
            return ToolResult(success=True, data={
                "query": query,
                "news": [r.to_dict() for r in results],
                "count": len(results)
            })
            
        except ImportError:
            # 备用方案：使用 Google News RSS
            return await self._search_news_rss(query, num_results)
        except Exception as e:
            return ToolResult(success=False, error=f"新闻搜索失败: {str(e)}")
    
    async def _search_news_rss(self, query: str, num_results: int) -> ToolResult:
        """使用 Google News RSS 搜索新闻"""
        try:
            import httpx
            import xml.etree.ElementTree as ET
            
            encoded_query = urllib.parse.quote(query)
            url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10)
                xml_content = response.text
            
            root = ET.fromstring(xml_content)
            
            results = []
            for item in root.findall(".//item")[:num_results]:
                title = item.find("title")
                link = item.find("link")
                pub_date = item.find("pubDate")
                source = item.find("source")
                
                results.append({
                    "title": title.text if title is not None else "",
                    "url": link.text if link is not None else "",
                    "published_date": pub_date.text if pub_date is not None else "",
                    "source": source.text if source is not None else ""
                })
            
            return ToolResult(success=True, data={
                "query": query,
                "news": results,
                "count": len(results)
            })
            
        except Exception as e:
            return ToolResult(success=False, error=f"新闻 RSS 获取失败: {str(e)}")
    
    async def _fetch_page(self, url: str) -> ToolResult:
        """获取网页内容"""
        if not url:
            return ToolResult(success=False, error="需要 URL")
        
        try:
            import httpx
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, headers=headers, timeout=15)
                
                content_type = response.headers.get("content-type", "")
                
                if "text/html" in content_type:
                    html = response.text
                    # 限制大小
                    if len(html) > 100000:
                        html = html[:100000] + "\n... (truncated)"
                    
                    return ToolResult(success=True, data={
                        "url": url,
                        "content_type": content_type,
                        "html": html,
                        "status_code": response.status_code
                    })
                else:
                    return ToolResult(success=True, data={
                        "url": url,
                        "content_type": content_type,
                        "size": len(response.content),
                        "status_code": response.status_code
                    })
                    
        except Exception as e:
            return ToolResult(success=False, error=f"获取网页失败: {str(e)}")
    
    async def _extract_text(self, url: str) -> ToolResult:
        """提取网页纯文本"""
        if not url:
            return ToolResult(success=False, error="需要 URL")
        
        try:
            import httpx
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, headers=headers, timeout=15)
                html = response.text
            
            # 尝试使用 BeautifulSoup
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                
                # 移除脚本和样式
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                
                # 获取标题
                title = soup.title.string if soup.title else ""
                
                # 获取主要内容
                main_content = soup.find("main") or soup.find("article") or soup.body
                text = main_content.get_text(separator="\n", strip=True) if main_content else ""
                
                # 清理多余空行
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                text = "\n".join(lines)
                
                # 限制长度
                if len(text) > 10000:
                    text = text[:10000] + "\n... (truncated)"
                
                return ToolResult(success=True, data={
                    "url": url,
                    "title": title,
                    "text": text,
                    "char_count": len(text)
                })
                
            except ImportError:
                # 简单的正则提取
                text = self._simple_extract_text(html)
                return ToolResult(success=True, data={
                    "url": url,
                    "text": text[:10000],
                    "char_count": len(text),
                    "note": "使用简单提取（安装 beautifulsoup4 获得更好效果）"
                })
                
        except Exception as e:
            return ToolResult(success=False, error=f"提取文本失败: {str(e)}")
    
    def _simple_extract_text(self, html: str) -> str:
        """简单的文本提取"""
        # 移除脚本和样式
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # 移除 HTML 标签
        text = re.sub(r'<[^>]+>', ' ', html)
        # 清理空白
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    async def _summarize_url(self, url: str) -> ToolResult:
        """总结网页内容（获取主要信息）"""
        # 先提取文本
        extract_result = await self._extract_text(url)
        
        if not extract_result.success:
            return extract_result
        
        text = extract_result.data.get("text", "")
        title = extract_result.data.get("title", "")
        
        # 提取关键段落（前几段通常是摘要）
        paragraphs = text.split("\n")
        key_paragraphs = [p for p in paragraphs if len(p) > 50][:5]
        
        return ToolResult(success=True, data={
            "url": url,
            "title": title,
            "summary": "\n\n".join(key_paragraphs),
            "full_text_length": len(text)
        })
    
    async def _search_images(self, query: str, num_results: int) -> ToolResult:
        """图片搜索"""
        if not query:
            return ToolResult(success=False, error="需要搜索关键词")
        
        try:
            from duckduckgo_search import DDGS
            
            results = []
            with DDGS() as ddgs:
                for r in ddgs.images(query, max_results=num_results):
                    results.append({
                        "title": r.get("title", ""),
                        "image_url": r.get("image", ""),
                        "thumbnail": r.get("thumbnail", ""),
                        "source": r.get("source", ""),
                        "url": r.get("url", "")
                    })
            
            return ToolResult(success=True, data={
                "query": query,
                "images": results,
                "count": len(results)
            })
            
        except ImportError:
            return ToolResult(success=False, error="需要安装 duckduckgo_search: pip install duckduckgo_search")
        except Exception as e:
            return ToolResult(success=False, error=f"图片搜索失败: {str(e)}")
    
    async def _answer_question(self, query: str) -> ToolResult:
        """直接回答问题（使用 DuckDuckGo Instant Answer）"""
        if not query:
            return ToolResult(success=False, error="需要问题")
        
        try:
            import httpx
            
            encoded_query = urllib.parse.quote(query)
            url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10)
                data = response.json()
            
            # 提取答案
            answer = data.get("AbstractText") or data.get("Answer") or data.get("Definition")
            
            if answer:
                return ToolResult(success=True, data={
                    "query": query,
                    "answer": answer,
                    "source": data.get("AbstractSource", ""),
                    "url": data.get("AbstractURL", ""),
                    "type": data.get("Type", "")
                })
            
            # 如果没有即时答案，返回相关主题
            related = data.get("RelatedTopics", [])
            if related:
                topics = []
                for topic in related[:5]:
                    if isinstance(topic, dict) and "Text" in topic:
                        topics.append({
                            "text": topic.get("Text", ""),
                            "url": topic.get("FirstURL", "")
                        })
                
                return ToolResult(success=True, data={
                    "query": query,
                    "answer": None,
                    "related_topics": topics,
                    "note": "无即时答案，返回相关主题"
                })
            
            return ToolResult(success=True, data={
                "query": query,
                "answer": None,
                "note": "无法找到即时答案，请尝试搜索"
            })
            
        except Exception as e:
            return ToolResult(success=False, error=f"回答失败: {str(e)}")
    
    async def _get_weather(self, location: str) -> ToolResult:
        """获取天气信息"""
        if not location:
            return ToolResult(success=False, error="需要位置")
        
        import httpx
        
        logger.info(f"Getting weather for location: {location}")
        
        # 尝试多个天气 API
        errors = []
        
        # 方法1：wttr.in
        try:
            encoded_location = urllib.parse.quote(location)
            url = f"https://wttr.in/{encoded_location}?format=j1"
            
            logger.info(f"Trying wttr.in: {url}")
            
            headers = {
                "User-Agent": "curl/7.64.1",
                "Accept": "application/json"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=15)
                
                logger.info(f"wttr.in response status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"wttr.in data received: {len(str(data))} bytes")
                    
                    current = data.get("current_condition", [{}])[0]
                    area = data.get("nearest_area", [{}])[0]
                    
                    weather = {
                        "location": area.get("areaName", [{}])[0].get("value", location),
                        "country": area.get("country", [{}])[0].get("value", ""),
                        "temperature_c": current.get("temp_C", ""),
                        "temperature_f": current.get("temp_F", ""),
                        "feels_like_c": current.get("FeelsLikeC", ""),
                        "humidity": current.get("humidity", ""),
                        "description": current.get("weatherDesc", [{}])[0].get("value", ""),
                        "wind_speed_kmh": current.get("windspeedKmph", ""),
                        "wind_direction": current.get("winddir16Point", ""),
                        "visibility_km": current.get("visibility", ""),
                        "uv_index": current.get("uvIndex", ""),
                        "observation_time": current.get("observation_time", "")
                    }
                    
                    forecast = []
                    for day in data.get("weather", [])[:3]:
                        hourly = day.get("hourly", [])
                        desc = ""
                        if len(hourly) > 4:
                            desc = hourly[4].get("weatherDesc", [{}])[0].get("value", "")
                        elif hourly:
                            desc = hourly[0].get("weatherDesc", [{}])[0].get("value", "")
                        
                        forecast.append({
                            "date": day.get("date", ""),
                            "max_temp_c": day.get("maxtempC", ""),
                            "min_temp_c": day.get("mintempC", ""),
                            "description": desc
                        })
                    
                    weather["forecast"] = forecast
                    return ToolResult(success=True, data=weather)
                    
        except Exception as e:
            errors.append(f"wttr.in: {str(e)}")
            logger.warning(f"wttr.in failed: {e}")
        
        # 方法2：使用 Open-Meteo (免费，无需 API Key)
        try:
            logger.info("Trying Open-Meteo API...")
            
            # 中国主要城市的拼音映射（提高准确性）
            city_pinyin = {
                "杭州": "Hangzhou", "北京": "Beijing", "上海": "Shanghai",
                "广州": "Guangzhou", "深圳": "Shenzhen", "成都": "Chengdu",
                "重庆": "Chongqing", "武汉": "Wuhan", "西安": "Xian",
                "南京": "Nanjing", "天津": "Tianjin", "苏州": "Suzhou",
                "长沙": "Changsha", "郑州": "Zhengzhou", "青岛": "Qingdao",
                "大连": "Dalian", "厦门": "Xiamen", "济南": "Jinan",
                "福州": "Fuzhou", "昆明": "Kunming", "合肥": "Hefei",
                "沈阳": "Shenyang", "哈尔滨": "Harbin", "南宁": "Nanning",
                "贵阳": "Guiyang", "太原": "Taiyuan", "石家庄": "Shijiazhuang",
                "兰州": "Lanzhou", "南昌": "Nanchang", "长春": "Changchun",
                "无锡": "Wuxi", "宁波": "Ningbo", "东莞": "Dongguan",
                "佛山": "Foshan", "温州": "Wenzhou", "绍兴": "Shaoxing",
            }
            
            # 使用拼音搜索提高准确性
            search_name = city_pinyin.get(location, location)
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(search_name)}&count=5&language=zh"
            
            async with httpx.AsyncClient() as client:
                geo_response = await client.get(geo_url, timeout=10)
                geo_data = geo_response.json()
                logger.info(f"Open-Meteo geocoding response: {geo_data}")
                
                results = geo_data.get("results", [])
                
                # 优先选择匹配的城市（检查 admin1 是否包含期望的省份）
                selected = None
                for r in results:
                    admin1 = r.get("admin1", "")
                    name = r.get("name", "")
                    # 如果是主要城市，选择匹配的那个
                    if location in name or name in location:
                        # 排除明显错误的匹配（如四川的杭州）
                        if location == "杭州" and "浙江" in admin1:
                            selected = r
                            break
                        elif location != "杭州":
                            selected = r
                            break
                
                # 如果没找到精确匹配，使用第一个结果
                if not selected and results:
                    selected = results[0]
                
                if selected:
                    lat = selected["latitude"]
                    lon = selected["longitude"]
                    city_name = selected.get("name", location)
                    country = selected.get("country", "")
                    admin1 = selected.get("admin1", "")
                    logger.info(f"Selected location: {city_name}, {admin1}, {country} ({lat}, {lon})")
                    
                    # 获取天气
                    weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&daily=weather_code,temperature_2m_max,temperature_2m_min&timezone=auto"
                    
                    weather_response = await client.get(weather_url, timeout=10)
                    weather_data = weather_response.json()
                    
                    current = weather_data.get("current", {})
                    daily = weather_data.get("daily", {})
                    
                    # 天气代码转描述
                    weather_codes = {
                        0: "晴朗", 1: "晴间多云", 2: "多云", 3: "阴天",
                        45: "雾", 48: "雾凇", 51: "小毛毛雨", 53: "毛毛雨",
                        55: "大毛毛雨", 61: "小雨", 63: "中雨", 65: "大雨",
                        71: "小雪", 73: "中雪", 75: "大雪", 80: "阵雨",
                        81: "中阵雨", 82: "大阵雨", 95: "雷暴"
                    }
                    
                    code = current.get("weather_code", 0)
                    desc = weather_codes.get(code, f"天气代码 {code}")
                    
                    weather = {
                        "location": city_name,
                        "country": country,
                        "temperature_c": str(current.get("temperature_2m", "")),
                        "humidity": str(current.get("relative_humidity_2m", "")),
                        "description": desc,
                        "wind_speed_kmh": str(current.get("wind_speed_10m", "")),
                        "source": "Open-Meteo"
                    }
                    
                    forecast = []
                    dates = daily.get("time", [])
                    max_temps = daily.get("temperature_2m_max", [])
                    min_temps = daily.get("temperature_2m_min", [])
                    codes = daily.get("weather_code", [])
                    
                    for i in range(min(3, len(dates))):
                        forecast.append({
                            "date": dates[i] if i < len(dates) else "",
                            "max_temp_c": str(max_temps[i]) if i < len(max_temps) else "",
                            "min_temp_c": str(min_temps[i]) if i < len(min_temps) else "",
                            "description": weather_codes.get(codes[i], "") if i < len(codes) else ""
                        })
                    
                    weather["forecast"] = forecast
                    return ToolResult(success=True, data=weather)
                    
        except Exception as e:
            errors.append(f"Open-Meteo: {str(e)}")
            logger.warning(f"Open-Meteo failed: {e}")
        
        # 方法3：搜索天气信息
        try:
            search_result = await self._search(f"{location} 天气 今天", 3, "zh-CN", "cn", None)
            if search_result.success:
                return ToolResult(success=True, data={
                    "location": location,
                    "note": "无法获取精确天气数据，以下是搜索结果",
                    "search_results": search_result.data.get("results", [])
                })
        except Exception as e:
            errors.append(f"search: {str(e)}")
        
        return ToolResult(success=False, error=f"获取天气失败: {'; '.join(errors)}")
    
    # A 股常用指数 / 股票中文名 → Yahoo Finance 代码映射
    _CN_STOCK_ALIASES: Dict[str, str] = {
        "上证指数": "000001.SS", "上证": "000001.SS", "沪指": "000001.SS",
        "深证成指": "399001.SZ", "深成指": "399001.SZ", "深指": "399001.SZ",
        "创业板指": "399006.SZ", "创业板": "399006.SZ",
        "科创50": "000688.SS", "科创板": "000688.SS",
        "沪深300": "000300.SS", "hs300": "000300.SS",
        "中证500": "000905.SS",
        "上证50": "000016.SS",
    }

    def _resolve_stock_symbol(self, raw: str) -> str:
        """将中文名称 / 纯数字代码转为 Yahoo Finance 可识别的 ticker"""
        raw = raw.strip()
        # 直接命中别名
        for alias, ticker in self._CN_STOCK_ALIASES.items():
            if alias in raw:
                return ticker
        # 纯 6 位数字 → 自动补后缀
        import re
        m = re.search(r"\b(\d{6})\b", raw)
        if m:
            code = m.group(1)
            if code.startswith(("6", "9")):
                return f"{code}.SS"
            elif code.startswith(("0", "3", "2")):
                return f"{code}.SZ"
            return code
        # 已含 .SS / .SZ / .HK 等后缀，直接返回
        if re.match(r"^[A-Za-z0-9.]+$", raw):
            return raw
        # 无法识别，返回原始值（大概率 404，由调用方处理）
        return raw

    async def _get_stock(self, symbol: str) -> ToolResult:
        """获取股票信息（支持 A 股中文名称、6 位代码、Yahoo ticker）"""
        if not symbol:
            return ToolResult(success=False, error="需要股票代码或名称，例如 '上证指数'、'002195'、'AAPL'")

        resolved = self._resolve_stock_symbol(symbol)

        try:
            import httpx

            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{resolved}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=10)
                if response.status_code == 404:
                    return ToolResult(
                        success=False,
                        error=f"未找到股票 '{symbol}'（解析为 {resolved}）。请使用标准代码，如 '000001'（上证指数）、'002195'（岩山科技）、'AAPL'。",
                    )
                data = response.json()

            chart = data.get("chart", {}).get("result", [{}])[0]
            meta = chart.get("meta", {})

            stock_info = {
                "symbol": meta.get("symbol", resolved),
                "name": meta.get("longName", "") or meta.get("shortName", ""),
                "currency": meta.get("currency", ""),
                "exchange": meta.get("exchangeName", ""),
                "current_price": meta.get("regularMarketPrice", ""),
                "previous_close": meta.get("previousClose", ""),
                "market_state": meta.get("marketState", ""),
                "timezone": meta.get("timezone", ""),
                "query": symbol,
            }

            if stock_info["current_price"] and stock_info["previous_close"]:
                change = float(stock_info["current_price"]) - float(stock_info["previous_close"])
                change_percent = (change / float(stock_info["previous_close"])) * 100
                stock_info["change"] = round(change, 2)
                stock_info["change_percent"] = round(change_percent, 2)

            return ToolResult(success=True, data=stock_info)

        except Exception as e:
            return ToolResult(success=False, error=f"获取股票信息失败 ({resolved}): {str(e)}")
    
    async def _translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> ToolResult:
        """翻译文本"""
        if not text:
            return ToolResult(success=False, error="需要翻译文本")
        
        try:
            import httpx
            
            # 使用 Google Translate 免费 API
            url = "https://translate.googleapis.com/translate_a/single"
            
            params = {
                "client": "gtx",
                "sl": source_lang if source_lang != "auto" else "auto",
                "tl": target_lang.split("-")[0],  # zh-CN -> zh
                "dt": "t",
                "q": text
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=10)
                data = response.json()
            
            # 解析翻译结果
            translated_parts = []
            if data and data[0]:
                for part in data[0]:
                    if part and part[0]:
                        translated_parts.append(part[0])
            
            translated_text = "".join(translated_parts)
            detected_lang = data[2] if len(data) > 2 else source_lang
            
            return ToolResult(success=True, data={
                "original": text,
                "translated": translated_text,
                "source_language": detected_lang,
                "target_language": target_lang
            })
            
        except Exception as e:
            return ToolResult(success=False, error=f"翻译失败: {str(e)}")


class WikipediaTool(BaseTool):
    """
    Wikipedia 搜索工具
    获取百科知识
    """
    
    name = "wikipedia"
    description = "维基百科搜索：获取百科知识、定义、解释"
    category = ToolCategory.BROWSER
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "summary", "full_page"],
                "description": "操作类型"
            },
            "query": {
                "type": "string",
                "description": "搜索关键词"
            },
            "language": {
                "type": "string",
                "description": "语言代码 (zh, en)"
            }
        },
        "required": ["action", "query"]
    }
    
    async def execute(
        self,
        action: str,
        query: str,
        language: str = "zh"
    ) -> ToolResult:
        """执行 Wikipedia 操作"""
        
        if action == "search":
            return await self._search(query, language)
        elif action == "summary":
            return await self._get_summary(query, language)
        elif action == "full_page":
            return await self._get_full_page(query, language)
        else:
            return ToolResult(success=False, error=f"未知操作: {action}")
    
    async def _search(self, query: str, language: str) -> ToolResult:
        """搜索 Wikipedia 条目"""
        try:
            import httpx
            
            url = f"https://{language}.wikipedia.org/w/api.php"
            params = {
                "action": "opensearch",
                "search": query,
                "limit": 10,
                "namespace": 0,
                "format": "json"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=10)
                data = response.json()
            
            # OpenSearch 返回 [query, [titles], [descriptions], [urls]]
            if len(data) >= 4:
                results = []
                for i, title in enumerate(data[1]):
                    results.append({
                        "title": title,
                        "description": data[2][i] if i < len(data[2]) else "",
                        "url": data[3][i] if i < len(data[3]) else ""
                    })
                
                return ToolResult(success=True, data={
                    "query": query,
                    "results": results
                })
            
            return ToolResult(success=True, data={"query": query, "results": []})
            
        except Exception as e:
            return ToolResult(success=False, error=f"Wikipedia 搜索失败: {str(e)}")
    
    async def _get_summary(self, query: str, language: str) -> ToolResult:
        """获取条目摘要"""
        try:
            import httpx
            
            url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(query)}"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10)
                
                if response.status_code == 404:
                    return ToolResult(success=False, error=f"找不到条目: {query}")
                
                data = response.json()
            
            return ToolResult(success=True, data={
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "extract": data.get("extract", ""),
                "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                "thumbnail": data.get("thumbnail", {}).get("source", "")
            })
            
        except Exception as e:
            return ToolResult(success=False, error=f"获取摘要失败: {str(e)}")
    
    async def _get_full_page(self, query: str, language: str) -> ToolResult:
        """获取完整页面内容"""
        try:
            import httpx
            
            url = f"https://{language}.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "titles": query,
                "prop": "extracts",
                "exintro": False,
                "explaintext": True,
                "format": "json"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=15)
                data = response.json()
            
            pages = data.get("query", {}).get("pages", {})
            
            for page_id, page in pages.items():
                if page_id != "-1":
                    content = page.get("extract", "")
                    # 限制长度
                    if len(content) > 15000:
                        content = content[:15000] + "\n... (truncated)"
                    
                    return ToolResult(success=True, data={
                        "title": page.get("title", ""),
                        "content": content,
                        "page_id": page_id
                    })
            
            return ToolResult(success=False, error=f"找不到条目: {query}")
            
        except Exception as e:
            return ToolResult(success=False, error=f"获取页面失败: {str(e)}")
