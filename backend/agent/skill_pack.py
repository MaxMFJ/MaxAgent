"""
Skill Pack System — 可装载技能包，按任务类型注入专项知识

在现有 Capsule 系统之上提供更高抽象层：
  - SkillPack: 打包多个 capsule + 知识文本 + prompt 片段
  - SkillPackLoader: 从目录/远程加载技能包
  - SkillPackManager: 管理活跃技能包，按任务匹配注入

结构:
  capsules/                      # 现有 capsule 目录
  skill_packs/                   # 技能包目录（新增）
    ├─ web_development/
    │   ├─ pack.json             # 技能包清单
    │   ├─ knowledge.md          # 领域知识
    │   └─ capsules/             # 关联的 capsule 文件
    ├─ data_analysis/
    │   ├─ pack.json
    │   └─ knowledge.md
    └─ ...

注入流程:
  任务描述 → SkillPackManager.match(task) → 匹配的技能包
    → knowledge.md 内容注入 system_prompt
    → 关联 capsule 注册到 CapsuleRegistry
    → prompt_hints 注入到 context_str
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SkillPack:
    """
    技能包定义 — 将相关知识、prompt、capsule 打包

    pack.json 示例:
    {
        "id": "web_development",
        "name": "Web 开发技能包",
        "description": "HTML/CSS/JS 前端开发相关知识和工具链",
        "keywords": ["html", "css", "javascript", "web", "前端", "网页"],
        "knowledge_file": "knowledge.md",
        "prompt_hints": [
            "创建网页时优先用 create_and_run_script 生成文件",
            "大文件（>2000字符）禁止用 write_file"
        ],
        "capsule_ids": ["web_scaffold", "responsive_layout"],
        "agent_types": ["coder", "designer"]
    }
    """
    id: str
    name: str
    description: str = ""
    keywords: List[str] = field(default_factory=list)
    knowledge_file: str = ""          # 相对于技能包目录的知识文件路径
    knowledge_content: str = ""       # 加载后的知识文本
    prompt_hints: List[str] = field(default_factory=list)
    capsule_ids: List[str] = field(default_factory=list)
    agent_types: List[str] = field(default_factory=list)  # 适用的 agent 类型
    source_dir: str = ""              # 技能包所在目录

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "keywords": self.keywords,
            "prompt_hints": self.prompt_hints,
            "capsule_ids": self.capsule_ids,
            "agent_types": self.agent_types,
        }


class SkillPackLoader:
    """从目录加载技能包"""

    @staticmethod
    def load_from_dir(pack_dir: str) -> Optional[SkillPack]:
        """从目录加载单个技能包"""
        pack_path = Path(pack_dir)
        manifest = pack_path / "pack.json"
        if not manifest.exists():
            return None

        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            pack = SkillPack(
                id=data["id"],
                name=data.get("name", data["id"]),
                description=data.get("description", ""),
                keywords=data.get("keywords", []),
                knowledge_file=data.get("knowledge_file", ""),
                prompt_hints=data.get("prompt_hints", []),
                capsule_ids=data.get("capsule_ids", []),
                agent_types=data.get("agent_types", []),
                source_dir=str(pack_path),
            )

            # 加载知识文件
            if pack.knowledge_file:
                knowledge_path = pack_path / pack.knowledge_file
                if knowledge_path.exists():
                    pack.knowledge_content = knowledge_path.read_text(encoding="utf-8")
                    logger.debug(f"SkillPack {pack.id}: loaded knowledge ({len(pack.knowledge_content)} chars)")

            return pack
        except Exception as e:
            logger.warning(f"Failed to load skill pack from {pack_dir}: {e}")
            return None

    @staticmethod
    def scan_directory(root_dir: str) -> List[SkillPack]:
        """扫描目录下所有技能包"""
        root = Path(root_dir)
        if not root.exists():
            return []

        packs = []
        for item in root.iterdir():
            if item.is_dir():
                pack = SkillPackLoader.load_from_dir(str(item))
                if pack:
                    packs.append(pack)

        logger.info(f"Scanned {len(packs)} skill packs from {root_dir}")
        return packs


class SkillPackManager:
    """
    技能包管理器 — 管理已加载的技能包，按任务匹配注入

    职责:
    1. 启动时扫描加载所有技能包
    2. 根据任务描述匹配最相关的技能包
    3. 生成注入到 prompt 的知识 + 提示
    """

    _instance: Optional["SkillPackManager"] = None

    def __init__(self):
        self._packs: Dict[str, SkillPack] = {}
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "SkillPackManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize(self, packs_dir: Optional[str] = None):
        """扫描并加载技能包"""
        if self._initialized:
            return

        if packs_dir is None:
            packs_dir = os.path.join(
                os.path.dirname(__file__),
                "..", "skill_packs"
            )

        packs = SkillPackLoader.scan_directory(packs_dir)
        for pack in packs:
            self._packs[pack.id] = pack

        self._initialized = True
        logger.info(f"SkillPackManager initialized: {len(self._packs)} packs loaded")

    def register(self, pack: SkillPack):
        """动态注册技能包"""
        self._packs[pack.id] = pack

    def get(self, pack_id: str) -> Optional[SkillPack]:
        return self._packs.get(pack_id)

    def list_all(self) -> List[SkillPack]:
        return list(self._packs.values())

    def match(self, task_description: str, agent_type: Optional[str] = None,
              top_k: int = 2) -> List[SkillPack]:
        """
        根据任务描述匹配相关技能包。
        使用关键词匹配 + agent_type 过滤。

        Args:
            task_description: 任务描述
            agent_type: 当前 agent 类型（可选过滤）
            top_k: 返回最多 N 个匹配结果
        """
        task_lower = task_description.lower()
        task_words = set(task_lower.split())

        scored = []
        for pack in self._packs.values():
            score = 0.0

            # 关键词匹配（权重最高）
            for keyword in pack.keywords:
                if keyword.lower() in task_lower:
                    score += 3.0

            # 描述词匹配
            desc_words = set(pack.description.lower().split())
            overlap = len(task_words & desc_words)
            score += overlap * 0.5

            # agent_type 过滤
            if agent_type and pack.agent_types:
                if agent_type not in pack.agent_types:
                    score *= 0.3  # 类型不匹配时降低权重

            if score > 0:
                scored.append((score, pack))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:top_k]]

    def get_prompt_injection(
        self,
        task_description: str,
        agent_type: Optional[str] = None,
        max_knowledge_chars: int = 2000,
    ) -> str:
        """
        获取应注入到 prompt 的技能包内容。

        返回格式化的文本，包含知识和提示。
        """
        matched = self.match(task_description, agent_type=agent_type)
        if not matched:
            return ""

        parts = ["【技能包知识】"]
        total_len = 20

        for pack in matched:
            # 知识内容
            if pack.knowledge_content:
                remaining = max_knowledge_chars - total_len
                if remaining > 200:
                    knowledge = pack.knowledge_content[:remaining]
                    parts.append(f"[{pack.name}]\n{knowledge}")
                    total_len += len(knowledge) + len(pack.name) + 5

            # Prompt 提示
            if pack.prompt_hints:
                hints = "\n".join(f"  - {h}" for h in pack.prompt_hints[:5])
                parts.append(f"[{pack.name} 提示]\n{hints}")
                total_len += len(hints) + 20

        return "\n\n".join(parts) if len(parts) > 1 else ""


# ─── 便捷函数 ──────────────────────────────────────────────

def get_skill_pack_manager() -> SkillPackManager:
    """获取全局 SkillPackManager 单例"""
    mgr = SkillPackManager.get_instance()
    if not mgr._initialized:
        mgr.initialize()
    return mgr
