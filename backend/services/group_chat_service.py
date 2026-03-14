"""
Group Chat Service —— 多 Agent 协作群聊管理
负责群聊 CRUD、消息广播、与 DAG/Scheduler 集成。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.group_chat import (
    GroupChat,
    GroupChatStatus,
    GroupMessage,
    GroupMessageType,
    GroupParticipant,
    ParticipantRole,
)

logger = logging.getLogger(__name__)

# 持久化目录
_DATA_DIR = Path(os.path.dirname(__file__)).parent / "data" / "group_chats"

# Duck type → emoji 映射
_DUCK_EMOJI: Dict[str, str] = {
    "crawler": "🕷️",
    "coder": "💻",
    "image": "🎨",
    "video": "🎬",
    "tester": "🧪",
    "designer": "✏️",
    "general": "🦆",
}


class GroupChatService:
    """群聊管理服务（单例）"""

    _instance: Optional["GroupChatService"] = None

    def __init__(self) -> None:
        self._groups: Dict[str, GroupChat] = {}  # group_id → GroupChat
        self._session_groups: Dict[str, List[str]] = {}  # session_id → [group_id]
        self._dag_groups: Dict[str, str] = {}  # dag_id → group_id
        self._lock = asyncio.Lock()
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    @classmethod
    def get_instance(cls) -> "GroupChatService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── 持久化 ────────────────────────────────────────────────────

    def _load_from_disk(self) -> None:
        """从磁盘加载所有群聊"""
        if not _DATA_DIR.exists():
            return
        for fp in _DATA_DIR.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                gc = GroupChat.model_validate(data)
                self._groups[gc.group_id] = gc
                self._session_groups.setdefault(gc.session_id, []).append(gc.group_id)
                if gc.dag_id:
                    self._dag_groups[gc.dag_id] = gc.group_id
            except Exception as e:
                logger.warning("加载群聊 %s 失败: %s", fp.name, e)

    def _save_group(self, gc: GroupChat) -> None:
        """保存单个群聊到磁盘"""
        try:
            fp = _DATA_DIR / f"{gc.group_id}.json"
            fp.write_text(
                json.dumps(gc.to_dict(), ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("保存群聊 %s 失败: %s", gc.group_id, e)

    # ── 创建 / 查询 ──────────────────────────────────────────────

    async def create_group(
        self,
        session_id: str,
        title: str,
        dag_id: Optional[str] = None,
    ) -> GroupChat:
        """
        创建群聊并加入主 Agent 作为第一个参与者。
        自动广播 group_chat_created 事件到前端。
        """
        async with self._lock:
            gc = GroupChat(
                title=title,
                session_id=session_id,
                dag_id=dag_id,
            )
            # 主 Agent 自动加入
            main_participant = GroupParticipant(
                participant_id="main",
                name="主 Agent",
                role=ParticipantRole.MAIN,
                emoji="🧠",
            )
            gc.add_participant(main_participant)

            self._groups[gc.group_id] = gc
            self._session_groups.setdefault(session_id, []).append(gc.group_id)
            if dag_id:
                self._dag_groups[dag_id] = gc.group_id
            self._save_group(gc)

        # 广播创建事件
        await self._broadcast(session_id, {
            "type": "group_chat_created",
            "group": gc.to_dict(),
        })

        logger.info("群聊已创建: %s [%s] session=%s", gc.title, gc.group_id, session_id)
        return gc

    async def get_group(self, group_id: str) -> Optional[GroupChat]:
        return self._groups.get(group_id)

    async def get_group_by_dag(self, dag_id: str) -> Optional[GroupChat]:
        gid = self._dag_groups.get(dag_id)
        return self._groups.get(gid) if gid else None

    async def list_groups(self, session_id: str) -> List[GroupChat]:
        gids = self._session_groups.get(session_id, [])
        return [self._groups[gid] for gid in gids if gid in self._groups]

    # ── 参与者 ────────────────────────────────────────────────────

    async def add_duck_participant(
        self,
        group_id: str,
        duck_id: str,
        duck_name: str,
        duck_type: str = "general",
    ) -> Optional[GroupParticipant]:
        """将 Duck 加入群聊"""
        gc = self._groups.get(group_id)
        if not gc:
            return None
        emoji = _DUCK_EMOJI.get(duck_type, "🦆")
        participant = GroupParticipant(
            participant_id=duck_id,
            name=duck_name,
            role=ParticipantRole.DUCK,
            duck_type=duck_type,
            emoji=emoji,
        )
        gc.add_participant(participant)
        self._save_group(gc)

        # 广播系统消息
        await self.post_system_message(
            group_id,
            f"{emoji} {duck_name} 加入了协作群",
            msg_type=GroupMessageType.STATUS_UPDATE,
        )
        return participant

    # ── 消息 ──────────────────────────────────────────────────────

    async def post_message(
        self,
        group_id: str,
        sender_id: str,
        content: str,
        msg_type: GroupMessageType = GroupMessageType.TEXT,
        mentions: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[GroupMessage]:
        """Agent 在群聊中发言"""
        gc = self._groups.get(group_id)
        if not gc or gc.status != GroupChatStatus.ACTIVE:
            return None
        participant = gc.get_participant(sender_id)
        if not participant:
            return None

        msg = GroupMessage(
            sender_id=sender_id,
            sender_name=participant.name,
            sender_role=participant.role,
            msg_type=msg_type,
            content=content,
            mentions=mentions or [],
            metadata=metadata or {},
        )
        gc.add_message(msg)
        self._save_group(gc)

        # 广播到前端
        await self._broadcast(gc.session_id, {
            "type": "group_message",
            "group_id": group_id,
            "message": msg.to_dict(),
        })
        return msg

    async def post_system_message(
        self,
        group_id: str,
        content: str,
        msg_type: GroupMessageType = GroupMessageType.STATUS_UPDATE,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[GroupMessage]:
        """系统消息（不需要 sender 在参与者列表中）"""
        gc = self._groups.get(group_id)
        if not gc:
            return None
        msg = GroupMessage(
            sender_id="system",
            sender_name="系统",
            sender_role=ParticipantRole.SYSTEM,
            msg_type=msg_type,
            content=content,
            metadata=metadata or {},
        )
        gc.add_message(msg)
        self._save_group(gc)

        await self._broadcast(gc.session_id, {
            "type": "group_message",
            "group_id": group_id,
            "message": msg.to_dict(),
        })
        return msg

    # ── 任务面板更新 ──────────────────────────────────────────────

    async def update_task_panel(
        self,
        group_id: str,
        total: Optional[int] = None,
        completed: Optional[int] = None,
        failed: Optional[int] = None,
        running: Optional[int] = None,
        pending: Optional[int] = None,
    ) -> None:
        """更新群聊内嵌的任务面板摘要"""
        gc = self._groups.get(group_id)
        if not gc:
            return
        updates: Dict[str, Any] = {}
        if total is not None:
            updates["total"] = total
        if completed is not None:
            updates["completed"] = completed
        if failed is not None:
            updates["failed"] = failed
        if running is not None:
            updates["running"] = running
        if pending is not None:
            updates["pending"] = pending
        gc.update_task_summary(**updates)
        self._save_group(gc)

        await self._broadcast(gc.session_id, {
            "type": "group_status_update",
            "group_id": group_id,
            "task_summary": gc.task_summary,
            "status": gc.status.value,
        })

    # ── 生命周期 ──────────────────────────────────────────────────

    async def complete_group(self, group_id: str, conclusion: str = "") -> None:
        """标记群聊为已完成，主 Agent 发布结论"""
        gc = self._groups.get(group_id)
        if not gc:
            return

        # 先发结论消息（此时 status 仍为 ACTIVE，post_message 检查会通过）
        if conclusion:
            await self.post_message(
                group_id, "main", conclusion,
                msg_type=GroupMessageType.CONCLUSION,
            )

        gc.status = GroupChatStatus.COMPLETED
        gc.completed_at = time.time()
        self._save_group(gc)
        await self._broadcast(gc.session_id, {
            "type": "group_status_update",
            "group_id": group_id,
            "task_summary": gc.task_summary,
            "status": gc.status.value,
        })
        logger.info("群聊已完成: %s", group_id)

    async def fail_group(self, group_id: str, reason: str = "") -> None:
        """标记群聊为失败"""
        gc = self._groups.get(group_id)
        if not gc:
            return
        gc.status = GroupChatStatus.FAILED
        gc.completed_at = time.time()
        if reason:
            await self.post_system_message(group_id, f"❌ 任务失败: {reason}")
        self._save_group(gc)
        await self._broadcast(gc.session_id, {
            "type": "group_status_update",
            "group_id": group_id,
            "task_summary": gc.task_summary,
            "status": gc.status.value,
        })

    async def cancel_group(self, group_id: str) -> None:
        """取消群聊"""
        gc = self._groups.get(group_id)
        if not gc:
            return
        gc.status = GroupChatStatus.CANCELLED
        gc.completed_at = time.time()
        await self.post_system_message(group_id, "⛔ 用户已取消任务")
        self._save_group(gc)
        await self._broadcast(gc.session_id, {
            "type": "group_status_update",
            "group_id": group_id,
            "task_summary": gc.task_summary,
            "status": gc.status.value,
        })

    # ── 广播 ──────────────────────────────────────────────────────

    @staticmethod
    async def _broadcast(session_id: str, message: Dict[str, Any]) -> None:
        """通过 ConnectionManager 广播到前端"""
        try:
            from connection_manager import connection_manager
            await connection_manager.broadcast_to_session(session_id, message)
        except Exception as e:
            logger.debug("群聊广播失败: %s", e)


# ── 全局单例 ──────────────────────────────────────────────────────


def get_group_chat_service() -> GroupChatService:
    return GroupChatService.get_instance()
