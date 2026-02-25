"""
Log Analyzer - 启动时日志分析
扫描后台日志缓冲区和 ErrorService 错误队列，
分析错误模式并通过 SystemMessageService 推送通知给前端
"""

import logging
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .error_service import get_error_service
from .system_message_service import get_system_message_service, MessageCategory

logger = logging.getLogger(__name__)

# 已知错误模式 → 用户友好提示（同时匹配 ERROR 和 WARNING 级别日志）
ERROR_PATTERNS = [
    {
        "pattern": r"(?i)connection\s*(refused|reset|timeout|error)",
        "title": "连接异常",
        "suggestion": "检查网络连接或目标服务是否正常运行",
        "level": "error",
    },
    {
        "pattern": r"(?i)(api[_\s]?key|auth|token).*(invalid|expired|missing|unauthorized)",
        "title": "认证失败",
        "suggestion": "请检查 API Key 或认证令牌是否正确配置",
        "level": "error",
    },
    {
        "pattern": r"(?i)(ollama|lm[\s_]?studio).*(not\s+running|unavailable|refused)",
        "title": "本地模型服务异常",
        "suggestion": "本地模型服务未启动，请检查 Ollama 或 LM Studio 是否正在运行",
        "level": "error",
    },
    {
        "pattern": r"(?i)out\s*of\s*memory|OOM|memory\s*error",
        "title": "内存不足",
        "suggestion": "系统内存不足，建议关闭不必要的应用或使用更小的模型",
        "level": "error",
    },
    {
        "pattern": r"(?i)rate\s*limit|too\s*many\s*requests|429",
        "title": "API 请求频率限制",
        "suggestion": "API 调用频率超限，请稍后重试或更换 API Key",
        "level": "error",
    },
    {
        "pattern": r"(?i)tool.*(not\s*found|missing|unavailable)",
        "title": "工具缺失",
        "suggestion": "部分工具不可用，可能需要重新加载或升级工具",
        "level": "warning",
    },
    {
        "pattern": r"(?i)(parse|json|decode)\s*(error|failed|exception)",
        "title": "数据解析错误",
        "suggestion": "模型返回格式异常，建议检查模型配置或切换模型",
        "level": "error",
    },
    {
        "pattern": r"(?i)(permission|access)\s*(denied|error)",
        "title": "权限不足",
        "suggestion": "操作权限不足，请在系统偏好设置中授予相应权限",
        "level": "error",
    },
    {
        "pattern": r"(?i)skipping\s+\S+.*(?:安全校验失败|signature not verified|not verified)",
        "title": "工具加载被跳过（安全校验）",
        "suggestion": "部分动态工具未通过安全校验，如需使用请通过 /tools/approve 审批",
        "level": "warning",
    },
    {
        "pattern": r"(?i)(bootstrap|init|setup)\s*(skipped|failed|error)",
        "title": "模块初始化异常",
        "suggestion": "部分模块启动失败，可能影响相关功能，请查看详细日志",
        "level": "warning",
    },
    {
        "pattern": r"(?i)cannot access local variable",
        "title": "代码变量引用错误",
        "suggestion": "代码中存在变量作用域问题，请检查相关模块",
        "level": "warning",
    },
    {
        "pattern": r"(?i)(import|module)\s*(error|not found|failed)",
        "title": "模块导入失败",
        "suggestion": "依赖模块缺失，请检查 requirements.txt 或重新安装依赖",
        "level": "error",
    },
]


class LogAnalyzer:
    """分析日志和错误队列，生成系统通知"""

    def __init__(self):
        self._last_analysis_time: Optional[datetime] = None

    def analyze_on_startup(self, log_buffer: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        启动时分析：扫描日志缓冲区 + ErrorService 错误队列
        返回生成的系统消息列表
        """
        findings: List[Dict[str, str]] = []

        findings.extend(self._analyze_log_buffer(log_buffer))
        findings.extend(self._analyze_error_queue())

        self._last_analysis_time = datetime.now()

        svc = get_system_message_service()
        for f in findings:
            svc.add(
                level=f["level"],
                title=f["title"],
                content=f["content"],
                source="log_analyzer",
                category=MessageCategory.SYSTEM_ERROR.value,
            )

        if findings:
            logger.info(f"LogAnalyzer: generated {len(findings)} system notifications")
        else:
            logger.info("LogAnalyzer: no issues found in logs")

        return findings

    def _analyze_log_buffer(self, log_buffer: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        findings = []
        if not log_buffer:
            return findings

        SCAN_LEVELS = {"ERROR", "CRITICAL", "WARNING", "WARN"}
        problem_logs = [
            entry for entry in log_buffer
            if entry.get("level", "").upper() in SCAN_LEVELS
        ]

        if not problem_logs:
            return findings

        matched_patterns: Dict[str, List[str]] = {}

        for entry in problem_logs:
            message = entry.get("message", "")
            for pat in ERROR_PATTERNS:
                if re.search(pat["pattern"], message):
                    key = pat["title"]
                    if key not in matched_patterns:
                        matched_patterns[key] = []
                    matched_patterns[key].append(message)
                    break

        for pat in ERROR_PATTERNS:
            key = pat["title"]
            if key in matched_patterns:
                msgs = matched_patterns[key]
                count = len(msgs)
                sample = msgs[-1][:300]
                content = f"检测到 {count} 次{key}。\n{pat['suggestion']}\n\n最近一条: {sample}"
                findings.append({
                    "level": pat.get("level", "warning"),
                    "title": f"启动检查: {key}",
                    "content": content,
                })

        unmatched_errors = []
        for entry in problem_logs:
            if entry.get("level", "").upper() not in ("ERROR", "CRITICAL"):
                continue
            message = entry.get("message", "")
            matched = any(re.search(p["pattern"], message) for p in ERROR_PATTERNS)
            if not matched:
                unmatched_errors.append(message)

        if unmatched_errors:
            count = len(unmatched_errors)
            sample = unmatched_errors[-1][:300]
            findings.append({
                "level": "warning",
                "title": f"启动检查: {count} 条未分类错误",
                "content": f"发现 {count} 条错误日志未匹配已知模式。\n最近一条: {sample}",
            })

        return findings

    def _analyze_error_queue(self) -> List[Dict[str, str]]:
        findings = []
        try:
            error_svc = get_error_service()
            queue_size = error_svc.get_queue_size()
            if queue_size == 0:
                return findings

            errors = error_svc.pop_all()
            event_counts: Counter = Counter()
            latest_by_event: Dict[str, str] = {}

            for err in errors:
                event_type = err.get("event", "unknown")
                event_counts[event_type] += 1
                payload = err.get("payload", {})
                detail = payload.get("error", payload.get("raw", str(payload)))
                latest_by_event[event_type] = str(detail)[:200]

            for event_type, count in event_counts.most_common():
                if event_type == "tool_failed":
                    title = "工具执行失败"
                    level = "error"
                elif event_type == "parse_failed":
                    title = "解析失败"
                    level = "warning"
                else:
                    title = f"事件: {event_type}"
                    level = "warning"

                latest = latest_by_event.get(event_type, "")
                content = f"累计 {count} 次{title}。\n最近一条: {latest}"
                findings.append({"level": level, "title": f"启动检查: {title}", "content": content})

        except Exception as e:
            logger.warning(f"LogAnalyzer: error queue analysis failed: {e}")

        return findings


_analyzer: Optional[LogAnalyzer] = None


def get_log_analyzer() -> LogAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = LogAnalyzer()
    return _analyzer
