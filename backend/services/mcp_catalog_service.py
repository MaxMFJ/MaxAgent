"""
MCP 目录索引服务
维护一份精选 MCP Server 目录，支持按关键词 / 分类搜索。
数据源：内置精选列表 + 可选远程更新（awesome-mcp-servers）
"""

import json
import logging
import os
import time
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 缓存文件路径
_CATALOG_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "mcp_catalog_cache.json"
)

# 缓存有效期（秒）
_CACHE_TTL = 86400  # 24h


@dataclass
class MCPCatalogEntry:
    """MCP 目录条目"""
    id: str                          # 唯一标识 e.g. "brave-search"
    name: str                        # 展示名称
    description: str                 # 简短说明
    category: str                    # 分类: search, browser, filesystem, database, ...
    transport: str = "stdio"         # 传输方式
    command: List[str] = field(default_factory=list)  # npx 命令
    env_hint: str = ""               # 需要的环境变量提示
    tags: List[str] = field(default_factory=list)     # 搜索标签
    url: str = ""                    # 项目/文档链接
    popular: bool = False            # 是否热门推荐

    def to_dict(self) -> Dict:
        return asdict(self)

    def matches(self, query: str) -> float:
        """计算与查询的相关度分数 (0-1)"""
        q = query.lower()
        score = 0.0
        # 名称完全匹配
        if q == self.id or q == self.name.lower():
            return 1.0
        # 名称包含
        if q in self.name.lower():
            score += 0.6
        # 描述包含
        if q in self.description.lower():
            score += 0.4
        # 标签匹配
        for tag in self.tags:
            if q in tag.lower():
                score += 0.3
        # 分类匹配
        if q in self.category.lower():
            score += 0.2
        return min(score, 1.0)


# ──────────────────────────────────────────────
# 内置精选目录
# ──────────────────────────────────────────────

_BUILTIN_CATALOG: List[MCPCatalogEntry] = [
    # ── 搜索 ──
    MCPCatalogEntry(
        id="brave-search",
        name="Brave Search",
        description="隐私优先的网页搜索引擎，支持 Web/Image/News/Video 搜索",
        category="search",
        command=["npx", "-y", "@modelcontextprotocol/server-brave-search"],
        env_hint="BRAVE_API_KEY",
        tags=["搜索", "search", "web", "网页搜索", "brave"],
        url="https://github.com/brave/brave-search-mcp-server",
        popular=True,
    ),
    MCPCatalogEntry(
        id="exa-search",
        name="Exa Search",
        description="AI 原生搜索引擎，支持语义搜索和内容提取",
        category="search",
        command=["npx", "-y", "exa-mcp-server"],
        env_hint="EXA_API_KEY",
        tags=["搜索", "search", "semantic", "语义搜索", "exa"],
        url="https://github.com/exa-labs/exa-mcp-server",
        popular=True,
    ),
    MCPCatalogEntry(
        id="duckduckgo-search",
        name="DuckDuckGo Search",
        description="免费 DuckDuckGo 网页搜索，无需 API Key",
        category="search",
        command=["npx", "-y", "duckduckgo-mcp-server"],
        env_hint="",
        tags=["搜索", "免费", "duckduckgo", "search", "free"],
        url="https://github.com/nickclyde/duckduckgo-mcp-server",
    ),
    MCPCatalogEntry(
        id="tavily-search",
        name="Tavily Search",
        description="专为 AI Agent 优化的搜索 API",
        category="search",
        command=["npx", "-y", "@tavily/mcp-server"],
        env_hint="TAVILY_API_KEY",
        tags=["搜索", "search", "tavily", "ai"],
        url="https://github.com/Tomatio13/mcp-server-tavily",
    ),

    # ── 浏览器 ──
    MCPCatalogEntry(
        id="playwright",
        name="Playwright Browser",
        description="微软官方 Playwright 浏览器自动化，通过快照与网页交互",
        category="browser",
        command=["npx", "-y", "@playwright/mcp@latest"],
        env_hint="",
        tags=["浏览器", "browser", "playwright", "自动化", "网页"],
        url="https://github.com/microsoft/playwright-mcp",
        popular=True,
    ),
    MCPCatalogEntry(
        id="puppeteer",
        name="Puppeteer",
        description="浏览器自动化，网页抓取和交互",
        category="browser",
        command=["npx", "-y", "@modelcontextprotocol/server-puppeteer"],
        env_hint="",
        tags=["浏览器", "browser", "puppeteer", "爬虫"],
        url="https://github.com/modelcontextprotocol/servers-archived/tree/main/src/puppeteer",
    ),
    MCPCatalogEntry(
        id="fetch",
        name="Web Fetch",
        description="高效抓取网页内容并转换为 Markdown，适合 AI 消费",
        category="browser",
        command=["npx", "-y", "@modelcontextprotocol/server-fetch"],
        env_hint="",
        tags=["网页", "fetch", "抓取", "markdown"],
        url="https://github.com/modelcontextprotocol/servers-archived/tree/main/src/fetch",
    ),

    # ── 文件系统 ──
    MCPCatalogEntry(
        id="filesystem",
        name="Filesystem",
        description="本地文件系统访问，读写搜索文件",
        category="filesystem",
        command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "/"],
        env_hint="",
        tags=["文件", "filesystem", "file", "读写"],
        url="https://github.com/modelcontextprotocol/servers-archived/tree/main/src/filesystem",
    ),

    # ── 知识与记忆 ──
    MCPCatalogEntry(
        id="memory",
        name="Memory",
        description="跨会话知识图谱，持久化记忆",
        category="knowledge",
        command=["npx", "-y", "@modelcontextprotocol/server-memory"],
        env_hint="",
        tags=["记忆", "memory", "知识图谱", "knowledge"],
        url="https://github.com/modelcontextprotocol/servers-archived",
    ),
    MCPCatalogEntry(
        id="sequential-thinking",
        name="Sequential Thinking",
        description="增强推理，逐步思考与问题分解",
        category="knowledge",
        command=["npx", "-y", "@modelcontextprotocol/server-sequential-thinking"],
        env_hint="",
        tags=["推理", "thinking", "reasoning", "分析"],
        url="https://github.com/modelcontextprotocol/servers-archived",
        popular=True,
    ),

    # ── 数据库 ──
    MCPCatalogEntry(
        id="postgres",
        name="PostgreSQL",
        description="PostgreSQL 数据库查询、分析与管理",
        category="database",
        command=["npx", "-y", "@crystaldba/postgres-mcp"],
        env_hint="DATABASE_URL",
        tags=["数据库", "database", "postgres", "sql", "postgresql"],
        url="https://github.com/crystaldba/postgres-mcp",
        popular=True,
    ),
    MCPCatalogEntry(
        id="sqlite",
        name="SQLite",
        description="SQLite 数据库查询与管理",
        category="database",
        command=["npx", "-y", "mcp-server-sqlite"],
        env_hint="",
        tags=["数据库", "database", "sqlite", "sql"],
    ),
    MCPCatalogEntry(
        id="redis",
        name="Redis",
        description="Redis 数据管理与搜索",
        category="database",
        command=["npx", "-y", "@redis/mcp"],
        env_hint="REDIS_URL",
        tags=["数据库", "database", "redis", "缓存", "cache"],
    ),

    # ── 开发工具 ──
    MCPCatalogEntry(
        id="github",
        name="GitHub",
        description="GitHub 仓库、PR、Issue、代码搜索",
        category="developer",
        command=["npx", "-y", "@modelcontextprotocol/server-github"],
        env_hint="GITHUB_TOKEN",
        tags=["开发", "github", "代码", "git", "仓库"],
        url="https://github.com/modelcontextprotocol/servers-archived/tree/main/src/github",
        popular=True,
    ),
    MCPCatalogEntry(
        id="linear",
        name="Linear",
        description="Linear 项目管理系统集成",
        category="developer",
        command=["npx", "-y", "@tacticlaunch/mcp-linear"],
        env_hint="LINEAR_API_KEY",
        tags=["项目管理", "linear", "issue", "任务"],
    ),

    # ── 视觉 ──
    MCPCatalogEntry(
        id="ai-vision",
        name="AI Vision",
        description="AI 图像与视频分析（Gemini/Vertex AI），支持目标检测、图片对比、视频分析",
        category="vision",
        command=["npx", "-y", "ai-vision-mcp"],
        env_hint="GEMINI_API_KEY",
        tags=["视觉", "vision", "图片", "视频", "image", "video", "OCR", "分析"],
        url="https://github.com/tan-yong-sheng/ai-vision-mcp",
        popular=True,
    ),

    # ── 通信 ──
    MCPCatalogEntry(
        id="slack",
        name="Slack",
        description="Slack 消息读写、频道管理",
        category="communication",
        command=["npx", "-y", "@anthropic/mcp-server-slack"],
        env_hint="SLACK_BOT_TOKEN",
        tags=["通信", "slack", "消息", "聊天"],
    ),

    # ── 文档 ──
    MCPCatalogEntry(
        id="markitdown",
        name="MarkItDown",
        description="多格式文件转 Markdown（PDF/DOCX/HTML/PPTX 等）",
        category="document",
        command=["npx", "-y", "@microsoft/markitdown-mcp"],
        env_hint="",
        tags=["文档", "document", "markdown", "pdf", "转换"],
        url="https://github.com/microsoft/markitdown",
    ),

    # ── 云平台 ──
    MCPCatalogEntry(
        id="cloudflare",
        name="Cloudflare",
        description="Cloudflare Workers/KV/R2/D1 服务管理",
        category="cloud",
        command=["npx", "-y", "@cloudflare/mcp-server-cloudflare"],
        env_hint="CLOUDFLARE_API_TOKEN",
        tags=["云", "cloud", "cloudflare", "workers", "cdn"],
    ),

    # ── 数据分析 ──
    MCPCatalogEntry(
        id="jupyter",
        name="Jupyter",
        description="Jupyter Notebook 交互与数据分析",
        category="data-science",
        command=["npx", "-y", "@datalayer/jupyter-mcp-server"],
        env_hint="",
        tags=["数据分析", "jupyter", "notebook", "python", "科学计算"],
    ),

    # ── 安全 ──
    MCPCatalogEntry(
        id="semgrep",
        name="Semgrep",
        description="代码安全漏洞扫描",
        category="security",
        command=["npx", "-y", "@semgrep/mcp"],
        env_hint="SEMGREP_APP_TOKEN",
        tags=["安全", "security", "漏洞", "扫描", "semgrep"],
    ),

    # ── 金融 ──
    MCPCatalogEntry(
        id="yahoo-finance",
        name="Yahoo Finance",
        description="股票行情、财务数据查询",
        category="finance",
        command=["npx", "-y", "yahoofinance-mcp"],
        env_hint="",
        tags=["金融", "finance", "股票", "stock", "行情"],
    ),
]

# ──────────────────────────────────────────────
# 分类中文映射
# ──────────────────────────────────────────────
CATEGORY_LABELS = {
    "search": "🔎 搜索",
    "browser": "🌐 浏览器",
    "filesystem": "📂 文件系统",
    "knowledge": "🧠 知识与记忆",
    "database": "🗄️ 数据库",
    "developer": "💻 开发工具",
    "vision": "👁️ 视觉",
    "communication": "💬 通信",
    "document": "📄 文档处理",
    "cloud": "☁️ 云平台",
    "data-science": "📊 数据分析",
    "security": "🔒 安全",
    "finance": "💰 金融",
    "other": "🛠️ 其他",
}


class MCPCatalogService:
    """MCP 目录索引服务 — 搜索、推荐、获取安装信息"""

    def __init__(self):
        self._entries: Dict[str, MCPCatalogEntry] = {}
        self._load_builtin()

    def _load_builtin(self):
        for entry in _BUILTIN_CATALOG:
            self._entries[entry.id] = entry
        logger.info("MCP Catalog loaded %d built-in entries", len(self._entries))

    # ── 搜索 ──

    def search(self, query: str, limit: int = 5) -> List[MCPCatalogEntry]:
        """按关键词搜索 MCP Server"""
        if not query.strip():
            return self.get_popular(limit)

        # 支持多关键词（空格分隔取并集）
        keywords = query.strip().lower().split()
        scored = []
        for entry in self._entries.values():
            total = 0.0
            for kw in keywords:
                total += entry.matches(kw)
            if total > 0:
                scored.append((total, entry))

        scored.sort(key=lambda x: -x[0])
        return [e for _, e in scored[:limit]]

    def search_by_category(self, category: str) -> List[MCPCatalogEntry]:
        """按分类查询"""
        return [e for e in self._entries.values() if e.category == category]

    def get_popular(self, limit: int = 6) -> List[MCPCatalogEntry]:
        """获取热门推荐"""
        popular = [e for e in self._entries.values() if e.popular]
        return popular[:limit]

    def get_entry(self, mcp_id: str) -> Optional[MCPCatalogEntry]:
        """根据 ID 获取条目"""
        return self._entries.get(mcp_id)

    def list_categories(self) -> Dict[str, int]:
        """列出所有分类及其条目数"""
        cats: Dict[str, int] = {}
        for entry in self._entries.values():
            cats[entry.category] = cats.get(entry.category, 0) + 1
        return {CATEGORY_LABELS.get(k, k): v for k, v in cats.items()}

    def get_all(self) -> List[MCPCatalogEntry]:
        """获取全部条目"""
        return list(self._entries.values())

    def get_install_info(self, mcp_id: str) -> Optional[Dict]:
        """获取安装所需的信息（供 mcp/servers POST 使用）"""
        entry = self._entries.get(mcp_id)
        if not entry:
            return None
        return {
            "name": entry.id,
            "transport": entry.transport,
            "command": entry.command,
            "env_hint": entry.env_hint,
            "description": entry.description,
        }


# ── 全局单例 ──

_catalog: Optional[MCPCatalogService] = None


def get_mcp_catalog() -> MCPCatalogService:
    global _catalog
    if _catalog is None:
        _catalog = MCPCatalogService()
    return _catalog
