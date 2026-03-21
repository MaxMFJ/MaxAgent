"""
Web Search Tool - 联网搜索能力
为本地模型提供获取实时信息的"眼睛"

支持多种搜索引擎和信息来源：
- Jina Search / Reader（结果更适合 LLM，需 JINA_API_KEY）
- SearXNG（自托管元搜索，需 SEARXNG_URL）
- DuckDuckGo（免费，无需 API Key）
- 网页内容抓取 / 纯文本提取
- 新闻搜索
"""

import os
import re
import json
import asyncio
import urllib.parse
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from .base import BaseTool, ToolResult, ToolCategory
from .web_result_utils import compact_web_payload, extract_highlights_from_text, truncate_text

import logging
logger = logging.getLogger(__name__)

# Wikipedia 要求请求带 User-Agent，否则易返回 403 Forbidden
WIKIPEDIA_USER_AGENT = "ChowDuck/1.0 (Wikipedia summary client; +https://www.mediawiki.org/wiki/API:Main_page)"


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
                    "research",         # 深度研究
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
        self.jina_api_key = os.getenv("JINA_API_KEY", "")
        self.searxng_url = os.getenv("SEARXNG_URL", "").rstrip("/")
        self.web_search_backend = os.getenv("WEB_SEARCH_BACKEND", "auto").strip().lower()
        self.web_read_backend = os.getenv("WEB_READ_BACKEND", "auto").strip().lower()
        self.web_timeout = float(os.getenv("WEB_SEARCH_TIMEOUT", "15"))
        self.jina_token_budget = os.getenv("JINA_TOKEN_BUDGET", "8000")
        self.research_max_pages = max(2, min(int(os.getenv("WEB_RESEARCH_MAX_PAGES", "5")), 8))
        self.research_excerpt_chars = max(400, min(int(os.getenv("WEB_RESEARCH_EXCERPT_CHARS", "1600")), 4000))
        self.crawl4ai_headless = os.getenv("CRAWL4AI_HEADLESS", "true").lower() != "false"
        
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
            "research": lambda: self._research(query, num_results, language, region, time_range),
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
        """通用搜索（支持 Jina / SearXNG / DuckDuckGo 多后端）"""
        if not query:
            return ToolResult(success=False, error="需要搜索关键词")

        errors: List[str] = []
        for backend in self._search_backend_chain():
            try:
                if backend == "jina":
                    results = await self._jina_search(query, num_results, region, search_type="web")
                    if results:
                        return self._format_search_result(query, results, backend="jina", source="Jina Search")
                    errors.append("jina: no results")
                elif backend == "searxng":
                    results = await self._searxng_search(query, num_results, language, time_range, categories=None)
                    if results:
                        return self._format_search_result(query, results, backend="searxng", source="SearXNG")
                    errors.append("searxng: no results")
                elif backend == "ddg":
                    results = await self._duckduckgo_search(query, num_results, region)
                    if results:
                        return self._format_search_result(query, results, backend="ddg", source="DuckDuckGo")
                    errors.append("ddg: no results")
                elif backend == "ddg_html":
                    fallback = await self._fallback_search(query, num_results)
                    if fallback.success and fallback.data.get("count", 0) > 0:
                        return fallback
                    errors.append(f"ddg_html: {fallback.error or 'no results'}")
            except Exception as e:
                logger.warning("Search backend %s failed: %s", backend, e)
                errors.append(f"{backend}: {e}")

        return ToolResult(success=False, error=f"搜索失败: {' | '.join(errors[-4:]) or 'no backend available'}")

    async def _research(
        self,
        query: str,
        num_results: int,
        language: str,
        region: str,
        time_range: Optional[str],
    ) -> ToolResult:
        """多源搜索 + 正文抓取，面向 crawler / research 任务。"""
        if not query:
            return ToolResult(success=False, error="需要研究关键词")

        target_results = min(max(int(num_results or 5), 3), self.research_max_pages)
        search_tool_result = await self._search(query, target_results, language, region, time_range)
        if not search_tool_result.success:
            return search_tool_result

        search_data = search_tool_result.data or {}
        raw_results = search_data.get("results") or []
        if not raw_results:
            return ToolResult(success=True, data={
                "query": query,
                "findings": [],
                "count": 0,
                "search_backend": search_data.get("backend", ""),
                "research_backend": "none",
                "summary": "未获取到可用搜索结果。",
            })

        findings = await self._build_research_findings(raw_results[:target_results])
        payload = {
            "query": query,
            "findings": findings,
            "count": len(findings),
            "search_backend": search_data.get("backend", ""),
            "search_source": search_data.get("source", ""),
            "research_backend": self._resolve_research_backend(findings),
            "summary": self._summarize_findings(query, findings),
        }
        return ToolResult(success=True, data=compact_web_payload(payload, max_items=5, excerpt_chars=900))

    def _search_backend_chain(self) -> List[str]:
        """返回搜索后端优先级链。默认 auto = 免费优先，不自动走付费后端。"""
        explicit = self.web_search_backend
        if explicit in {"jina", "searxng", "ddg", "ddg_html"}:
            return [explicit]
        if explicit in {"hybrid", "best"}:
            chain: List[str] = []
            if self.jina_api_key:
                chain.append("jina")
            if self.searxng_url:
                chain.append("searxng")
            chain.extend(["ddg", "ddg_html"])
            return chain

        chain: List[str] = []
        if self.searxng_url:
            chain.append("searxng")
        chain.extend(["ddg", "ddg_html"])
        return chain

    def _read_backend_chain(self) -> List[str]:
        explicit = self.web_read_backend
        if explicit in {"jina", "builtin"}:
            return [explicit]
        if explicit in {"hybrid", "best"}:
            chain: List[str] = []
            if self.jina_api_key:
                chain.append("jina")
            chain.append("builtin")
            return chain

        return ["builtin"]

    def _research_backend_chain(self) -> List[str]:
        chain: List[str] = []
        if self._crawl4ai_available():
            chain.append("crawl4ai")
        chain.extend(self._read_backend_chain())
        return chain

    def _default_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _jina_headers(self, accept: str = "application/json") -> Dict[str, str]:
        headers = self._default_headers()
        headers["Accept"] = accept
        headers["Authorization"] = f"Bearer {self.jina_api_key}"
        headers["X-Token-Budget"] = self.jina_token_budget
        return headers

    def _format_search_result(
        self,
        query: str,
        results: List[SearchResult],
        backend: str,
        source: str,
        data_key: str = "results",
    ) -> ToolResult:
        return ToolResult(success=True, data={
            "query": query,
            data_key: [r.to_dict() for r in results],
            "count": len(results),
            "source": source,
            "backend": backend,
        })

    def _clean_snippet(self, text: Any, limit: int = 500) -> str:
        return truncate_text(text, limit)

    def _as_search_result(self, item: Dict[str, Any], default_source: str) -> Optional[SearchResult]:
        title = str(item.get("title") or item.get("name") or "").strip()
        url = str(item.get("url") or item.get("href") or item.get("link") or "").strip()
        snippet = self._clean_snippet(
            item.get("snippet")
            or item.get("description")
            or item.get("content")
            or item.get("body")
            or item.get("text")
            or ""
        )
        published_date = (
            item.get("published_date")
            or item.get("publishedDate")
            or item.get("date")
            or item.get("published")
        )
        source = str(item.get("source") or item.get("engine") or default_source)
        if not title and url:
            title = url
        if not url:
            return None
        return SearchResult(
            title=title,
            url=url,
            snippet=snippet,
            source=source,
            published_date=str(published_date) if published_date else None,
        )

    def _parse_generic_search_payload(self, payload: Any, default_source: str, max_results: int) -> List[SearchResult]:
        items: List[Dict[str, Any]] = []
        if isinstance(payload, list):
            items = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            for key in ("results", "data", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    items = [item for item in value if isinstance(item, dict)]
                    break

        results: List[SearchResult] = []
        for item in items[:max_results]:
            parsed = self._as_search_result(item, default_source)
            if parsed:
                results.append(parsed)
        return results

    async def _jina_search(
        self,
        query: str,
        num_results: int,
        region: str,
        search_type: str = "web",
    ) -> List[SearchResult]:
        if not self.jina_api_key:
            return []

        import httpx

        params: Dict[str, Any] = {"num": max(1, min(int(num_results), 10))}
        if search_type != "web":
            params["type"] = search_type
        if region:
            params["gl"] = region.lower()[:2]

        url = f"https://s.jina.ai/{urllib.parse.quote(query, safe='')}"
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                url,
                params=params,
                headers=self._jina_headers(),
                timeout=self.web_timeout,
            )
            response.raise_for_status()
            payload = response.json()

        return self._parse_generic_search_payload(payload, "Jina Search", num_results)

    async def _searxng_search(
        self,
        query: str,
        num_results: int,
        language: str,
        time_range: Optional[str],
        categories: Optional[str],
    ) -> List[SearchResult]:
        if not self.searxng_url:
            return []

        import httpx

        params: Dict[str, Any] = {
            "q": query,
            "format": "json",
            "language": language,
        }
        if categories:
            params["categories"] = categories
        if time_range:
            params["time_range"] = time_range

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                f"{self.searxng_url}/search",
                params=params,
                headers=self._default_headers(),
                timeout=self.web_timeout,
            )
            response.raise_for_status()
            payload = response.json()

        return self._parse_generic_search_payload(payload, "SearXNG", num_results)

    def _crawl4ai_available(self) -> bool:
        try:
            from crawl4ai import AsyncWebCrawler  # noqa: F401
            return True
        except Exception:
            return False

    async def _build_research_findings(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        crawl4ai_docs = await self._crawl4ai_fetch_many(items)
        for item in items:
            url = str(item.get("url") or "")
            doc = crawl4ai_docs.get(url)
            if doc is None:
                doc = await self._read_result_for_research(url)

            text = (doc or {}).get("text", "")
            snippet = self._clean_snippet(item.get("snippet") or item.get("body") or "", 260)
            excerpt = truncate_text(text, self.research_excerpt_chars) if text else ""
            findings.append({
                "title": str(item.get("title") or (doc or {}).get("title") or url),
                "url": url,
                "source": item.get("source", ""),
                "published_date": item.get("published_date"),
                "snippet": snippet,
                "content_excerpt": excerpt,
                "highlights": extract_highlights_from_text(excerpt or snippet, max_points=3, max_chars=180),
                "read_backend": (doc or {}).get("backend", ""),
            })
        return findings

    async def _crawl4ai_fetch_many(self, items: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
        urls = [str(item.get("url") or "") for item in items if item.get("url")]
        if not urls or not self._crawl4ai_available():
            return {}

        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

            browser_config = BrowserConfig(headless=self.crawl4ai_headless, verbose=False)
            run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
            docs: Dict[str, Dict[str, str]] = {}
            async with AsyncWebCrawler(config=browser_config) as crawler:
                for url in urls:
                    try:
                        result = await crawler.arun(url=url, config=run_config)
                        if not getattr(result, "success", True):
                            continue
                        text = (
                            getattr(result, "fit_markdown", None)
                            or getattr(result, "markdown", None)
                            or getattr(result, "cleaned_html", None)
                            or ""
                        )
                        text = str(text or "").strip()
                        if not text:
                            continue
                        docs[url] = {
                            "title": str(getattr(result, "title", "") or ""),
                            "text": text,
                            "backend": "crawl4ai",
                        }
                    except Exception as item_error:
                        logger.debug("Crawl4AI fetch failed for %s: %s", url, item_error)
            return docs
        except Exception as e:
            logger.warning("Crawl4AI unavailable or failed: %s", e)
            return {}

    async def _read_result_for_research(self, url: str) -> Dict[str, str]:
        if not url:
            return {}
        for backend in self._research_backend_chain():
            if backend == "crawl4ai":
                continue
            if backend == "jina":
                result = await self._extract_text_jina(url)
            else:
                result = await self._extract_text_builtin(url)
            if result.success:
                data = result.data or {}
                return {
                    "title": str(data.get("title") or ""),
                    "text": str(data.get("text") or data.get("content") or ""),
                    "backend": str(data.get("backend") or backend),
                }
        return {}

    def _summarize_findings(self, query: str, findings: List[Dict[str, Any]]) -> str:
        if not findings:
            return f"未针对「{query}」提取到可用正文。"

        lines = [f"围绕「{query}」共整理 {len(findings)} 个来源："]
        for idx, item in enumerate(findings[:4], start=1):
            title = truncate_text(item.get("title"), 70)
            highlights = item.get("highlights") or []
            if highlights:
                lines.append(f"{idx}. {title}：{highlights[0]}")
            else:
                lines.append(f"{idx}. {title}：{truncate_text(item.get('snippet'), 120)}")
        return "\n".join(lines)

    def _resolve_research_backend(self, findings: List[Dict[str, Any]]) -> str:
        backends: List[str] = []
        for item in findings:
            backend = str(item.get("read_backend") or "").strip()
            if backend and backend not in backends:
                backends.append(backend)
        return " -> ".join(backends) if backends else "none"
    
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
                "source": "DuckDuckGo (HTML)",
                "backend": "ddg_html",
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

        errors: List[str] = []
        for backend in self._search_backend_chain():
            try:
                if backend == "jina":
                    results = await self._jina_search(query, num_results, region="cn", search_type="news")
                    if results:
                        return self._format_search_result(query, results, backend="jina", source="Jina News", data_key="news")
                    errors.append("jina_news: no results")
                elif backend == "searxng":
                    results = await self._searxng_search(query, num_results, language, None, categories="news")
                    if results:
                        return self._format_search_result(query, results, backend="searxng", source="SearXNG", data_key="news")
                    errors.append("searxng_news: no results")
                elif backend == "ddg":
                    results = await self._duckduckgo_news(query, num_results)
                    if results:
                        return self._format_search_result(query, results, backend="ddg", source="DuckDuckGo", data_key="news")
                    errors.append("ddg_news: no results")
            except Exception as e:
                logger.warning("News backend %s failed: %s", backend, e)
                errors.append(f"{backend}: {e}")

        rss_result = await self._search_news_rss(query, num_results)
        if rss_result.success:
            return rss_result
        errors.append(rss_result.error or "google_news_rss failed")
        return ToolResult(success=False, error=f"新闻搜索失败: {' | '.join(errors[-4:])}")

    async def _duckduckgo_news(self, query: str, num_results: int) -> List[SearchResult]:
        try:
            from duckduckgo_search import DDGS

            results = []
            with DDGS() as ddgs:
                for r in ddgs.news(query, max_results=num_results):
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        snippet=r.get("body", ""),
                        source=r.get("source", "") or "DuckDuckGo",
                        published_date=r.get("date", ""),
                    ))
            return results
        except ImportError:
            return []
        except Exception as e:
            logger.error("DuckDuckGo news error: %s", e)
            return []
    
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
                "count": len(results),
                "source": "Google News RSS",
                "backend": "google_news_rss",
            })
            
        except Exception as e:
            return ToolResult(success=False, error=f"新闻 RSS 获取失败: {str(e)}")
    
    async def _fetch_page(self, url: str) -> ToolResult:
        """获取网页内容"""
        if not url:
            return ToolResult(success=False, error="需要 URL")

        builtin_result = await self._fetch_page_builtin(url)
        if builtin_result.success:
            return builtin_result

        for backend in self._read_backend_chain():
            if backend != "jina":
                continue
            reader_result = await self._extract_text_jina(url)
            if reader_result.success:
                data = reader_result.data or {}
                return ToolResult(success=True, data={
                    "url": url,
                    "content_type": "text/markdown",
                    "content": data.get("text", ""),
                    "title": data.get("title", ""),
                    "status_code": 200,
                    "backend": "jina_reader",
                    "note": "原始页面抓取失败，已回退到 Jina Reader 内容视图",
                })

        return builtin_result

    async def _fetch_page_builtin(self, url: str) -> ToolResult:
        try:
            import httpx

            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, headers=self._default_headers(), timeout=self.web_timeout)

                content_type = response.headers.get("content-type", "")
                if "text/html" in content_type:
                    html = response.text
                    if len(html) > 100000:
                        html = html[:100000] + "\n... (truncated)"

                    return ToolResult(success=True, data={
                        "url": url,
                        "content_type": content_type,
                        "html": html,
                        "status_code": response.status_code,
                        "backend": "builtin",
                    })
                return ToolResult(success=True, data={
                    "url": url,
                    "content_type": content_type,
                    "size": len(response.content),
                    "status_code": response.status_code,
                    "backend": "builtin",
                })
        except Exception as e:
            return ToolResult(success=False, error=f"获取网页失败: {str(e)}")
    
    async def _extract_text(self, url: str) -> ToolResult:
        """提取网页纯文本"""
        if not url:
            return ToolResult(success=False, error="需要 URL")

        errors: List[str] = []
        for backend in self._read_backend_chain():
            if backend == "jina":
                result = await self._extract_text_jina(url)
            else:
                result = await self._extract_text_builtin(url)

            if result.success:
                return result
            errors.append(result.error or f"{backend} failed")

        return ToolResult(success=False, error=f"提取文本失败: {' | '.join(errors[-3:])}")

    async def _extract_text_builtin(self, url: str) -> ToolResult:
        try:
            import httpx

            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, headers=self._default_headers(), timeout=self.web_timeout)
                html = response.text

            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")

                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()

                title = soup.title.string if soup.title else ""
                main_content = soup.find("main") or soup.find("article") or soup.body
                text = main_content.get_text(separator="\n", strip=True) if main_content else ""
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                text = "\n".join(lines)
                if len(text) > 10000:
                    text = text[:10000] + "\n... (truncated)"

                return ToolResult(success=True, data={
                    "url": url,
                    "title": title,
                    "text": text,
                    "char_count": len(text),
                    "backend": "builtin",
                })
            except ImportError:
                text = self._simple_extract_text(html)
                return ToolResult(success=True, data={
                    "url": url,
                    "text": text[:10000],
                    "char_count": len(text),
                    "backend": "builtin",
                    "note": "使用简单提取（安装 beautifulsoup4 获得更好效果）",
                })
        except Exception as e:
            return ToolResult(success=False, error=f"builtin 提取失败: {str(e)}")

    async def _extract_text_jina(self, url: str) -> ToolResult:
        if not self.jina_api_key:
            return ToolResult(success=False, error="未配置 JINA_API_KEY")

        try:
            import httpx

            reader_url = f"https://r.jina.ai/{url}"
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    reader_url,
                    headers=self._jina_headers(),
                    timeout=max(self.web_timeout, 20),
                )
                response.raise_for_status()
                payload = response.json()

            data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
            if not isinstance(data, dict):
                return ToolResult(success=False, error="Jina Reader 返回格式异常")

            title = str(data.get("title") or payload.get("title") or "")
            text = str(
                data.get("content")
                or data.get("text")
                or data.get("markdown")
                or payload.get("content")
                or payload.get("text")
                or ""
            )
            text = text.strip()
            if not text:
                return ToolResult(success=False, error="Jina Reader 未返回正文")
            if len(text) > 12000:
                text = text[:12000] + "\n... (truncated)"

            return ToolResult(success=True, data={
                "url": url,
                "title": title,
                "text": text,
                "char_count": len(text),
                "backend": "jina_reader",
            })
        except Exception as e:
            return ToolResult(success=False, error=f"jina_reader 提取失败: {str(e)}")
    
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
    
    # 中国主要城市的拼音映射（Open-Meteo geocoding 用拼音更准）
    _CITY_PINYIN = {
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
        "珠海": "Zhuhai", "中山": "Zhongshan", "惠州": "Huizhou",
        "汕头": "Shantou", "潮州": "Chaozhou", "湛江": "Zhanjiang",
        "桂林": "Guilin", "海口": "Haikou", "三亚": "Sanya",
        "拉萨": "Lhasa", "乌鲁木齐": "Urumqi", "呼和浩特": "Hohhot",
        "银川": "Yinchuan", "西宁": "Xining",
    }

    # 天气代码转描述（WMO 标准，Open-Meteo 使用）
    _WEATHER_CODES = {
        0: "晴朗", 1: "晴间多云", 2: "多云", 3: "阴天",
        45: "雾", 48: "雾凇", 51: "小毛毛雨", 53: "毛毛雨",
        55: "大毛毛雨", 61: "小雨", 63: "中雨", 65: "大雨",
        71: "小雪", 73: "中雪", 75: "大雪", 80: "阵雨",
        81: "中阵雨", 82: "大阵雨", 95: "雷暴",
    }

    async def _get_weather_open_meteo(self, location: str, errors: list) -> Optional[ToolResult]:
        """通过 Open-Meteo API 获取天气（国内访问快，~1-2s）"""
        import httpx
        try:
            logger.info(f"Trying Open-Meteo API for '{location}'...")
            search_name = self._CITY_PINYIN.get(location, location)
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(search_name)}&count=5&language=zh"

            async with httpx.AsyncClient() as client:
                geo_response = await client.get(geo_url, timeout=10)
                geo_data = geo_response.json()
                results = geo_data.get("results", [])

                selected = None
                for r in results:
                    admin1 = r.get("admin1", "")
                    name = r.get("name", "")
                    if location in name or name in location:
                        if location == "杭州" and "浙江" in admin1:
                            selected = r
                            break
                        elif location != "杭州":
                            selected = r
                            break
                if not selected and results:
                    selected = results[0]

                if not selected:
                    errors.append(f"Open-Meteo: 未找到位置 '{location}'")
                    return None

                lat = selected["latitude"]
                lon = selected["longitude"]
                city_name = selected.get("name", location)
                country = selected.get("country", "")
                admin1 = selected.get("admin1", "")
                logger.info(f"Open-Meteo location: {city_name}, {admin1}, {country} ({lat}, {lon})")

                weather_url = (
                    f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                    f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
                    f"&daily=weather_code,temperature_2m_max,temperature_2m_min&timezone=auto"
                )
                weather_response = await client.get(weather_url, timeout=10)
                weather_data = weather_response.json()

                current = weather_data.get("current", {})
                daily = weather_data.get("daily", {})
                code = current.get("weather_code", 0)
                desc = self._WEATHER_CODES.get(code, f"天气代码 {code}")

                weather = {
                    "location": city_name,
                    "country": country,
                    "temperature_c": str(current.get("temperature_2m", "")),
                    "humidity": str(current.get("relative_humidity_2m", "")),
                    "description": desc,
                    "wind_speed_kmh": str(current.get("wind_speed_10m", "")),
                    "source": "Open-Meteo",
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
                        "description": self._WEATHER_CODES.get(codes[i], "") if i < len(codes) else "",
                    })
                weather["forecast"] = forecast
                logger.info(f"Open-Meteo weather success: {city_name} {desc} {current.get('temperature_2m', '')}°C")
                return ToolResult(success=True, data=weather)

        except Exception as e:
            errors.append(f"Open-Meteo: {str(e)}")
            logger.warning(f"Open-Meteo failed: {e}")
            return None

    async def _get_weather(self, location: str) -> ToolResult:
        """获取天气信息（优先 Open-Meteo，因其更快更稳定）"""
        if not location:
            return ToolResult(success=False, error="需要位置")
        
        import httpx
        
        logger.info(f"Getting weather for location: {location}")
        
        # 尝试多个天气 API（Open-Meteo 优先，国内访问更快更稳定）
        errors = []
        
        # --- 方法1：Open-Meteo（优先，国内 ~1-2s） ---
        open_meteo_result = await self._get_weather_open_meteo(location, errors)
        if open_meteo_result and open_meteo_result.success:
            return open_meteo_result
        
        # --- 方法2：wttr.in（国内 ~10-15s，容易超时） ---
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
            headers = {"User-Agent": WIKIPEDIA_USER_AGENT}
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=headers, timeout=10)
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
            headers = {"User-Agent": WIKIPEDIA_USER_AGENT}
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=10)
                
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
            headers = {"User-Agent": WIKIPEDIA_USER_AGENT}
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=headers, timeout=15)
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
