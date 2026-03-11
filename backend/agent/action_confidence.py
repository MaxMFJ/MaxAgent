"""
Action Confidence Model — 动作置信度评估
基于规则的置信度评分，辅助 LLM 决策。

评估维度：
1. action 类型的成功率历史
2. 参数完整性
3. 环境匹配度（文件存在、应用运行等）
4. 连续失败趋势
"""

import logging
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 置信度阈值
CONFIDENCE_HIGH = 0.8
CONFIDENCE_MEDIUM = 0.5
CONFIDENCE_LOW = 0.3


class ActionConfidenceModel:
    """
    基于规则 + 历史统计的动作置信度评估器。
    不需要 ML 模型，用启发式规则快速给出评分。
    """

    def __init__(self):
        # 按 action_type 统计成功/失败
        self._success_counts: Dict[str, int] = defaultdict(int)
        self._failure_counts: Dict[str, int] = defaultdict(int)
        self._consecutive_failures: int = 0
        self._last_action_success: bool = True

    def score(
        self,
        action_type: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        评估动作的置信度 (0.0 ~ 1.0)。

        Args:
            action_type: 动作类型
            params:      动作参数
            context:     可选的上下文 (如 {focused_app, cwd, ...})

        Returns:
            置信度分数
        """
        scores: List[Tuple[float, float]] = []  # (score, weight)

        # 1. 历史成功率
        hist_score, hist_weight = self._history_score(action_type)
        if hist_weight > 0:
            scores.append((hist_score, hist_weight))

        # 2. 参数完整性
        param_score = self._param_completeness(action_type, params)
        scores.append((param_score, 1.5))

        # 3. 环境匹配
        env_score = self._env_check(action_type, params, context or {})
        scores.append((env_score, 2.0))

        # 4. 连续失败惩罚
        if self._consecutive_failures > 0:
            penalty = min(self._consecutive_failures * 0.15, 0.5)
            scores.append((1.0 - penalty, 1.0))

        # 加权平均
        if not scores:
            return 0.7  # 默认中等

        total_weight = sum(w for _, w in scores)
        weighted_sum = sum(s * w for s, w in scores)
        return round(max(0.0, min(1.0, weighted_sum / total_weight)), 2)

    def record_outcome(self, action_type: str, success: bool) -> None:
        """记录 action 执行结果，更新历史统计"""
        if success:
            self._success_counts[action_type] += 1
            self._consecutive_failures = 0
            self._last_action_success = True
        else:
            self._failure_counts[action_type] += 1
            self._consecutive_failures += 1
            self._last_action_success = False

    def get_recommendation(self, confidence: float) -> str:
        """根据置信度给出建议"""
        if confidence >= CONFIDENCE_HIGH:
            return "高置信度，可直接执行"
        elif confidence >= CONFIDENCE_MEDIUM:
            return "中等置信度，建议先验证参数"
        elif confidence >= CONFIDENCE_LOW:
            return "低置信度，建议先收集更多信息"
        else:
            return "极低置信度，建议换用其他方法"

    def should_gather_first(self, confidence: float) -> bool:
        """是否应该先收集信息再执行"""
        return confidence < CONFIDENCE_MEDIUM

    def stats(self) -> Dict[str, Any]:
        all_types = set(self._success_counts.keys()) | set(self._failure_counts.keys())
        per_type = {}
        for at in all_types:
            s = self._success_counts[at]
            f = self._failure_counts[at]
            per_type[at] = {
                "success": s, "failure": f,
                "rate": round(s / max(s + f, 1), 2),
            }
        return {
            "per_action_type": per_type,
            "consecutive_failures": self._consecutive_failures,
        }

    # ------------------------------------------------------------------
    # Scoring components
    # ------------------------------------------------------------------

    def _history_score(self, action_type: str) -> Tuple[float, float]:
        """基于历史成功率评分"""
        s = self._success_counts.get(action_type, 0)
        f = self._failure_counts.get(action_type, 0)
        total = s + f
        if total == 0:
            return 0.7, 0.5  # 无历史数据，给默认分和低权重
        rate = s / total
        weight = min(total / 5.0, 2.0)  # 数据越多权重越高，上限2.0
        return rate, weight

    def _param_completeness(self, action_type: str, params: Dict[str, Any]) -> float:
        """参数完整性评分"""
        required_params: Dict[str, List[str]] = {
            "write_file": ["path", "content"],
            "read_file": ["path"],
            "run_shell": ["command"],
            "move_file": ["source", "destination"],
            "copy_file": ["source", "destination"],
            "delete_file": ["path"],
            "open_app": ["app_name"],
            "mouse_click": ["x", "y"],
            "keyboard_input": ["text"],
        }

        required = required_params.get(action_type.lower(), [])
        if not required:
            return 0.8  # 无已知要求，给较高分

        present = sum(1 for k in required if params.get(k) is not None)
        return present / len(required)

    def _env_check(
        self, action_type: str, params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> float:
        """环境匹配度评分"""
        at = action_type.lower()
        score = 0.8  # 默认

        if at == "read_file":
            path = params.get("path", "")
            if path:
                path = os.path.expanduser(path)
                if os.path.exists(path):
                    score = 1.0
                else:
                    score = 0.1

        elif at == "write_file":
            path = params.get("path", "")
            if path:
                path = os.path.expanduser(path)
                parent = os.path.dirname(path)
                if parent and os.path.isdir(parent):
                    score = 0.95
                elif not parent:
                    score = 0.9
                else:
                    score = 0.4  # 父目录不存在

        elif at in ("mouse_click", "mouse_double_click"):
            x = params.get("x", 0)
            y = params.get("y", 0)
            # 坐标合理性检查（假设屏幕分辨率不超过 4K）
            if 0 < x < 4000 and 0 < y < 3000:
                score = 0.7
            else:
                score = 0.2

        elif at == "run_shell":
            command = params.get("command", "")
            if command:
                # 检查是否使用了危险命令
                dangerous = ["rm -rf /", "mkfs", "dd if="]
                if any(d in command for d in dangerous):
                    score = 0.1
                else:
                    score = 0.8

        return score

    def reset(self) -> None:
        self._success_counts.clear()
        self._failure_counts.clear()
        self._consecutive_failures = 0
        self._last_action_success = True


# 单例
_model: Optional[ActionConfidenceModel] = None


def get_confidence_model() -> ActionConfidenceModel:
    global _model
    if _model is None:
        _model = ActionConfidenceModel()
    return _model
