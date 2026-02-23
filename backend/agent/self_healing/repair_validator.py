"""
修复验证器 - 验证修复结果

负责：
1. 验证修复是否成功
2. 运行测试用例
3. 检查系统状态
4. 生成验证报告
"""

import asyncio
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

from .diagnostic_engine import DiagnosticResult, ProblemType
from .repair_planner import RepairPlan, RepairStrategy
from .repair_executor import ExecutionResult, ExecutionStatus

logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """验证状态"""
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    SKIPPED = "skipped"


@dataclass
class ValidationCheck:
    """单个验证检查"""
    name: str
    description: str
    check_function: str  # 检查函数名称或脚本
    expected_result: Any = None
    actual_result: Any = None
    status: ValidationStatus = ValidationStatus.SKIPPED
    error_message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "expected": str(self.expected_result),
            "actual": str(self.actual_result),
            "error": self.error_message
        }


@dataclass
class ValidationResult:
    """验证结果"""
    plan: RepairPlan
    execution_result: ExecutionResult
    status: ValidationStatus
    checks: List[ValidationCheck] = field(default_factory=list)
    overall_score: float = 0.0  # 0-1 之间
    recommendations: List[str] = field(default_factory=list)
    validated_at: datetime = field(default_factory=datetime.now)
    
    @property
    def passed(self) -> bool:
        return self.status == ValidationStatus.PASSED
    
    @property
    def passed_checks(self) -> List[ValidationCheck]:
        return [c for c in self.checks if c.status == ValidationStatus.PASSED]
    
    @property
    def failed_checks(self) -> List[ValidationCheck]:
        return [c for c in self.checks if c.status == ValidationStatus.FAILED]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_strategy": self.plan.strategy.value,
            "problem_type": self.plan.problem.problem_type.value,
            "execution_status": self.execution_result.status.value,
            "validation_status": self.status.value,
            "checks": [c.to_dict() for c in self.checks],
            "overall_score": self.overall_score,
            "recommendations": self.recommendations,
            "validated_at": self.validated_at.isoformat()
        }


class RepairValidator:
    """修复验证器"""
    
    # 问题类型对应的验证检查
    VALIDATION_CHECKS: Dict[ProblemType, List[Dict[str, Any]]] = {
        ProblemType.TOOL_PARSE_FAILURE: [
            {
                "name": "tool_parse_test",
                "description": "测试工具解析是否正常",
                "test_input": '{"tool": "app_control", "args": {"action": "list"}}',
                "expected": "parsed_successfully"
            },
            {
                "name": "tool_execution_test",
                "description": "测试工具执行是否正常",
                "test_tool": "app_control",
                "test_args": {"action": "list"}
            }
        ],
        ProblemType.LLM_EMPTY_RESPONSE: [
            {
                "name": "llm_response_test",
                "description": "测试 LLM 是否返回有效响应",
                "test_prompt": "请回复 OK",
                "expected_contains": "OK"
            }
        ],
        ProblemType.FUNCTION_CALLING_FAILED: [
            {
                "name": "function_call_test",
                "description": "测试 Function Calling 或文本解析",
                "test_prompt": "列出当前运行的应用",
            }
        ],
        ProblemType.LLM_CONNECTION_ERROR: [
            {
                "name": "connection_test",
                "description": "测试 LLM 连接",
                "test_endpoint": "/status"
            }
        ],
        ProblemType.CONTEXT_LOST: [
            {
                "name": "context_test",
                "description": "测试上下文是否恢复",
                "test_session": True
            }
        ],
    }
    
    def __init__(self):
        self.validation_history: List[ValidationResult] = []
        self._test_runners: Dict[str, Callable] = {}
    
    async def validate(
        self,
        plan: RepairPlan,
        execution_result: ExecutionResult,
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """
        验证修复结果
        
        Args:
            plan: 修复计划
            execution_result: 执行结果
            context: 额外上下文
        
        Returns:
            ValidationResult: 验证结果
        """
        context = context or {}
        
        logger.info(f"Starting validation for: {plan.strategy.value}")
        
        # 如果执行失败，直接返回失败
        if execution_result.status == ExecutionStatus.FAILED:
            return ValidationResult(
                plan=plan,
                execution_result=execution_result,
                status=ValidationStatus.FAILED,
                overall_score=0.0,
                recommendations=["执行失败，请检查错误日志并重试"]
            )
        
        # 获取验证检查列表
        check_configs = self.VALIDATION_CHECKS.get(
            plan.problem.problem_type,
            []
        )
        
        checks: List[ValidationCheck] = []
        
        for config in check_configs:
            check = await self._run_check(config, context)
            checks.append(check)
        
        # 添加通用检查
        generic_checks = await self._run_generic_checks(plan, execution_result)
        checks.extend(generic_checks)
        
        # 计算总体得分
        passed_count = len([c for c in checks if c.status == ValidationStatus.PASSED])
        total_count = len(checks)
        overall_score = passed_count / total_count if total_count > 0 else 0.0
        
        # 确定验证状态
        if overall_score >= 0.8:
            status = ValidationStatus.PASSED
        elif overall_score >= 0.5:
            status = ValidationStatus.PARTIAL
        else:
            status = ValidationStatus.FAILED
        
        # 生成建议
        recommendations = self._generate_recommendations(
            plan, checks, overall_score
        )
        
        result = ValidationResult(
            plan=plan,
            execution_result=execution_result,
            status=status,
            checks=checks,
            overall_score=overall_score,
            recommendations=recommendations
        )
        
        self.validation_history.append(result)
        logger.info(f"Validation completed: {status.value} (score: {overall_score:.2f})")
        
        return result
    
    async def _run_check(
        self,
        config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> ValidationCheck:
        """运行单个检查"""
        check = ValidationCheck(
            name=config.get("name", "unknown"),
            description=config.get("description", ""),
            check_function=config.get("name", "")
        )
        
        try:
            # 根据检查类型执行不同的测试
            if "test_input" in config:
                # 解析测试
                result = await self._test_parse(config["test_input"])
                check.actual_result = result
                check.expected_result = config.get("expected")
                check.status = (
                    ValidationStatus.PASSED 
                    if result == config.get("expected") 
                    else ValidationStatus.FAILED
                )
            
            elif "test_prompt" in config:
                # LLM 响应测试
                result = await self._test_llm_response(config["test_prompt"])
                check.actual_result = result
                
                if "expected_contains" in config:
                    check.expected_result = f"contains: {config['expected_contains']}"
                    check.status = (
                        ValidationStatus.PASSED
                        if config["expected_contains"] in str(result)
                        else ValidationStatus.FAILED
                    )
                else:
                    check.status = (
                        ValidationStatus.PASSED 
                        if result 
                        else ValidationStatus.FAILED
                    )
            
            elif "test_endpoint" in config:
                # API 连接测试
                result = await self._test_endpoint(config["test_endpoint"])
                check.actual_result = "connected" if result else "failed"
                check.expected_result = "connected"
                check.status = (
                    ValidationStatus.PASSED 
                    if result 
                    else ValidationStatus.FAILED
                )
            
            elif "test_tool" in config:
                # 工具执行测试
                result = await self._test_tool_execution(
                    config["test_tool"],
                    config.get("test_args", {})
                )
                check.actual_result = "executed" if result else "failed"
                check.expected_result = "executed"
                check.status = (
                    ValidationStatus.PASSED 
                    if result 
                    else ValidationStatus.FAILED
                )
            
            elif "test_session" in config:
                # 会话测试
                result = await self._test_session(context.get("session_id"))
                check.actual_result = result
                check.status = (
                    ValidationStatus.PASSED 
                    if result 
                    else ValidationStatus.FAILED
                )
            
            else:
                check.status = ValidationStatus.SKIPPED
        
        except Exception as e:
            check.status = ValidationStatus.FAILED
            check.error_message = str(e)
            logger.error(f"Check failed: {check.name} - {e}")
        
        return check
    
    async def _run_generic_checks(
        self,
        plan: RepairPlan,
        execution_result: ExecutionResult
    ) -> List[ValidationCheck]:
        """运行通用检查"""
        checks = []
        
        # 检查后端状态
        backend_check = ValidationCheck(
            name="backend_status",
            description="检查后端服务状态",
            check_function="check_backend"
        )
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://127.0.0.1:8765/status",
                    timeout=5.0
                )
                backend_check.actual_result = "running"
                backend_check.expected_result = "running"
                backend_check.status = ValidationStatus.PASSED
        except Exception as e:
            backend_check.actual_result = "not responding"
            backend_check.expected_result = "running"
            backend_check.status = ValidationStatus.FAILED
            backend_check.error_message = str(e)
        
        checks.append(backend_check)
        
        # 检查执行结果
        execution_check = ValidationCheck(
            name="execution_success",
            description="检查修复执行是否成功",
            check_function="check_execution"
        )
        
        successful_actions = len([
            r for r in execution_result.action_results 
            if r.status == ExecutionStatus.SUCCESS
        ])
        total_actions = len(execution_result.action_results)
        
        execution_check.actual_result = f"{successful_actions}/{total_actions} actions succeeded"
        execution_check.expected_result = "all actions succeeded"
        execution_check.status = (
            ValidationStatus.PASSED 
            if successful_actions == total_actions 
            else ValidationStatus.PARTIAL if successful_actions > 0 
            else ValidationStatus.FAILED
        )
        
        checks.append(execution_check)
        
        return checks
    
    async def _test_parse(self, test_input: str) -> str:
        """测试解析"""
        try:
            from ..local_tool_parser import LocalToolParser
            result, _ = LocalToolParser.parse_response(test_input)
            return "parsed_successfully" if result else "parse_failed"
        except Exception as e:
            return f"error: {e}"
    
    async def _test_llm_response(self, prompt: str) -> str:
        """测试 LLM 响应"""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://127.0.0.1:8765/chat",
                    json={"message": prompt},
                    timeout=30.0
                )
                data = response.json()
                return data.get("content", "")
        except Exception as e:
            return f"error: {e}"
    
    async def _test_endpoint(self, endpoint: str) -> bool:
        """测试端点连接"""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://127.0.0.1:8765{endpoint}",
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception:
            return False
    
    async def _test_tool_execution(
        self,
        tool_name: str,
        args: Dict[str, Any]
    ) -> bool:
        """测试工具执行"""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://127.0.0.1:8765/tools/execute",
                    json={"tool": tool_name, "args": args},
                    timeout=10.0
                )
                return response.status_code == 200
        except Exception:
            return False
    
    async def _test_session(self, session_id: Optional[str]) -> bool:
        """测试会话状态"""
        if not session_id:
            return True  # 没有会话 ID 时跳过
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://127.0.0.1:8765/context/{session_id}",
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception:
            return False
    
    def _generate_recommendations(
        self,
        plan: RepairPlan,
        checks: List[ValidationCheck],
        score: float
    ) -> List[str]:
        """生成建议"""
        recommendations = []
        
        if score < 0.5:
            recommendations.append("修复效果不佳，建议尝试其他修复策略")
            
            # 根据失败的检查提供具体建议
            for check in checks:
                if check.status == ValidationStatus.FAILED:
                    if "llm" in check.name.lower():
                        recommendations.append("检查 LLM 服务是否正常运行")
                    elif "tool" in check.name.lower():
                        recommendations.append("检查工具注册和执行逻辑")
                    elif "connection" in check.name.lower():
                        recommendations.append("检查网络连接和服务端口")
        
        elif score < 0.8:
            recommendations.append("部分检查通过，建议监控后续运行情况")
        
        else:
            recommendations.append("修复成功，建议记录此次修复经验")
        
        # 根据修复策略提供额外建议
        if plan.strategy == RepairStrategy.SWITCH_MODE:
            recommendations.append("已切换模式，如问题复发可考虑永久更改默认设置")
        
        if plan.strategy == RepairStrategy.MODIFY_CODE:
            recommendations.append("代码已修改，建议添加相关测试用例")
        
        return recommendations
    
    def get_validation_statistics(self) -> Dict[str, Any]:
        """获取验证统计"""
        total = len(self.validation_history)
        if total == 0:
            return {"total": 0}
        
        passed = len([v for v in self.validation_history if v.passed])
        avg_score = sum(v.overall_score for v in self.validation_history) / total
        
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": passed / total,
            "average_score": avg_score
        }


# 全局实例
_repair_validator: Optional[RepairValidator] = None


def get_repair_validator() -> RepairValidator:
    """获取修复验证器单例"""
    global _repair_validator
    if _repair_validator is None:
        _repair_validator = RepairValidator()
    return _repair_validator
