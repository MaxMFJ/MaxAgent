/**
 * GroupChatView —— 多 Agent 协作群聊（只读观察）
 * 用户看到所有Agent讨论，任务面板嵌入顶部，不能发送消息。
 */
import React, { useEffect, useRef, useMemo } from 'react';
import { useGroupChatStore } from '@/stores/groupChatStore';
import type { GroupChat, GroupMessage, GroupTaskSummary } from '@/types/types';

/* ── 工具函数 ────────────────────────────────── */

const fmtTime = (ts: number) => {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

const statusLabel: Record<string, string> = {
  active: '进行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

const statusColor: Record<string, string> = {
  active: '#3b82f6',
  completed: '#22c55e',
  failed: '#ef4444',
  cancelled: '#6b7280',
};

const msgTypeIcon: Record<string, string> = {
  task_assign: '📌',
  task_complete: '✅',
  task_failed: '❌',
  task_progress: '⚙️',
  status_update: 'ℹ️',
  plan: '📋',
  conclusion: '🎉',
  text: '💬',
};

/* ── 任务面板 ────────────────────────────────── */

const TaskPanel: React.FC<{ summary: GroupTaskSummary; status: string }> = ({
  summary,
  status,
}) => {
  const total = summary.total ?? 0;
  const completed = summary.completed ?? 0;
  const failed = summary.failed ?? 0;
  const running = summary.running ?? 0;
  const pending = summary.pending ?? 0;
  const progress = total > 0 ? Math.round(((completed + failed) / total) * 100) : 0;

  return (
    <div
      style={{
        padding: '12px 16px',
        borderBottom: '1px solid var(--border, #e5e7eb)',
        background: 'var(--bg-secondary, #f9fafb)',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        flexWrap: 'wrap',
        fontSize: 13,
      }}
    >
      <span
        style={{
          display: 'inline-block',
          padding: '2px 8px',
          borderRadius: 4,
          background: statusColor[status] ?? '#6b7280',
          color: '#fff',
          fontWeight: 600,
          fontSize: 12,
        }}
      >
        {statusLabel[status] ?? status}
      </span>
      <span>总任务: <b>{total}</b></span>
      <span style={{ color: '#22c55e' }}>✅ {completed}</span>
      <span style={{ color: '#f59e0b' }}>🔄 {running}</span>
      <span style={{ color: '#6b7280' }}>⏳ {pending}</span>
      <span style={{ color: '#ef4444' }}>❌ {failed}</span>
      <div
        style={{
          flex: 1,
          minWidth: 100,
          height: 6,
          borderRadius: 3,
          background: '#e5e7eb',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${progress}%`,
            background: failed > 0 ? '#f59e0b' : '#22c55e',
            borderRadius: 3,
            transition: 'width 0.3s ease',
          }}
        />
      </div>
      <span style={{ fontWeight: 600 }}>{progress}%</span>
    </div>
  );
};

/* ── 消息气泡 ────────────────────────────────── */

const GroupMessageBubble: React.FC<{ message: GroupMessage }> = ({ message }) => {
  const isSystem = message.sender_role === 'system';
  const isMain = message.sender_role === 'main';

  if (isSystem) {
    return (
      <div
        style={{
          textAlign: 'center',
          fontSize: 12,
          color: '#9ca3af',
          padding: '4px 0',
        }}
      >
        {msgTypeIcon[message.msg_type] || 'ℹ️'} {message.content}
        <span style={{ marginLeft: 8, fontSize: 11 }}>{fmtTime(message.timestamp)}</span>
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: isMain ? 'flex-start' : 'flex-start',
        padding: '6px 0',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
        <span style={{ fontSize: 16 }}>
          {isMain ? '🧠' : '🦆'}
        </span>
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: isMain ? '#3b82f6' : '#f59e0b',
          }}
        >
          {message.sender_name}
        </span>
        <span style={{ fontSize: 11, color: '#9ca3af' }}>{fmtTime(message.timestamp)}</span>
        {message.msg_type !== 'text' && (
          <span
            style={{
              fontSize: 11,
              padding: '1px 6px',
              borderRadius: 3,
              background: '#f3f4f6',
              color: '#6b7280',
            }}
          >
            {msgTypeIcon[message.msg_type] || ''} {message.msg_type}
          </span>
        )}
      </div>
      <div
        style={{
          background: isMain ? '#eff6ff' : '#fef9ee',
          borderRadius: 8,
          padding: '8px 12px',
          maxWidth: '85%',
          fontSize: 13,
          lineHeight: 1.6,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          border: `1px solid ${isMain ? '#bfdbfe' : '#fed7aa'}`,
        }}
      >
        {message.content}
      </div>
    </div>
  );
};

/* ── 主组件 ────────────────────────────────── */

const GroupChatView: React.FC = () => {
  const activeGroupId = useGroupChatStore((s) => s.activeGroupId);
  const groups = useGroupChatStore((s) => s.groups);
  const group = activeGroupId ? groups[activeGroupId] : undefined;
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [group?.messages.length]);

  if (!group) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          color: '#9ca3af',
          fontSize: 14,
        }}
      >
        选择左侧群聊查看多 Agent 协作详情
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 标题栏 */}
      <div
        style={{
          padding: '10px 16px',
          borderBottom: '1px solid var(--border, #e5e7eb)',
          fontWeight: 600,
          fontSize: 15,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <span>🦆</span>
        <span>{group.title}</span>
        <span style={{ fontSize: 12, color: '#9ca3af', fontWeight: 400 }}>
          ({group.participants.length} 个参与者)
        </span>
      </div>

      {/* 任务面板 */}
      <TaskPanel summary={group.task_summary} status={group.status} />

      {/* 参与者列表 */}
      <div
        style={{
          padding: '6px 16px',
          borderBottom: '1px solid var(--border, #e5e7eb)',
          fontSize: 12,
          color: '#6b7280',
          display: 'flex',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        {group.participants.map((p) => (
          <span key={p.participant_id}>
            {p.emoji} {p.name}
            {p.duck_type ? ` (${p.duck_type})` : ''}
          </span>
        ))}
      </div>

      {/* 消息列表（只读） */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '12px 16px',
        }}
      >
        {group.messages.map((msg) => (
          <GroupMessageBubble key={msg.msg_id} message={msg} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* 底部只读提示 */}
      <div
        style={{
          padding: '8px 16px',
          textAlign: 'center',
          fontSize: 12,
          color: '#9ca3af',
          borderTop: '1px solid var(--border, #e5e7eb)',
          background: 'var(--bg-secondary, #f9fafb)',
        }}
      >
        👀 只读模式 — 如需干预请在主聊天中与主 Agent 沟通
      </div>
    </div>
  );
};

export default GroupChatView;
