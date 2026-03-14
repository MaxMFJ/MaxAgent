/**
 * Group Chat Store —— 多 Agent 协作群聊状态管理
 * 用户只读观察，所有群聊数据由后端 WebSocket 推送。
 */
import { create } from 'zustand';
import type {
  GroupChat,
  GroupChatBrief,
  GroupChatStatus,
  GroupMessage,
  GroupTaskSummary,
} from '@/types/types';

interface GroupChatState {
  /** 完整群聊数据（已展开查看的） */
  groups: Record<string, GroupChat>;
  /** 群聊简要列表 */
  briefs: GroupChatBrief[];
  /** 当前激活的群聊 ID */
  activeGroupId: string | null;

  /* ── Actions ────────────────────────────────── */

  /** 设置当前查看的群聊 */
  setActiveGroup: (groupId: string | null) => void;

  /** 新群聊创建（WS: group_chat_created） */
  onGroupCreated: (group: GroupChat) => void;

  /** 收到群聊消息（WS: group_message） */
  onGroupMessage: (groupId: string, message: GroupMessage) => void;

  /** 群聊状态/任务面板更新（WS: group_status_update） */
  onGroupStatusUpdate: (
    groupId: string,
    status: GroupChatStatus,
    taskSummary: GroupTaskSummary,
  ) => void;

  /** 从 REST API 加载群聊列表 */
  loadBriefs: (briefs: GroupChatBrief[]) => void;

  /** 从 REST API 加载完整群聊 */
  loadFullGroup: (group: GroupChat) => void;
}

export const useGroupChatStore = create<GroupChatState>((set, get) => ({
  groups: {},
  briefs: [],
  activeGroupId: null,

  setActiveGroup: (groupId) => set({ activeGroupId: groupId }),

  onGroupCreated: (group) =>
    set((state) => {
      const brief: GroupChatBrief = {
        group_id: group.group_id,
        title: group.title,
        session_id: group.session_id,
        dag_id: group.dag_id,
        status: group.status,
        participant_count: group.participants.length,
        message_count: group.messages.length,
        task_summary: group.task_summary,
        created_at: group.created_at,
        completed_at: group.completed_at,
        last_message: group.messages[group.messages.length - 1],
      };
      return {
        groups: { ...state.groups, [group.group_id]: group },
        briefs: [brief, ...state.briefs],
        // 自动跳转到新群聊
        activeGroupId: group.group_id,
      };
    }),

  onGroupMessage: (groupId, message) =>
    set((state) => {
      const existing = state.groups[groupId];
      if (!existing) return state;

      const updated: GroupChat = {
        ...existing,
        messages: [...existing.messages, message],
      };

      // 更新 brief
      const briefs = state.briefs.map((b) =>
        b.group_id === groupId
          ? { ...b, message_count: b.message_count + 1, last_message: message }
          : b,
      );

      return { groups: { ...state.groups, [groupId]: updated }, briefs };
    }),

  onGroupStatusUpdate: (groupId, status, taskSummary) =>
    set((state) => {
      const existing = state.groups[groupId];
      const completedAt =
        status !== 'active' ? Date.now() / 1000 : undefined;

      const updatedGroups = existing
        ? {
            ...state.groups,
            [groupId]: {
              ...existing,
              status,
              task_summary: taskSummary,
              completed_at: completedAt ?? existing.completed_at,
            },
          }
        : state.groups;

      const briefs = state.briefs.map((b) =>
        b.group_id === groupId
          ? {
              ...b,
              status,
              task_summary: taskSummary,
              completed_at: completedAt ?? b.completed_at,
            }
          : b,
      );

      return { groups: updatedGroups, briefs };
    }),

  loadBriefs: (briefs) => set({ briefs }),

  loadFullGroup: (group) =>
    set((state) => ({
      groups: { ...state.groups, [group.group_id]: group },
    })),
}));
