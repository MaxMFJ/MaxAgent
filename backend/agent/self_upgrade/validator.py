"""
Validation: exists, Python syntax OK, importable
Stage: VALIDATING
"""

import ast
import importlib.util
import logging
import os
import sys

from .models import UpgradePlan
from .workspace import PROJECT_ROOT

logger = logging.getLogger(__name__)


def validate(plan: UpgradePlan) -> tuple:
    """
    For each target file:
    - exists
    - Python syntax OK
    - importable
    Returns (success, error_message)
    """
    if not plan.target_files:
        return False, "无目标文件"

    for rel in plan.target_files:
        abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, rel))
        if not abs_path.startswith(PROJECT_ROOT + os.sep) and abs_path != PROJECT_ROOT:
            return False, f"路径越界: {rel}"

        if not os.path.exists(abs_path):
            return False, f"文件不存在: {rel}"

        # Python syntax
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                ast.parse(f.read())
        except SyntaxError as e:
            return False, f"语法错误 {rel}: {e}"

        # Importable: try to load module
        try:
            module_name = rel.replace("/", ".").replace("\\", ".").replace(".py", "")
            if module_name.startswith("tools."):
                spec = importlib.util.spec_from_file_location(
                    module_name, abs_path
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = mod
                    spec.loader.exec_module(mod)
                    # Remove to avoid polluting
                    sys.modules.pop(module_name, None)
        except Exception as e:
            return False, f"无法导入 {rel}: {e}"

    return True, ""
