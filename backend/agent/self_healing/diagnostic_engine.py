"""
诊断引擎 - 检测和分类问题

负责：
1. 分析错误日志和异常
2. 识别问题类型
3. 提取问题上下文
4. 评估问题严重性
"""

import re
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ProblemType(Enum):
    """问题类型分类"""
    # 工具调用相关
    TOOL_PARSE_FAILURE = "tool_parse_failure"      # 工具解析失败
    TOOL_EXECUTION_ERROR = "tool_execution_error"  # 工具执行错误
    TOOL_NOT_FOUND = "tool_not_found"              # 工具未找到
    
    # LLM 相关
    LLM_EMPTY_RESPONSE = "llm_empty_response"      # LLM 返回空响应
    LLM_INVALID_FORMAT = "llm_invalid_format"      # LLM 返回格式错误
    LLM_TIMEOUT = "llm_timeout"                    # LLM 响应超时
    LLM_CONNECTION_ERROR = "llm_connection_error"  # LLM 连接错误
    
    # 上下文相关
    CONTEXT_LOST = "context_lost"                  # 上下文丢失
    CONTEXT_OVERFLOW = "context_overflow"          # 上下文溢出
    
    # 模型兼容性
    MODEL_INCOMPATIBLE = "model_incompatible"      # 模型不兼容
    FUNCTION_CALLING_FAILED = "function_calling_failed"  # Function Calling 失败
    
    # 脚本相关
    SCRIPT_SYNTAX_ERROR = "script_syntax_error"    # 脚本语法错误
    SCRIPT_RUNTIME_ERROR = "script_runtime_error"  # 脚本运行时错误
    
    # 系统相关
    PERMISSION_DENIED = "permission_denied"        # 权限不足
    RESOURCE_NOT_FOUND = "resource_not_found"      # 资源未找到
    
    # 未知
    UNKNOWN = "unknown"


class Severity(Enum):
    """问题严重性"""
    LOW = 1       # 可忽略，不影响功能
    MEDIUM = 2    # 影响部分功能
    HIGH = 3      # 严重影响功能
    CRITICAL = 4  # 系统无法工作


@dataclass
class DiagnosticResult:
    """诊断结果"""
    problem_type: ProblemType
    severity: Severity
    description: str
    source_file: Optional[str] = None
    source_line: Optional[int] = None
    error_message: str = ""
    stack_trace: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "problem_type": self.problem_type.value,
            "severity": self.severity.name,
            "description": self.description,
            "source_file": self.source_file,
            "source_line": self.source_line,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
            "context": self.context,
            "suggestions": self.suggestions,
            "timestamp": self.timestamp.isoformat()
        }


class DiagnosticEngine:
    """诊断引擎"""
    
    # 问题模式匹配规则
    PROBLEM_PATTERNS = [
        # 工具解析失败
        (r"LocalToolParser.*(?:parse|failed|error)", ProblemType.TOOL_PARSE_FAILURE),
        (r"No tool call found", ProblemType.TOOL_PARSE_FAILURE),
        (r"Failed to parse tool", ProblemType.TOOL_PARSE_FAILURE),
        
        # LLM 空响应
        (r"tool_calls.*\[\s*\]", ProblemType.LLM_EMPTY_RESPONSE),
        (r"content.*\"\"", ProblemType.LLM_EMPTY_RESPONSE),
        (r"Empty response from", ProblemType.LLM_EMPTY_RESPONSE),
        
        # Function Calling 失败
        (r"function.*call.*failed", ProblemType.FUNCTION_CALLING_FAILED),
        (r"tool_calls.*empty", ProblemType.FUNCTION_CALLING_FAILED),
        
        # 工具执行错误
        (r"Tool execution failed", ProblemType.TOOL_EXECUTION_ERROR),
        (r"Error executing tool", ProblemType.TOOL_EXECUTION_ERROR),
        
        # 上下文丢失
        (r"无法看到之前的对话", ProblemType.CONTEXT_LOST),
        (r"没有之前的.*上下文", ProblemType.CONTEXT_LOST),
        (r"context.*lost", ProblemType.CONTEXT_LOST),
        
        # LLM 连接错误
        (r"Connection.*refused", ProblemType.LLM_CONNECTION_ERROR),
        (r"Failed to connect.*LLM", ProblemType.LLM_CONNECTION_ERROR),
        (r"Ollama.*not running", ProblemType.LLM_CONNECTION_ERROR),
        
        # 超时
        (r"timeout|Timeout|timed out", ProblemType.LLM_TIMEOUT),
        
        # 权限问题
        (r"Permission denied|EACCES", ProblemType.PERMISSION_DENIED),
        
        # 资源未找到
        (r"not found|Not Found|ENOENT", ProblemType.RESOURCE_NOT_FOUND),
        
        # 脚本错误
        (r"SyntaxError|IndentationError", ProblemType.SCRIPT_SYNTAX_ERROR),
        (r"RuntimeError|NameError|TypeError", ProblemType.SCRIPT_RUNTIME_ERROR),
    ]
    
    # 严重性评估规则
    SEVERITY_RULES = {
        ProblemType.TOOL_PARSE_FAILURE: Severity.HIGH,
        ProblemType.TOOL_EXECUTION_ERROR: Severity.MEDIUM,
        ProblemType.TOOL_NOT_FOUND: Severity.HIGH,
        ProblemType.LLM_EMPTY_RESPONSE: Severity.HIGH,
        ProblemType.LLM_INVALID_FORMAT: Severity.MEDIUM,
        ProblemType.LLM_TIMEOUT: Severity.MEDIUM,
        ProblemType.LLM_CONNECTION_ERROR: Severity.CRITICAL,
        ProblemType.CONTEXT_LOST: Severity.MEDIUM,
        ProblemType.CONTEXT_OVERFLOW: Severity.MEDIUM,
        ProblemType.MODEL_INCOMPATIBLE: Severity.HIGH,
        ProblemType.FUNCTION_CALLING_FAILED: Severity.HIGH,
        ProblemType.SCRIPT_SYNTAX_ERROR: Severity.LOW,
        ProblemType.SCRIPT_RUNTIME_ERROR: Severity.MEDIUM,
        ProblemType.PERMISSION_DENIED: Severity.HIGH,
        ProblemType.RESOURCE_NOT_FOUND: Severity.MEDIUM,
        ProblemType.UNKNOWN: Severity.MEDIUM,
    }
    
    # 问题建议
    SUGGESTIONS = {
        ProblemType.TOOL_PARSE_FAILURE: [
            "切换到远程模型（支持 Function Calling）",
            "优化 LOCAL_MODEL_SYSTEM_PROMPT",
            "添加更多 JSON 解析容错",
            "重试并使用更明确的提示词"
        ],
        ProblemType.LLM_EMPTY_RESPONSE: [
            "检查模型是否正确加载",
            "切换到本地模式（文本解析）",
            "增加 max_tokens 参数",
            "简化输入提示词"
        ],
        ProblemType.FUNCTION_CALLING_FAILED: [
            "切换到本地模式使用 LocalToolParser",
            "使用支持 Function Calling 的模型",
            "降级到文本提示方式"
        ],
        ProblemType.LLM_CONNECTION_ERROR: [
            "检查 Ollama/LM Studio 是否运行",
            "切换到备用 LLM 提供商",
            "检查网络连接"
        ],
        ProblemType.CONTEXT_LOST: [
            "从磁盘重新加载上下文",
            "使用向量搜索恢复相关历史",
            "提示用户重新描述任务"
        ],
        ProblemType.SCRIPT_SYNTAX_ERROR: [
            "使用 LLM 重新生成脚本",
            "添加语法检查预处理",
            "提供错误位置给 LLM 修复"
        ],
    }
    
    def __init__(self):
        self.history: List[DiagnosticResult] = []
    
    def diagnose(
        self,
        error_message: str,
        stack_trace: str = "",
        context: Optional[Dict[str, Any]] = None
    ) -> DiagnosticResult:
        """
        诊断问题
        
        Args:
            error_message: 错误消息
            stack_trace: 堆栈跟踪
            context: 额外上下文信息
        
        Returns:
            DiagnosticResult: 诊断结果
        """
        context = context or {}
        
        # 1. 识别问题类型
        problem_type = self._identify_problem_type(error_message, stack_trace)
        
        # 2. 评估严重性
        severity = self._assess_severity(problem_type, context)
        
        # 3. 提取源文件信息
        source_file, source_line = self._extract_source_location(stack_trace)
        
        # 4. 生成描述
        description = self._generate_description(problem_type, error_message)
        
        # 5. 获取建议
        suggestions = self.SUGGESTIONS.get(problem_type, ["请检查日志获取更多信息"])
        
        result = DiagnosticResult(
            problem_type=problem_type,
            severity=severity,
            description=description,
            source_file=source_file,
            source_line=source_line,
            error_message=error_message,
            stack_trace=stack_trace,
            context=context,
            suggestions=list(suggestions)
        )
        
        self.history.append(result)
        logger.info(f"Diagnosed problem: {problem_type.value} (severity: {severity.name})")
        
        return result
    
    def diagnose_from_exception(
        self,
        exception: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> DiagnosticResult:
        """从异常对象诊断问题"""
        import traceback
        
        error_message = str(exception)
        stack_trace = traceback.format_exc()
        
        return self.diagnose(error_message, stack_trace, context)
    
    def diagnose_llm_response(
        self,
        response: Dict[str, Any],
        expected_tool_call: bool = False
    ) -> Optional[DiagnosticResult]:
        """
        诊断 LLM 响应问题
        
        Args:
            response: LLM 响应
            expected_tool_call: 是否期望工具调用
        
        Returns:
            如果有问题返回诊断结果，否则返回 None
        """
        content = response.get("content", "")
        tool_calls = response.get("tool_calls", [])
        
        # 检查空响应
        if not content and not tool_calls:
            return self.diagnose(
                "LLM returned empty response",
                context={"response": response, "expected_tool_call": expected_tool_call}
            )
        
        # 检查期望工具调用但没有
        if expected_tool_call and not tool_calls:
            # 检查是否在内容中有工具调用 JSON
            if content and '{"tool"' not in content and '"tool":' not in content:
                return self.diagnose(
                    "Expected tool call but none found in response",
                    context={"response": response, "content_preview": content[:200]}
                )
        
        return None
    
    def _identify_problem_type(self, error_message: str, stack_trace: str) -> ProblemType:
        """识别问题类型"""
        combined_text = f"{error_message} {stack_trace}"
        
        for pattern, problem_type in self.PROBLEM_PATTERNS:
            if re.search(pattern, combined_text, re.IGNORECASE):
                return problem_type
        
        return ProblemType.UNKNOWN
    
    def _assess_severity(self, problem_type: ProblemType, context: Dict[str, Any]) -> Severity:
        """评估严重性"""
        base_severity = self.SEVERITY_RULES.get(problem_type, Severity.MEDIUM)
        
        # 根据上下文调整严重性
        if context.get("retry_count", 0) > 2:
            # 多次重试失败，提升严重性
            if base_severity.value < Severity.HIGH.value:
                return Severity.HIGH
        
        if context.get("is_critical_task"):
            # 关键任务，提升严重性
            if base_severity.value < Severity.HIGH.value:
                return Severity(base_severity.value + 1)
        
        return base_severity
    
    def _extract_source_location(self, stack_trace: str) -> tuple[Optional[str], Optional[int]]:
        """从堆栈跟踪提取源文件位置"""
        # 匹配 Python 堆栈跟踪格式: File "xxx.py", line 123
        match = re.search(r'File "([^"]+)", line (\d+)', stack_trace)
        if match:
            return match.group(1), int(match.group(2))
        return None, None
    
    def _generate_description(self, problem_type: ProblemType, error_message: str) -> str:
        """生成问题描述"""
        descriptions = {
            ProblemType.TOOL_PARSE_FAILURE: "本地模型工具调用解析失败",
            ProblemType.TOOL_EXECUTION_ERROR: "工具执行过程中出错",
            ProblemType.TOOL_NOT_FOUND: "请求的工具不存在",
            ProblemType.LLM_EMPTY_RESPONSE: "LLM 返回空响应，未生成有效内容",
            ProblemType.LLM_INVALID_FORMAT: "LLM 返回格式不正确",
            ProblemType.LLM_TIMEOUT: "LLM 响应超时",
            ProblemType.LLM_CONNECTION_ERROR: "无法连接到 LLM 服务",
            ProblemType.CONTEXT_LOST: "对话上下文丢失",
            ProblemType.CONTEXT_OVERFLOW: "上下文长度超出限制",
            ProblemType.MODEL_INCOMPATIBLE: "当前模型不兼容所需功能",
            ProblemType.FUNCTION_CALLING_FAILED: "Function Calling 调用失败",
            ProblemType.SCRIPT_SYNTAX_ERROR: "脚本语法错误",
            ProblemType.SCRIPT_RUNTIME_ERROR: "脚本运行时错误",
            ProblemType.PERMISSION_DENIED: "权限不足",
            ProblemType.RESOURCE_NOT_FOUND: "请求的资源不存在",
            ProblemType.UNKNOWN: "未知错误",
        }
        
        base_desc = descriptions.get(problem_type, "未知错误")
        
        # 添加具体错误信息
        if error_message and len(error_message) < 100:
            return f"{base_desc}: {error_message}"
        
        return base_desc
    
    def get_recent_problems(self, count: int = 10) -> List[DiagnosticResult]:
        """获取最近的问题"""
        return self.history[-count:]
    
    def get_problem_statistics(self) -> Dict[str, Any]:
        """获取问题统计"""
        type_counts: Dict[str, int] = {}
        severity_counts: Dict[str, int] = {}
        
        for result in self.history:
            type_name = result.problem_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
            
            severity_name = result.severity.name
            severity_counts[severity_name] = severity_counts.get(severity_name, 0) + 1
        
        return {
            "total_problems": len(self.history),
            "by_type": type_counts,
            "by_severity": severity_counts
        }


# 全局实例
_diagnostic_engine: Optional[DiagnosticEngine] = None


def get_diagnostic_engine() -> DiagnosticEngine:
    """获取诊断引擎单例"""
    global _diagnostic_engine
    if _diagnostic_engine is None:
        _diagnostic_engine = DiagnosticEngine()
    return _diagnostic_engine
