"""
Web Augmented Thinking - 联网增强思维
为本地模型提供"眼睛"和更多思维路径

核心理念：
1. 本地模型生成思维（可能包含需要验证的信息）
2. 系统检测到需要联网的场景，自动搜索补充
3. 将搜索结果注入上下文，增强模型理解

支持的增强场景：
- 实时信息查询（天气、股票、新闻）
- 知识验证（百科、定义）
- 代码/文档查找
- 事实核查
"""

import re
import asyncio
import logging
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class AugmentationType(Enum):
    """增强类型"""
    REALTIME_INFO = "realtime_info"      # 实时信息（天气、股票、新闻）
    KNOWLEDGE = "knowledge"               # 知识查询（百科、定义）
    CODE_SEARCH = "code_search"          # 代码搜索
    FACT_CHECK = "fact_check"            # 事实核查
    TRANSLATION = "translation"          # 翻译需求
    NONE = "none"                        # 不需要增强


@dataclass
class AugmentationContext:
    """增强上下文"""
    augmentation_type: AugmentationType
    query: str
    keywords: List[str] = field(default_factory=list)
    confidence: float = 0.0
    search_results: Optional[Dict[str, Any]] = None
    

class ThinkingAugmenter:
    """
    思维增强器
    分析用户输入和模型思维，自动决定是否需要联网增强
    """
    
    # 实时信息关键词
    REALTIME_KEYWORDS = {
        "天气": ["天气", "气温", "下雨", "刮风", "温度", "weather"],
        "股票": ["股票", "股价", "涨", "跌", "市值", "stock", "上涨", "下跌"],
        "新闻": ["新闻", "最新", "今天", "昨天", "刚刚", "news", "热点"],
        "时间": ["现在几点", "今天是", "日期", "时间"],
    }
    
    # 知识查询关键词
    KNOWLEDGE_KEYWORDS = [
        "什么是", "是什么", "定义", "解释", "介绍",
        "what is", "define", "explain", "who is",
        "怎么", "如何", "为什么", "why", "how",
        "历史", "背景", "原理", "概念",
    ]
    
    # 翻译关键词
    TRANSLATION_KEYWORDS = [
        "翻译", "translate", "用英文", "用中文", "用日文",
        "什么意思", "怎么说", "how to say",
    ]
    
    # 事实核查关键词
    FACT_CHECK_KEYWORDS = [
        "真的吗", "是真的", "是否", "确认", "验证",
        "is it true", "really", "fact check",
    ]
    
    def __init__(self):
        self._web_search_tool = None
        self._wikipedia_tool = None
        
    async def _get_tools(self):
        """懒加载搜索工具"""
        if self._web_search_tool is None:
            from tools import WebSearchTool, WikipediaTool
            self._web_search_tool = WebSearchTool()
            self._wikipedia_tool = WikipediaTool()
    
    def analyze_input(self, user_input: str) -> AugmentationContext:
        """
        分析用户输入，判断是否需要联网增强
        
        Args:
            user_input: 用户输入文本
            
        Returns:
            AugmentationContext 包含增强类型和查询信息
        """
        input_lower = user_input.lower()
        
        # 1. 检查实时信息需求
        for category, keywords in self.REALTIME_KEYWORDS.items():
            for keyword in keywords:
                if keyword in input_lower:
                    # 提取具体查询
                    query = self._extract_realtime_query(user_input, category)
                    return AugmentationContext(
                        augmentation_type=AugmentationType.REALTIME_INFO,
                        query=query,
                        keywords=[keyword],
                        confidence=0.9
                    )
        
        # 2. 检查翻译需求
        for keyword in self.TRANSLATION_KEYWORDS:
            if keyword in input_lower:
                query = self._extract_translation_query(user_input)
                return AugmentationContext(
                    augmentation_type=AugmentationType.TRANSLATION,
                    query=query,
                    keywords=[keyword],
                    confidence=0.85
                )
        
        # 3. 检查知识查询
        for keyword in self.KNOWLEDGE_KEYWORDS:
            if keyword in input_lower:
                query = self._extract_knowledge_query(user_input, keyword)
                return AugmentationContext(
                    augmentation_type=AugmentationType.KNOWLEDGE,
                    query=query,
                    keywords=[keyword],
                    confidence=0.8
                )
        
        # 4. 检查事实核查
        for keyword in self.FACT_CHECK_KEYWORDS:
            if keyword in input_lower:
                return AugmentationContext(
                    augmentation_type=AugmentationType.FACT_CHECK,
                    query=user_input,
                    keywords=[keyword],
                    confidence=0.7
                )
        
        return AugmentationContext(
            augmentation_type=AugmentationType.NONE,
            query="",
            confidence=0.0
        )
    
    def _extract_realtime_query(self, text: str, category: str) -> str:
        """提取实时信息查询"""
        if category == "天气":
            # 提取地点
            location_patterns = [
                r'(.{2,10}?)的?天气',
                r'天气.*?(.{2,10})',
            ]
            for pattern in location_patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1).strip()
            return "当前位置"
        
        elif category == "股票":
            # 提取股票代码或名称
            stock_patterns = [
                r'([A-Z]{1,5})\s*股',
                r'(\d{6})\s*股?',
                r'(.{2,10}?)的?股票',
            ]
            for pattern in stock_patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1).strip()
            return text
        
        elif category == "新闻":
            # 提取新闻主题
            news_patterns = [
                r'(.{2,20}?)的?新闻',
                r'新闻.*?(.{2,20})',
                r'关于(.{2,20}?)的?最新',
            ]
            for pattern in news_patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1).strip()
            return text
        
        return text
    
    def _extract_knowledge_query(self, text: str, keyword: str) -> str:
        """提取知识查询主题"""
        patterns = [
            rf'{keyword}\s*(.+)',
            rf'(.+?)\s*{keyword}',
            rf'(.+?)是什么',
            rf'什么是(.+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                query = match.group(1).strip()
                # 清理标点
                query = re.sub(r'[？?。.！!]', '', query)
                if len(query) > 1:
                    return query
        
        return text
    
    def _extract_translation_query(self, text: str) -> str:
        """提取翻译文本"""
        patterns = [
            r'翻译[：:\s]*["\']?(.+?)["\']?$',
            r'把["\']?(.+?)["\']?翻译',
            r'["\'](.+?)["\'].*翻译',
            r'(.+?)是什么意思',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        return text
    
    async def augment(
        self,
        user_input: str,
        context: Optional[AugmentationContext] = None
    ) -> Optional[Dict[str, Any]]:
        """
        执行思维增强
        
        Args:
            user_input: 用户输入
            context: 预分析的上下文（可选）
            
        Returns:
            增强信息字典，或 None（无需增强）
        """
        if context is None:
            context = self.analyze_input(user_input)
        
        if context.augmentation_type == AugmentationType.NONE:
            return None
        
        await self._get_tools()
        
        augmentation_data = {
            "type": context.augmentation_type.value,
            "query": context.query,
            "confidence": context.confidence,
        }
        
        try:
            if context.augmentation_type == AugmentationType.REALTIME_INFO:
                result = await self._fetch_realtime_info(context)
            elif context.augmentation_type == AugmentationType.KNOWLEDGE:
                result = await self._fetch_knowledge(context)
            elif context.augmentation_type == AugmentationType.TRANSLATION:
                result = await self._fetch_translation(context)
            elif context.augmentation_type == AugmentationType.FACT_CHECK:
                result = await self._fetch_fact_check(context)
            else:
                result = None
            
            if result:
                augmentation_data["result"] = result
                augmentation_data["success"] = True
            else:
                augmentation_data["success"] = False
                
        except Exception as e:
            logger.error(f"Augmentation failed: {e}")
            augmentation_data["success"] = False
            augmentation_data["error"] = str(e)
        
        return augmentation_data
    
    async def _fetch_realtime_info(self, context: AugmentationContext) -> Optional[Dict]:
        """获取实时信息"""
        query = context.query
        keywords = context.keywords
        
        # 判断具体类型
        if any(k in str(keywords) for k in ["天气", "weather", "气温"]):
            result = await self._web_search_tool.execute(
                action="get_weather",
                query=query
            )
            if result.success:
                return {"type": "weather", "data": result.data}
        
        elif any(k in str(keywords) for k in ["股票", "stock"]):
            result = await self._web_search_tool.execute(
                action="get_stock",
                query=query
            )
            if result.success:
                return {"type": "stock", "data": result.data}
        
        elif any(k in str(keywords) for k in ["新闻", "news", "最新"]):
            result = await self._web_search_tool.execute(
                action="news",
                query=query,
                num_results=5
            )
            if result.success:
                return {"type": "news", "data": result.data}
        
        # 默认通用搜索
        result = await self._web_search_tool.execute(
            action="search",
            query=query,
            num_results=3
        )
        if result.success:
            return {"type": "search", "data": result.data}
        
        return None
    
    async def _fetch_knowledge(self, context: AugmentationContext) -> Optional[Dict]:
        """获取知识信息"""
        query = context.query
        
        # 首先尝试 Wikipedia
        wiki_result = await self._wikipedia_tool.execute(
            action="summary",
            query=query,
            language="zh"
        )
        
        if wiki_result.success and wiki_result.data.get("extract"):
            return {
                "type": "wikipedia",
                "data": wiki_result.data
            }
        
        # 尝试英文 Wikipedia
        wiki_en_result = await self._wikipedia_tool.execute(
            action="summary",
            query=query,
            language="en"
        )
        
        if wiki_en_result.success and wiki_en_result.data.get("extract"):
            return {
                "type": "wikipedia_en",
                "data": wiki_en_result.data
            }
        
        # 回退到网页搜索
        search_result = await self._web_search_tool.execute(
            action="answer_question",
            query=query
        )
        
        if search_result.success:
            return {
                "type": "instant_answer",
                "data": search_result.data
            }
        
        # 最后尝试通用搜索
        search_result = await self._web_search_tool.execute(
            action="search",
            query=query,
            num_results=3
        )
        
        if search_result.success:
            return {
                "type": "search",
                "data": search_result.data
            }
        
        return None
    
    async def _fetch_translation(self, context: AugmentationContext) -> Optional[Dict]:
        """获取翻译"""
        result = await self._web_search_tool.execute(
            action="translate",
            query=context.query,
            source_lang="auto",
            target_lang="zh-CN"
        )
        
        if result.success:
            return {
                "type": "translation",
                "data": result.data
            }
        
        return None
    
    async def _fetch_fact_check(self, context: AugmentationContext) -> Optional[Dict]:
        """事实核查"""
        # 搜索相关信息
        result = await self._web_search_tool.execute(
            action="search",
            query=context.query,
            num_results=5
        )
        
        if result.success:
            return {
                "type": "fact_check",
                "data": result.data
            }
        
        return None
    
    def format_augmentation_for_llm(self, augmentation: Dict[str, Any]) -> str:
        """
        将增强信息格式化为 LLM 可理解的文本
        
        Args:
            augmentation: augment() 返回的增强数据
            
        Returns:
            格式化的文本，可注入到上下文中
        """
        if not augmentation or not augmentation.get("success"):
            return ""
        
        aug_type = augmentation.get("type", "")
        result = augmentation.get("result", {})
        result_type = result.get("type", "")
        data = result.get("data", {})
        
        lines = ["\n[🌐 联网信息补充]"]
        
        if result_type == "weather":
            lines.append(f"📍 位置: {data.get('location', '')}")
            lines.append(f"🌡️ 温度: {data.get('temperature_c', '')}°C")
            lines.append(f"☁️ 天气: {data.get('description', '')}")
            lines.append(f"💧 湿度: {data.get('humidity', '')}%")
            if data.get('forecast'):
                lines.append("📅 预报:")
                for f in data['forecast'][:2]:
                    lines.append(f"  - {f.get('date', '')}: {f.get('min_temp_c', '')}~{f.get('max_temp_c', '')}°C, {f.get('description', '')}")
        
        elif result_type == "stock":
            lines.append(f"📈 股票: {data.get('symbol', '')} ({data.get('name', '')})")
            lines.append(f"💰 当前价格: {data.get('current_price', '')} {data.get('currency', '')}")
            if data.get('change') is not None:
                change = data.get('change', 0)
                change_pct = data.get('change_percent', 0)
                symbol = "📈" if change >= 0 else "📉"
                lines.append(f"{symbol} 涨跌: {change:+.2f} ({change_pct:+.2f}%)")
        
        elif result_type == "news":
            news_list = data.get("news", [])
            if news_list:
                lines.append(f"📰 找到 {len(news_list)} 条相关新闻:")
                for i, news in enumerate(news_list[:3], 1):
                    lines.append(f"  {i}. {news.get('title', '')}")
                    if news.get('published_date'):
                        lines.append(f"     📅 {news.get('published_date', '')}")
        
        elif result_type == "wikipedia":
            lines.append(f"📚 维基百科: {data.get('title', '')}")
            extract = data.get('extract', '')
            if len(extract) > 500:
                extract = extract[:500] + "..."
            lines.append(f"📝 {extract}")
        
        elif result_type == "translation":
            lines.append(f"🌐 翻译结果:")
            lines.append(f"  原文: {data.get('original', '')}")
            lines.append(f"  译文: {data.get('translated', '')}")
        
        elif result_type == "search":
            results = data.get("results", [])
            if results:
                lines.append(f"🔍 搜索结果 ({data.get('count', 0)} 条):")
                for i, r in enumerate(results[:3], 1):
                    lines.append(f"  {i}. {r.get('title', '')}")
                    snippet = r.get('snippet', '')
                    if snippet:
                        lines.append(f"     {snippet[:100]}...")
        
        elif result_type == "instant_answer":
            answer = data.get("answer")
            if answer:
                lines.append(f"💡 答案: {answer}")
            else:
                topics = data.get("related_topics", [])
                if topics:
                    lines.append("📋 相关主题:")
                    for t in topics[:3]:
                        lines.append(f"  - {t.get('text', '')}")
        
        lines.append("[/联网信息补充]\n")
        
        return "\n".join(lines)


class WebAugmentedAgent:
    """
    联网增强 Agent 包装器
    自动为用户请求添加联网信息
    """
    
    def __init__(self, base_agent=None):
        self.augmenter = ThinkingAugmenter()
        self.base_agent = base_agent
        self.enable_auto_augment = True
    
    async def prepare_augmented_context(
        self,
        user_message: str
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        准备增强上下文
        
        Args:
            user_message: 用户消息
            
        Returns:
            (增强后的消息, 增强数据)
        """
        if not self.enable_auto_augment:
            return user_message, None
        
        # 分析是否需要增强
        context = self.augmenter.analyze_input(user_message)
        
        if context.augmentation_type == AugmentationType.NONE:
            return user_message, None
        
        # 执行增强
        augmentation = await self.augmenter.augment(user_message, context)
        
        if not augmentation or not augmentation.get("success"):
            return user_message, augmentation
        
        # 格式化增强信息
        augment_text = self.augmenter.format_augmentation_for_llm(augmentation)
        
        # 将增强信息添加到用户消息
        augmented_message = f"{user_message}\n{augment_text}"
        
        return augmented_message, augmentation
