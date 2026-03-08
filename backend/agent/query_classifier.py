"""
企业级 Query 分级：静态规则 + ML Intent Classifier 占位
用于分层 Prompt（FULL/LITE）与 Execution Guard 决策。
支持结构化日志与指标，便于持续优化规则和训练 classifier。
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 可选：分类结果写入 data 目录，供后续规则优化 / ML 训练
QUERY_METRICS_DIR = os.environ.get(
    "QUERY_METRICS_DIR",
    os.path.join(os.path.dirname(__file__), "..", "data"),
)
QUERY_METRICS_FILE = os.path.join(QUERY_METRICS_DIR, "query_classifier_metrics.jsonl")
ENABLE_QUERY_METRICS_LOG = os.environ.get("ENABLE_QUERY_METRICS_LOG", "true").lower() == "true"


class Intent(str, Enum):
    """用户意图"""
    EXECUTION = "execution"   # 需要执行操作：创建、运行、打开等
    INFORMATION = "information"  # 仅追问信息：在哪、做到哪步、生成了吗
    GREETING = "greeting"    # 问候/闲聊
    UNKNOWN = "unknown"      # 未分类，交予模型判断


class QueryTier(str, Enum):
    """查询层级，对应 Prompt 分层"""
    SIMPLE = "simple"   # LITE prompt，优先仅回答
    COMPLEX = "complex"  # FULL prompt，允许工具调用


@dataclass
class IntentResult:
    """分类结果"""
    intent: Intent
    tier: QueryTier
    source: str  # "static" | "ml"
    query_preview: str
    features: Dict[str, Any] = field(default_factory=dict)

    def to_log_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.value,
            "tier": self.tier.value,
            "source": self.source,
            "query_preview": self.query_preview[:100],
            "features": self.features,
        }


# ── 静态规则（可配置化扩展）───────────────────────────────────────────────

GREETING_PHRASES = [
    "你好", "hi", "hello", "hey", "嗨", "在吗", "你是谁", "谢谢", "感谢", "好的", "ok",
]

ACTION_KEYWORDS = [
    "打开", "关闭", "启动", "运行", "创建", "删除", "移动", "复制", "写入", "读取",
    "执行", "命令", "终端", "截图", "截屏", "发送", "邮件", "搜索", "下载", "安装",
    "监控", "升级", "部署", "编译", "构建", "docker", "git", "brew", "npm", "pip",
    "鼠标", "键盘", "点击", "输入", "粘贴", "剪贴板", "capsule", "技能",
    "保存到", "导出", "生成文件", "写到",
    # 任务委派 / 创作类动词
    "制作", "设计一个", "设计一款", "帮我做", "帮我制作", "帮我设计",
    "coder duck", "delegate_duck",
    "开发网页", "做一个网页", "做一个页面", "做网页", "做页面",
]

# 需要 re.search 匹配的 ACTION 模式（支持通配符）
ACTION_PATTERNS = [
    r"让.*?duck",  # 如 "让 coder duck 去做"
]

# 知识/咨询型关键词（触发 COMPLEX tier 以获得完整回答，但不需要工具执行）
KNOWLEDGE_KEYWORDS = [
    "分析", "方案", "策略", "建议", "规划", "推荐", "对比", "比较", "评测",
    "讲解", "解释", "说明", "总结", "梳理", "归纳", "攻略", "指南",
    "怎么样", "什么是", "为什么", "如何理解", "区别是", "优缺点",
    "帮我写", "帮我想", "帮我列",
]

# 纯追问信息（无操作性动词时判为 information）
INFO_ONLY_PATTERNS = [
    "在哪里", "在哪个目录", "哪个目录", "目录在哪", "去哪个目录",
    "我去看一下", "生成了吗", "做到哪一步", "项目目录", "文件在哪",
    "在哪儿", "路径是什么", "位置在哪",
]


def _classify_static(query: str) -> IntentResult:
    """静态规则分类"""
    q = (query or "").strip()
    q_lower = q.lower()
    features = {"len": len(q), "has_action_kw": False, "has_info_pattern": False, "has_knowledge_kw": False}

    # 短问候
    if len(q) < 15:
        for g in GREETING_PHRASES:
            if q_lower.startswith(g) or q_lower == g:
                return IntentResult(
                    intent=Intent.GREETING,
                    tier=QueryTier.SIMPLE,
                    source="static",
                    query_preview=q[:80],
                    features={**features, "rule": "greeting_short"},
                )

    # 操作性关键词 → execution
    if any(kw in q_lower for kw in ACTION_KEYWORDS) or any(re.search(p, q_lower) for p in ACTION_PATTERNS):
        features["has_action_kw"] = True
        return IntentResult(
            intent=Intent.EXECUTION,
            tier=QueryTier.COMPLEX,
            source="static",
            query_preview=q[:80],
            features={**features, "rule": "action_keyword"},
        )
    # 知识/咨询型关键词 → EXECUTION（知识问答可能仍需写文件、委派 Duck, 应获得 FULL prompt）
    # 注意：INFORMATION 只保留给"纯追问位置/结果"（INFO_ONLY_PATTERNS）
    if any(kw in q_lower for kw in KNOWLEDGE_KEYWORDS):
        features["has_knowledge_kw"] = True
        return IntentResult(
            intent=Intent.EXECUTION,
            tier=QueryTier.COMPLEX,
            source="static",
            query_preview=q[:80],
            features={**features, "rule": "knowledge_keyword_as_execution"},
        )
    # 问号结尾且非“怎么/如何/帮我” → 倾向 information/simple
    if q_lower.endswith("?") or q_lower.endswith("？"):
        if not any(kw in q_lower for kw in ["怎么", "如何", "帮我"]):
            return IntentResult(
                intent=Intent.INFORMATION,
                tier=QueryTier.SIMPLE,
                source="static",
                query_preview=q[:80],
                features={**features, "rule": "question_mark"},
            )

    # 纯追问位置/结果
    if any(p in q_lower for p in INFO_ONLY_PATTERNS):
        features["has_info_pattern"] = True
        if not any(kw in q_lower for kw in ACTION_KEYWORDS):
            return IntentResult(
                intent=Intent.INFORMATION,
                tier=QueryTier.SIMPLE,
                source="static",
                query_preview=q[:80],
                features={**features, "rule": "info_only_pattern"},
            )

    # 默认：复杂，交予模型
    return IntentResult(
        intent=Intent.UNKNOWN,
        tier=QueryTier.COMPLEX,
        source="static",
        query_preview=q[:80],
        features={**features, "rule": "default_complex"},
    )


def _classify_with_ml(query: str, context_summary: Optional[str] = None) -> Optional[IntentResult]:
    """
    ML Intent Classifier 占位。
    可接入：本地小模型、远程 API、或已训练的分类器。
    返回 None 表示未启用或失败，回退静态规则。
    """
    # 占位：从环境或配置读取是否启用 ML
    use_ml = os.environ.get("QUERY_CLASSIFIER_ML_ENABLED", "false").lower() == "true"
    if not use_ml:
        return None
    # TODO: 调用 ML 服务，例如：
    # result = ml_client.predict(query=query, context=context_summary)
    # return IntentResult(intent=..., tier=..., source="ml", ...)
    return None


def classify(
    query: str,
    context_summary: Optional[str] = None,
    session_id: Optional[str] = None,
) -> IntentResult:
    """
    分级入口：优先 ML（若启用），否则静态规则。
    写入结构化日志与可选 metrics 文件，便于优化。
    """
    ml_result = _classify_with_ml(query, context_summary)
    result = ml_result if ml_result is not None else _classify_static(query)

    # 结构化日志
    logger.info(
        "query_classifier result=%s tier=%s source=%s query_preview=%s",
        result.intent.value,
        result.tier.value,
        result.source,
        result.query_preview[:50],
        extra={"intent": result.intent.value, "tier": result.tier.value},
    )

    # 可选：追加到 metrics 文件（用于规则调优与 ML 训练数据）
    if ENABLE_QUERY_METRICS_LOG and session_id is not None:
        try:
            os.makedirs(QUERY_METRICS_DIR, exist_ok=True)
            record = {
                "ts": datetime.utcnow().isoformat() + "Z",
                "session_id": session_id,
                "intent": result.intent.value,
                "tier": result.tier.value,
                "source": result.source,
                "query_preview": result.query_preview[:200],
                "features": result.features,
            }
            with open(QUERY_METRICS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("Failed to write query_classifier metrics: %s", e)

    return result


def get_tier_for_prompt(query: str) -> str:
    """兼容 prompt_loader：返回 'simple' 或 'complex'"""
    r = classify(query)
    return r.tier.value
