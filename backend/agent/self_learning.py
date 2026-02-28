"""
Self-Learning Module - 自学习模块
让 Agent 能够从失败中学习，自动改进和扩展能力
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# 学习数据存储目录
from paths import DATA_DIR
LEARNING_DATA_DIR = os.path.join(DATA_DIR, "learning")
os.makedirs(LEARNING_DATA_DIR, exist_ok=True)

# 任务模式数据库
TASK_PATTERNS_FILE = os.path.join(LEARNING_DATA_DIR, "task_patterns.json")
# 解决方案库
SOLUTIONS_FILE = os.path.join(LEARNING_DATA_DIR, "solutions.json")
# 失败记录
FAILURES_FILE = os.path.join(LEARNING_DATA_DIR, "failures.json")


class SelfLearningEngine:
    """
    自学习引擎 - 让 Agent 从经验中学习
    
    核心功能：
    1. 记录任务执行结果（成功/失败）
    2. 分析失败原因
    3. 生成改进建议
    4. 存储和检索解决方案
    5. 自动更新任务处理策略
    """
    
    def __init__(self):
        self.task_patterns = self._load_json(TASK_PATTERNS_FILE, {})
        self.solutions = self._load_json(SOLUTIONS_FILE, {})
        self.failures = self._load_json(FAILURES_FILE, [])
    
    def _load_json(self, path: str, default: Any) -> Any:
        """加载 JSON 文件"""
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return default
    
    def _save_json(self, path: str, data: Any):
        """保存 JSON 文件"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def record_task_attempt(
        self,
        task_description: str,
        tools_used: List[str],
        success: bool,
        result: Optional[str] = None,
        error: Optional[str] = None,
        context: Optional[Dict] = None
    ):
        """
        记录任务执行尝试
        """
        record = {
            "task": task_description,
            "tools_used": tools_used,
            "success": success,
            "result": result,
            "error": error,
            "context": context or {},
            "timestamp": datetime.now().isoformat()
        }
        
        if success:
            # 成功的任务，提取模式并保存为解决方案
            pattern = self._extract_pattern(task_description)
            if pattern not in self.solutions:
                self.solutions[pattern] = []
            
            self.solutions[pattern].append({
                "tools": tools_used,
                "success_count": 1,
                "last_used": datetime.now().isoformat()
            })
            self._save_json(SOLUTIONS_FILE, self.solutions)
            logger.info(f"Learned solution for pattern: {pattern}")
        else:
            # 失败的任务，记录以供分析
            self.failures.append(record)
            # 只保留最近 100 条失败记录
            if len(self.failures) > 100:
                self.failures = self.failures[-100:]
            self._save_json(FAILURES_FILE, self.failures)
            logger.info(f"Recorded failure: {error}")
    
    def _extract_pattern(self, task: str) -> str:
        """从任务描述中提取模式"""
        # 简化任务描述为模式
        # 移除具体的应用名、文件名等
        import re
        
        pattern = task.lower()
        
        # 应用操作模式
        app_patterns = {
            r"打开\s*(\S+)": "open_app",
            r"关闭\s*(\S+)": "close_app",
            r"截图.*二维码": "screenshot_qrcode",
            r"截图.*窗口": "screenshot_window",
            r"截图": "screenshot",
            r"点击.*按钮": "click_button",
            r"输入.*文字": "type_text",
            r"发送.*消息": "send_message",
        }
        
        for regex, pattern_name in app_patterns.items():
            if re.search(regex, pattern):
                return pattern_name
        
        return "generic_task"
    
    def get_solution(self, task_description: str) -> Optional[Dict]:
        """
        根据任务描述获取已知的解决方案
        """
        pattern = self._extract_pattern(task_description)
        
        if pattern in self.solutions:
            solutions = self.solutions[pattern]
            if solutions:
                # 返回成功次数最多的方案
                best = max(solutions, key=lambda x: x.get("success_count", 0))
                return {
                    "pattern": pattern,
                    "suggested_tools": best.get("tools", []),
                    "success_count": best.get("success_count", 0)
                }
        
        return None
    
    def analyze_failure(self, error: str, context: Dict) -> Dict[str, Any]:
        """
        分析失败原因并生成改进建议
        """
        analysis = {
            "error_type": "unknown",
            "possible_causes": [],
            "suggestions": [],
            "auto_fix_available": False
        }
        
        error_lower = error.lower()
        
        # 分析错误类型
        if "permission" in error_lower or "denied" in error_lower:
            analysis["error_type"] = "permission"
            analysis["possible_causes"].append("缺少必要的权限")
            analysis["suggestions"].append("检查系统偏好设置 → 隐私与安全 → 辅助功能")
            analysis["suggestions"].append("确保应用已被授权使用辅助功能")
        
        elif "not found" in error_lower or "找不到" in error:
            analysis["error_type"] = "not_found"
            analysis["possible_causes"].append("目标应用或元素不存在")
            analysis["suggestions"].append("确认应用已安装并且名称正确")
            analysis["suggestions"].append("尝试使用 app_control list 查看运行中的应用")
        
        elif "timeout" in error_lower or "超时" in error:
            analysis["error_type"] = "timeout"
            analysis["possible_causes"].append("操作耗时过长")
            analysis["suggestions"].append("增加等待时间")
            analysis["suggestions"].append("分解为更小的操作步骤")
        
        elif "ui element" in error_lower or "element" in error_lower:
            analysis["error_type"] = "ui_not_found"
            analysis["possible_causes"].append("UI 元素不可访问或不存在")
            analysis["suggestions"].append("使用 vision 工具先截图分析界面")
            analysis["suggestions"].append("使用 gui_automation.get_ui_elements 获取可用元素")
            analysis["auto_fix_available"] = True
        
        elif "截图" in error or "screenshot" in error_lower:
            analysis["error_type"] = "screenshot_failed"
            analysis["possible_causes"].append("截图权限不足或被取消")
            analysis["suggestions"].append("检查系统偏好设置 → 隐私与安全 → 屏幕录制")
        
        # 检查是否有类似任务的成功案例
        task = context.get("task", "")
        if task:
            solution = self.get_solution(task)
            if solution:
                analysis["suggestions"].append(f"之前成功使用过: {', '.join(solution['suggested_tools'])}")
                analysis["auto_fix_available"] = True
        
        return analysis
    
    def generate_improvement_plan(self, task: str, failures: List[Dict]) -> Dict[str, Any]:
        """
        根据失败历史生成改进计划
        """
        plan = {
            "task": task,
            "analysis": [],
            "recommended_approach": [],
            "new_tools_needed": []
        }
        
        task_lower = task.lower()
        
        # 分析常见失败点
        for failure in failures:
            if failure.get("task", "").lower() in task_lower or task_lower in failure.get("task", "").lower():
                error = failure.get("error", "")
                analysis = self.analyze_failure(error, {"task": task})
                plan["analysis"].append(analysis)
        
        # 生成推荐方法
        if "微信" in task and "二维码" in task:
            plan["recommended_approach"] = [
                "1. 使用 app_control 打开微信",
                "2. 等待微信窗口完全加载（delay 2-3秒）",
                "3. 使用 vision.describe_window 分析微信界面",
                "4. 使用 vision.get_qrcode 尝试识别二维码",
                "5. 如果找到二维码，使用 gui_automation.screenshot_region 截取",
                "6. 将截图路径返回给用户"
            ]
            plan["new_tools_needed"] = []
        
        elif "截图" in task:
            plan["recommended_approach"] = [
                "1. 确定截图目标（全屏/窗口/区域）",
                "2. 如果是窗口截图，先使用 app_control 激活目标窗口",
                "3. 使用 screenshot 或 vision.capture_and_analyze 截图",
                "4. 如果需要分析内容，使用 OCR 识别"
            ]
        
        return plan
    
    def get_task_guide(self, task: str) -> str:
        """
        获取任务执行指南
        """
        # 检查是否有已知解决方案
        solution = self.get_solution(task)
        
        # 生成改进计划
        plan = self.generate_improvement_plan(task, self.failures)
        
        guide = f"## 任务指南\n\n"
        guide += f"**任务**: {task}\n\n"
        
        if solution:
            guide += f"### 已知解决方案\n"
            guide += f"- 推荐工具: {', '.join(solution['suggested_tools'])}\n"
            guide += f"- 历史成功次数: {solution['success_count']}\n\n"
        
        if plan["recommended_approach"]:
            guide += f"### 推荐步骤\n"
            for step in plan["recommended_approach"]:
                guide += f"{step}\n"
            guide += "\n"
        
        if plan["analysis"]:
            guide += f"### 注意事项\n"
            for analysis in plan["analysis"]:
                if analysis["suggestions"]:
                    for suggestion in analysis["suggestions"]:
                        guide += f"- {suggestion}\n"
        
        return guide


# 全局实例
_learning_engine = None

def get_learning_engine() -> SelfLearningEngine:
    global _learning_engine
    if _learning_engine is None:
        _learning_engine = SelfLearningEngine()
    return _learning_engine
