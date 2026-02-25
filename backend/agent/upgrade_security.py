"""
Upgrade Security - 升级安全校验
行为白名单、路径保护、签名校验
"""

import ast
import os
import re
import json
import hashlib
import logging
from typing import Tuple, List, Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# MacAgent backend 根目录
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED_TOOLS_DIR = os.path.join(BACKEND_ROOT, "tools", "generated")
DATA_DIR = os.path.join(BACKEND_ROOT, "data")
SIGNATURES_FILE = os.path.join(DATA_DIR, "signatures.json")

# 允许写入的路径（必须是这些目录下的子路径）
ALLOWED_WRITE_PREFIXES = [
    os.path.normpath(os.path.abspath(GENERATED_TOOLS_DIR)),
    os.path.normpath(os.path.abspath(os.path.join(DATA_DIR, "generated_tools"))),
]

# 禁止修改的路径/文件
PROTECTED_PATHS = [
    "agent/",
    "main.py",
    "tools/registry.py",
    "tools/__init__.py",
    "tools/base.py",
    "agent/core.py",
    "agent/self_upgrade/",
    "agent/upgrade_security.py",
    "agent/upgrade_git.py",
]

# 禁止的代码模式（正则）
FORBIDDEN_PATTERNS = [
    (r'\bexec\s*\(', "禁止 exec()"),
    (r'\beval\s*\(', "禁止 eval()"),
    (r'\bcompile\s*\(', "禁止 compile()"),
    (r'__import__\s*\(', "禁止 __import__"),
    (r'\bos\.remove\s*\(', "禁止 os.remove"),
    (r'\bos\.unlink\s*\(', "禁止 os.unlink"),
    (r'\bshutil\.rmtree\s*\(', "禁止 shutil.rmtree"),
    (r'\bos\.system\s*\(', "禁止 os.system"),
    (r'\bsubprocess\.run\s*\(', "禁止 subprocess.run"),
    (r'\bsubprocess\.Popen\s*\(', "禁止 subprocess.Popen"),
    (r'\bgetattr\s*\([^,]+,\s*["\']__', "禁止 getattr 访问 __ 开头属性"),
    (r'\bglobals\s*\(\s*\)', "禁止 globals()"),
    (r'\blocals\s*\(\s*\)\s*=', "禁止 locals() 赋值"),
    (r'while\s+True\s*:', "禁止 while True (可能无限循环)"),
]

# 允许的 import（工具可用的模块白名单，可选严格模式）
ALLOWED_IMPORTS = {
    "asyncio", "os", "json", "re", "logging", "datetime",
    "pathlib", "subprocess", "tempfile", "hashlib",
    "typing", "dataclasses", "abc", "enum",
    "tools.base", "tools",
}


def check_code_safety(code: str) -> Tuple[bool, str]:
    """
    静态检查代码安全性（行为白名单）
    
    Returns:
        (safe, error_message) - safe 为 True 表示通过
    """
    for pattern, msg in FORBIDDEN_PATTERNS:
        if re.search(pattern, code):
            return False, f"安全校验失败: {msg}"
    return True, ""


def is_path_allowed(path: str) -> bool:
    """
    检查路径是否在允许写入的范围内
    仅允许 tools/generated/ 和 data/generated_tools/
    """
    path = os.path.normpath(os.path.abspath(path))
    for prefix in ALLOWED_WRITE_PREFIXES:
        if path == prefix or path.startswith(prefix + os.sep):
            return True
    return False


def is_path_protected(path: str) -> bool:
    """检查路径是否为受保护路径（禁止修改）"""
    path_norm = path.replace("\\", "/")
    for protected in PROTECTED_PATHS:
        if protected in path_norm or path_norm.endswith(protected.rstrip("/")):
            return True
    return False


def compute_file_hash(filepath: str) -> str:
    """计算文件内容的 SHA256"""
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_signatures() -> dict:
    """加载 signatures.json"""
    if not os.path.exists(SIGNATURES_FILE):
        return {}
    try:
        with open(SIGNATURES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load signatures: {e}")
        return {}


def save_signatures(data: dict) -> bool:
    """保存 signatures.json"""
    try:
        os.makedirs(os.path.dirname(SIGNATURES_FILE), exist_ok=True)
        with open(SIGNATURES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save signatures: {e}")
        return False


def verify_tool_signature(filepath: str, tool_name: str, trust_all: bool = False) -> Tuple[bool, str]:
    """
    校验工具签名
    - trust_all=True: 跳过校验
    - signatures.json 中有且 hash 匹配: 通过
    - 无记录: 拒绝（需人工审批）
    
    Returns:
        (verified, message)
    """
    if trust_all:
        return True, "trust_all 模式，跳过签名校验"
    
    if not os.path.exists(filepath):
        return False, f"文件不存在: {filepath}"
    
    current_hash = compute_file_hash(filepath)
    sigs = load_signatures()
    
    if tool_name in sigs:
        expected = sigs[tool_name].get("sha256")
        if expected and expected == current_hash:
            return True, "签名匹配"
        return False, f"签名不匹配: 文件已修改"
    
    return False, f"工具 {tool_name} 未在 signatures.json 中注册，需人工审批后调用 POST /tools/approve"


def approve_tool(filepath: str, tool_name: str) -> Tuple[bool, str]:
    """人工审批：将工具 hash 加入 signatures.json"""
    if not os.path.exists(filepath):
        return False, "文件不存在"
    
    from datetime import datetime
    sigs = load_signatures()
    sigs[tool_name] = {
        "sha256": compute_file_hash(filepath),
        "approved_at": datetime.now().isoformat(),
        "approved_by": "manual"
    }
    if save_signatures(sigs):
        return True, f"已批准 {tool_name}"
    return False, "写入 signatures.json 失败"


def _get_tool_name_from_file(filepath: str) -> Optional[str]:
    """从 .py 文件中解析出 BaseTool 子类的 name 属性（不执行代码）"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except Exception:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        # 检查是否继承 BaseTool
        has_base_tool = False
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "BaseTool":
                has_base_tool = True
                break
            if isinstance(base, ast.Attribute) and base.attr == "BaseTool":
                has_base_tool = True
                break
        if not has_base_tool:
            continue
        # 在类体中查找 name = "xxx"
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name) and t.id == "name" and stmt.value:
                        if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                            return stmt.value.value
                        if isinstance(stmt.value, ast.Str):  # Python 3.7
                            return stmt.value.s
        return None
    return None


def list_pending_tool_approvals() -> List[Dict[str, Any]]:
    """
    列出 tools/generated/ 下未通过签名校验的工具（待人工审批）。
    不执行工具代码，仅解析 AST 获取工具名并检查 signatures.json。
    """
    result: List[Dict[str, Any]] = []
    if not os.path.isdir(GENERATED_TOOLS_DIR):
        return result
    for filename in sorted(os.listdir(GENERATED_TOOLS_DIR)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        filepath = os.path.join(GENERATED_TOOLS_DIR, filename)
        if not is_path_allowed(filepath):
            continue
        tool_name = _get_tool_name_from_file(filepath)
        if not tool_name:
            continue
        verified, _ = verify_tool_signature(filepath, tool_name, trust_all=False)
        if not verified:
            result.append({
                "tool_name": tool_name,
                "file_path": filepath,
                "filename": filename,
            })
    return result
