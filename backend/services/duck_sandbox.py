"""
Duck Sandbox — 每个 Duck 子代理的隔离工作区

借鉴 DeerFlow Sandbox 概念 + MacAgent 现有路径白名单:
  - 每个 Duck 任务分配独立工作目录
  - 文件操作路径重映射到沙箱目录
  - 任务结束后产出文件归档到主工作区
  - 防止 Duck 间文件冲突

层次:
  ~/Desktop/macagent_workspace/
    ├─ ducks/
    │   ├─ {duck_id}_{task_id}/     # Duck 沙箱目录
    │   │   ├─ workspace/           # Duck 工作区根
    │   │   └─ _metadata.json       # 任务元数据
    │   └─ ...
    └─ outputs/                     # 归档产出
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认沙箱根目录
_DEFAULT_SANDBOX_ROOT = os.path.expanduser("~/Desktop/macagent_workspace/ducks")


@dataclass
class SandboxInfo:
    """沙箱实例信息"""
    sandbox_id: str           # "{duck_id}_{task_id}"
    duck_id: str
    task_id: str
    workspace_dir: str        # 沙箱工作目录绝对路径
    created_at: float = 0.0
    output_files: List[str] = field(default_factory=list)
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "duck_id": self.duck_id,
            "task_id": self.task_id,
            "workspace_dir": self.workspace_dir,
            "created_at": self.created_at,
            "output_files": self.output_files,
            "is_active": self.is_active,
        }


class DuckSandbox:
    """
    Duck 沙箱管理器 — 为每个 Duck 任务提供隔离工作区

    职责：
    1. 创建/回收沙箱目录
    2. 提供路径重映射（虚拟路径 → 沙箱物理路径）
    3. 任务完成后收集产出文件
    4. 注入沙箱约束到 Agent 上下文
    """

    def __init__(self, sandbox_root: Optional[str] = None):
        self._root = Path(sandbox_root or _DEFAULT_SANDBOX_ROOT)
        self._root.mkdir(parents=True, exist_ok=True)
        self._active: Dict[str, SandboxInfo] = {}

    def create_sandbox(self, duck_id: str, task_id: str, label: str = "") -> SandboxInfo:
        """
        为 Duck 任务创建独立沙箱目录。

        Args:
            duck_id: Duck 标识符
            task_id: 任务 ID（取前 8 位）
            label: 可读任务标签（由主 Agent 设置，用于目录命名，如 "AI行业数据搜集"）

        Returns:
            SandboxInfo with workspace_dir set
        """
        sandbox_id = f"{duck_id}_{task_id}"  # 内部查找键不变

        # 用可读 label 作为目录前缀（限 20 字符，去除特殊字符）
        if label:
            import re as _re
            safe_label = _re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", label).strip()[:20]
            dir_name = f"{safe_label}_{task_id}" if safe_label else sandbox_id
        else:
            dir_name = sandbox_id

        workspace_dir = self._root / dir_name / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        info = SandboxInfo(
            sandbox_id=sandbox_id,
            duck_id=duck_id,
            task_id=task_id,
            workspace_dir=str(workspace_dir),
            created_at=time.time(),
        )

        # 写入元数据
        meta_path = self._root / dir_name / "_metadata.json"
        meta_path.write_text(
            json.dumps(info.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self._active[sandbox_id] = info
        logger.info(f"Sandbox created: {sandbox_id} → {workspace_dir}")
        return info

    def get_sandbox(self, duck_id: str, task_id: str) -> Optional[SandboxInfo]:
        """获取活跃沙箱"""
        sandbox_id = f"{duck_id}_{task_id}"
        return self._active.get(sandbox_id)

    def resolve_path(self, sandbox: SandboxInfo, virtual_path: str) -> str:
        """
        将虚拟路径映射到沙箱物理路径。

        规则:
        - 绝对路径中的 ~/Desktop 前缀重映射到沙箱 workspace
        - 相对路径解析为相对于沙箱 workspace
        - 已在沙箱内的路径不做转换
        """
        expanded = os.path.expanduser(virtual_path)
        abs_path = os.path.abspath(expanded)

        # 已在沙箱内
        if abs_path.startswith(sandbox.workspace_dir):
            return abs_path

        # ~/Desktop/xxx → sandbox/workspace/xxx
        desktop = os.path.expanduser("~/Desktop")
        if abs_path.startswith(desktop):
            relative = os.path.relpath(abs_path, desktop)
            return os.path.join(sandbox.workspace_dir, relative)

        # 相对路径
        if not os.path.isabs(virtual_path):
            return os.path.join(sandbox.workspace_dir, virtual_path)

        # 其他绝对路径：保持不变但发出警告
        logger.warning(f"Sandbox: path outside sandbox scope: {virtual_path}")
        return abs_path

    def collect_outputs(self, sandbox: SandboxInfo) -> List[str]:
        """
        收集沙箱中产生的所有文件。

        Returns:
            list of relative file paths within workspace
        """
        outputs = []
        ws = Path(sandbox.workspace_dir)
        if ws.exists():
            for file_path in ws.rglob("*"):
                if file_path.is_file() and file_path.name != "_metadata.json":
                    rel = str(file_path.relative_to(ws))
                    outputs.append(rel)
        sandbox.output_files = outputs
        return outputs

    def archive_sandbox(
        self,
        sandbox: SandboxInfo,
        archive_dir: Optional[str] = None,
    ) -> List[str]:
        """
        任务完成后归档沙箱产出到目标目录。

        Args:
            sandbox: 沙箱信息
            archive_dir: 归档目标目录（默认 ~/Desktop）

        Returns:
            归档后的文件路径列表
        """
        if archive_dir is None:
            archive_dir = os.path.expanduser("~/Desktop")

        outputs = self.collect_outputs(sandbox)
        archived = []
        ws = Path(sandbox.workspace_dir)

        for rel_path in outputs:
            src = ws / rel_path
            dst = Path(archive_dir) / rel_path
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))
                archived.append(str(dst))
            except Exception as e:
                logger.warning(f"Failed to archive {rel_path}: {e}")

        sandbox.is_active = False
        logger.info(f"Sandbox archived: {sandbox.sandbox_id}, {len(archived)} files")
        return archived

    def cleanup_sandbox(self, sandbox: SandboxInfo, force: bool = False):
        """清理沙箱目录"""
        if sandbox.is_active and not force:
            logger.warning(f"Cannot cleanup active sandbox: {sandbox.sandbox_id}")
            return

        sandbox_dir = self._root / sandbox.sandbox_id
        if sandbox_dir.exists():
            shutil.rmtree(str(sandbox_dir), ignore_errors=True)
            logger.info(f"Sandbox cleaned: {sandbox.sandbox_id}")

        self._active.pop(sandbox.sandbox_id, None)

    def get_sandbox_context(self, sandbox: SandboxInfo) -> str:
        """
        生成沙箱约束提示，注入到 Duck 的 prompt 中。
        """
        return (
            f"【工作区约束】你的独立工作目录: {sandbox.workspace_dir}\n"
            f"所有文件操作（读写、创建）必须在此目录或其子目录中进行。\n"
            f"禁止访问其他 Duck 的工作目录或系统敏感路径。"
        )

    def cleanup_stale(self, max_age_hours: float = 24):
        """清理过期的非活跃沙箱"""
        now = time.time()
        cutoff = now - max_age_hours * 3600

        for item in self._root.iterdir():
            if not item.is_dir():
                continue
            meta_file = item / "_metadata.json"
            if not meta_file.exists():
                continue
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                created = meta.get("created_at", 0)
                if created < cutoff and not meta.get("is_active", False):
                    shutil.rmtree(str(item), ignore_errors=True)
                    logger.info(f"Stale sandbox cleaned: {item.name}")
            except Exception:
                pass

    @property
    def active_count(self) -> int:
        return len(self._active)


# ─── 单例 ──────────────────────────────────────────────

_sandbox_instance: Optional[DuckSandbox] = None


def get_duck_sandbox() -> DuckSandbox:
    global _sandbox_instance
    if _sandbox_instance is None:
        _sandbox_instance = DuckSandbox()
    return _sandbox_instance
