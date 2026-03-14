import React, { useState, useMemo } from 'react';
import { useChatStore } from '../stores/chatStore';
import { useWSStore } from '../stores/wsStore';
import { useGroupChatStore } from '../stores/groupChatStore';
import { Button, IconButton, StatusDot, Input } from './ui';
import { Plus, X, Search, MessageSquare, Trash2, Pencil, Users } from 'lucide-react';

interface Props {
  onClose?: () => void;
}

const Sidebar: React.FC<Props> = ({ onClose }) => {
  const conversations = useChatStore((s) => s.conversations);
  const activeId = useChatStore((s) => s.activeConversationId);
  const createConversation = useChatStore((s) => s.createConversation);
  const deleteConversation = useChatStore((s) => s.deleteConversation);
  const setActive = useChatStore((s) => s.setActiveConversation);
  const rename = useChatStore((s) => s.renameConversation);
  const wsStatus = useWSStore((s) => s.status);
  const reconnect = useWSStore((s) => s.reconnect);
  const groupBriefs = useGroupChatStore((s) => s.briefs);
  const activeGroupId = useGroupChatStore((s) => s.activeGroupId);
  const setActiveGroup = useGroupChatStore((s) => s.setActiveGroup);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const sorted = useMemo(() => {
    const list = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt);
    if (!searchQuery.trim()) return list;
    const q = searchQuery.toLowerCase();
    return list.filter(c => c.title.toLowerCase().includes(q) || c.messages.some(m => m.content.toLowerCase().includes(q)));
  }, [conversations, searchQuery]);

  const handleDoubleClick = (id: string, title: string) => {
    setEditingId(id);
    setEditTitle(title);
  };

  const handleRenameSubmit = (id: string) => {
    if (editTitle.trim()) rename(id, editTitle.trim());
    setEditingId(null);
  };

  const connStatus: 'online' | 'offline' | 'connecting' =
    wsStatus === 'connected' ? 'online' :
    wsStatus === 'connecting' ? 'connecting' :
    'offline';

  return (
    <div className="panel-fill" style={{ background: 'var(--bg-surface)', borderRight: '1px solid var(--border)' }}>
      {/* Header */}
      <div className="p-3 flex-shrink-0">
        {onClose && (
          <div className="flex items-center justify-between mb-3">
            <span className="font-display text-sm font-semibold tracking-wider" style={{ color: 'var(--accent)' }}>会话</span>
            <IconButton variant="ghost" size="sm" onClick={onClose} aria-label="关闭侧边栏">
              <X size={16} />
            </IconButton>
          </div>
        )}
        <Button
          variant="primary"
          size="md"
          icon={<Plus size={15} />}
          onClick={() => { createConversation(); onClose?.(); }}
          className="w-full btn-neon"
        >
          新建会话
        </Button>
      </div>

      {/* Search */}
      <div className="px-3 pb-2.5 flex-shrink-0">
        <div className="relative flex items-center">
          <Search size={13} className="absolute left-3 pointer-events-none" style={{ color: 'var(--text-tertiary)' }} />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索会话…"
            className="pl-8 pr-8 h-9 text-xs"
            aria-label="搜索会话"
          />
          {searchQuery && (
            <IconButton
              variant="ghost"
              size="sm"
              className="absolute right-1"
              onClick={() => setSearchQuery('')}
              aria-label="清除搜索"
            >
              <X size={12} />
            </IconButton>
          )}
        </div>
      </div>

      {/* Conversations List */}
      <div className="panel-scroll px-2 pb-2" role="listbox" aria-label="会话列表">
        {sorted.length === 0 && (
          <div className="flex flex-col items-center justify-center py-14 gap-3">
            <div
              className="w-12 h-12 rounded-[var(--radius-xl)] flex items-center justify-center"
              style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
            >
              <MessageSquare size={20} style={{ color: 'var(--text-tertiary)' }} />
            </div>
            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              {searchQuery ? '无搜索结果' : '暂无会话'}
            </span>
          </div>
        )}
        <div className="space-y-1">
          {sorted.map((conv) => {
            const isActive = conv.id === activeId;
            const msgCount = (conv.messages ?? []).length;
            const lastTime = conv.updatedAt;
            const timeStr = lastTime
              ? new Date(lastTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
              : '';

            return (
              <div
                key={conv.id}
                role="option"
                aria-selected={isActive}
                className={`
                  group flex items-center gap-2.5 px-2.5 py-2.5 rounded-[var(--radius-md)] cursor-pointer
                  transition-all duration-[var(--duration-normal)]
                `}
                style={{
                  background: isActive ? 'var(--accent-dim)' : 'transparent',
                  border: isActive ? '1px solid var(--border-glow)' : '1px solid transparent',
                }}
                onClick={() => { setActive(conv.id); onClose?.(); }}
                onDoubleClick={() => handleDoubleClick(conv.id, conv.title)}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-hover)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                  }
                }}
              >
                {editingId === conv.id ? (
                  <input
                    autoFocus
                    className="flex-1 bg-transparent text-sm outline-none px-1"
                    style={{
                      color: 'var(--text-primary)',
                      borderBottom: '1px solid var(--accent)',
                    }}
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onBlur={() => handleRenameSubmit(conv.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleRenameSubmit(conv.id);
                      if (e.key === 'Escape') setEditingId(null);
                    }}
                    aria-label="重命名会话"
                  />
                ) : (
                  <>
                    {/* Icon */}
                    <div
                      className="flex-shrink-0 w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-all duration-200"
                      style={{
                        background: isActive ? 'var(--gradient-accent)' : 'var(--bg-card)',
                        color: isActive ? '#fff' : 'var(--text-tertiary)',
                        border: isActive ? '1px solid transparent' : '1px solid var(--border)',
                      }}
                    >
                      {<MessageSquare size={14} />}
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <span
                        className="block text-[13px] truncate font-medium"
                        style={{ color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)' }}
                      >
                        {conv.title}
                      </span>
                      <div className="flex items-center gap-2 mt-0.5">
                        {msgCount > 0 && (
                          <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                            {msgCount} 条
                          </span>
                        )}
                        <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                          {timeStr}
                        </span>
                      </div>
                    </div>

                    {/* Actions (visible on hover) */}
                    <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex-shrink-0">
                      <IconButton
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDoubleClick(conv.id, conv.title);
                        }}
                        title="重命名"
                        aria-label="重命名会话"
                      >
                        <Pencil size={12} />
                      </IconButton>
                      <IconButton
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm('删除此会话？')) deleteConversation(conv.id);
                        }}
                        title="删除"
                        aria-label="删除会话"
                        className="hover:text-[var(--red)]"
                      >
                        <Trash2 size={12} />
                      </IconButton>
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Group Chats */}
      {groupBriefs.length > 0 && (
        <div className="px-2 pb-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
          <div className="px-1 py-2 flex items-center gap-1.5">
            <Users size={12} style={{ color: 'var(--text-tertiary)' }} />
            <span className="text-[11px] font-semibold tracking-wide" style={{ color: 'var(--text-tertiary)' }}>
              协作群聊
            </span>
          </div>
          <div className="space-y-1">
            {groupBriefs.map((g) => {
              const isActive = g.group_id === activeGroupId;
              const statusEmoji = g.status === 'active' ? '🟢' : g.status === 'completed' ? '✅' : g.status === 'failed' ? '🔴' : '⚪';
              return (
                <div
                  key={g.group_id}
                  className="flex items-center gap-2 px-2.5 py-2 rounded-[var(--radius-md)] cursor-pointer transition-all"
                  style={{
                    background: isActive ? 'var(--accent-dim)' : 'transparent',
                    border: isActive ? '1px solid var(--border-glow)' : '1px solid transparent',
                  }}
                  onClick={() => {
                    setActiveGroup(g.group_id);
                    setActive(null as any);
                    onClose?.();
                  }}
                  onMouseEnter={(e) => { if (!isActive) (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-hover)'; }}
                  onMouseLeave={(e) => { if (!isActive) (e.currentTarget as HTMLDivElement).style.background = 'transparent'; }}
                >
                  <span style={{ fontSize: 14 }}>🦆</span>
                  <div className="flex-1 min-w-0">
                    <span className="block text-[12px] truncate font-medium" style={{ color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                      {g.title}
                    </span>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                        {statusEmoji} {g.participant_count} 人 · {g.message_count} 条
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Footer: Connection Status */}
      <div
        className="flex items-center justify-between px-3 py-3 flex-shrink-0"
        style={{ borderTop: '1px solid var(--border-subtle)' }}
      >
        <StatusDot
          status={connStatus}
          label={wsStatus === 'connected' ? '已连接' : wsStatus === 'connecting' ? '连接中…' : '未连接'}
        />
        {wsStatus === 'disconnected' && (
          <Button variant="ghost" size="sm" onClick={reconnect} className="text-[var(--accent)]">
            重连
          </Button>
        )}
      </div>
    </div>
  );
};

export default Sidebar;
