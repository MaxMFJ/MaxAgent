import React, { useState, useMemo } from 'react';
import { useNotificationStore } from '../stores/notificationStore';

type Category = '全部' | '错误' | '任务' | '系统' | '其他';

const categoryFilter: Record<Category, (type: string) => boolean> = {
  '全部': () => true,
  '错误': (t) => t === 'error' || t === 'warning',
  '任务': (t) => t === 'success' || t === 'task',
  '系统': (t) => t === 'info' || t === 'system',
  '其他': (t) => !['error', 'warning', 'success', 'task', 'info', 'system'].includes(t),
};

const NotificationPanel: React.FC = () => {
  const notifications = useNotificationStore((s) => s.notifications);
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const markAllRead = useNotificationStore((s) => s.markAllRead);
  const clearAll = useNotificationStore((s) => s.clearAll);
  const removeNotification = useNotificationStore((s) => s.removeNotification);

  const [category, setCategory] = useState<Category>('全部');

  const filtered = useMemo(
    () => notifications.filter((n) => categoryFilter[category](n.type)),
    [notifications, category],
  );

  const typeIcon = (type: string) => {
    switch (type) {
      case 'error': return '⚠️';
      case 'warning': return '⚡';
      case 'success': return '✅';
      case 'task': return '🎯';
      case 'system': return '🔧';
      default: return 'ℹ️';
    }
  };

  const categories: Category[] = ['全部', '错误', '任务', '系统', '其他'];

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg-surface)' }}>
      {/* 标题 */}
      <div
        className="flex items-center justify-between px-4 py-3 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border-subtle)' }}
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            🔔 系统消息
          </span>
          {unreadCount > 0 && (
            <span
              className="text-xs px-1.5 py-0.5 rounded-full font-semibold"
              style={{ background: 'var(--red)', color: '#fff' }}
            >
              {unreadCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {unreadCount > 0 && (
            <button
              onClick={markAllRead}
              className="text-xs cursor-pointer transition-colors hover:opacity-80"
              style={{ color: 'var(--text-tertiary)' }}
            >
              全部已读
            </button>
          )}
          <button
            onClick={clearAll}
            className="text-xs cursor-pointer transition-colors hover:opacity-80"
            style={{ color: 'var(--text-tertiary)' }}
          >
            清空
          </button>
        </div>
      </div>

      {/* 分类标签 */}
      <div className="flex gap-1 px-3 py-2.5 flex-shrink-0" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setCategory(cat)}
            className="text-xs px-2.5 py-1 rounded-[var(--radius-md)] transition-all duration-200 cursor-pointer font-medium"
            style={{
              background: category === cat ? 'var(--accent-dim)' : 'transparent',
              color: category === cat ? 'var(--accent)' : 'var(--text-tertiary)',
            }}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {filtered.length === 0 ? (
          <div className="text-xs text-center py-8" style={{ color: 'var(--text-tertiary)' }}>
            暂无{category === '全部' ? '' : category}消息
          </div>
        ) : (
          filtered.map((n) => (
            <div
              key={n.id}
              className="px-3 py-2.5 rounded-[var(--radius-md)] group transition-all duration-200 animate-fade-in-up"
              style={{
                background: n.read ? 'var(--bg-elevated)' : 'var(--accent-dim)',
                border: `1px solid ${n.read ? 'var(--border-subtle)' : 'color-mix(in srgb, var(--accent) 20%, transparent)'}`,
              }}
            >
              <div className="flex items-start gap-2">
                <span className="text-xs flex-shrink-0 mt-0.5">{typeIcon(n.type)}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-xs leading-relaxed" style={{ color: 'var(--text-primary)' }}>
                    {n.message}
                  </div>
                  <div className="text-xs mt-1" style={{ color: 'var(--text-tertiary)', opacity: 0.6 }}>
                    {new Date(n.timestamp).toLocaleTimeString()}
                  </div>
                </div>
                <button
                  onClick={() => removeNotification(n.id)}
                  className="text-xs opacity-0 group-hover:opacity-60 hover:opacity-100 cursor-pointer flex-shrink-0 transition-opacity"
                  style={{ color: 'var(--text-tertiary)' }}
                  aria-label="删除通知"
                >
                  ✕
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default NotificationPanel;
