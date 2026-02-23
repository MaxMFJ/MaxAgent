"""
Upgrade Git - Git 版本管理与回滚
升级前 commit，失败时回滚
"""

import os
import subprocess
import logging
from typing import Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# MacAgent 项目根目录（backend 的上一级）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_git(args: list, cwd: Optional[str] = None) -> Tuple[bool, str, str]:
    """执行 git 命令"""
    cwd = cwd or PROJECT_ROOT
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "", "Git command timeout"
    except FileNotFoundError:
        return False, "", "Git not found"
    except Exception as e:
        return False, "", str(e)


def is_git_repo() -> bool:
    """检查是否为 Git 仓库"""
    ok, _, _ = _run_git(["rev-parse", "--git-dir"])
    return ok


def git_checkpoint(message: Optional[str] = None) -> Tuple[bool, str]:
    """
    升级前 checkpoint：add + commit 当前状态
    
    Returns:
        (success, message)
    """
    if not is_git_repo():
        return False, "不是 Git 仓库，跳过 checkpoint"
    
    msg = message or f"checkpoint before upgrade {datetime.now().isoformat()}"
    
    ok, out, err = _run_git(["add", "."])
    if not ok:
        return False, f"git add 失败: {err}"
    
    ok, out, err = _run_git(["commit", "-m", msg])
    if not ok:
        if "nothing to commit" in err:
            return True, "工作区无变更，已是干净状态"
        return False, f"git commit 失败: {err}"
    
    return True, f"Checkpoint 已创建: {out[:40]}..."


def git_rollback() -> Tuple[bool, str]:
    """
    回滚：丢弃工作区所有修改
    git checkout -- . 或 git reset --hard HEAD
    """
    if not is_git_repo():
        return False, "不是 Git 仓库"
    
    ok, _, err = _run_git(["checkout", "--", "."])
    if not ok:
        return False, f"git checkout 失败: {err}"
    
    ok2, _, err2 = _run_git(["clean", "-fd"], cwd=os.path.join(PROJECT_ROOT, "backend", "tools", "generated"))
    # clean 失败不致命
    return True, "工作区已回滚"


def git_rollback_to(ref: str = "HEAD") -> Tuple[bool, str]:
    """回滚到指定 commit/tag"""
    if not is_git_repo():
        return False, "不是 Git 仓库"
    
    ok, _, err = _run_git(["reset", "--hard", ref])
    if not ok:
        return False, f"git reset 失败: {err}"
    
    return True, f"已回滚到 {ref}"


def git_tag_pre_upgrade() -> Optional[str]:
    """打 tag 标记升级前状态，返回 tag 名"""
    if not is_git_repo():
        return None
    
    tag_name = f"pre-upgrade-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    ok, _, err = _run_git(["tag", "-a", tag_name, "-m", f"Checkpoint before upgrade"])
    if not ok:
        logger.warning(f"git tag 失败: {err}")
        return None
    return tag_name
