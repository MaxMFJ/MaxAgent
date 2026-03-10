import React, { useState, useMemo } from 'react';
import { useNotificationStore } from '../stores/notificationStore';
import { Tabs, TabsList, TabsTrigger } from './ui';
import { Card, Button, Badge, IconButton } from './ui';
import { X } from 'lucide-react';

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
    <div className="panel-fill" style={{ background: 'var(--bg-surface)' }}>
      <Tabs value={category} onValueChange={(v) => setCategory(v as Category)}>
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
              <Badge variant="danger">{unreadCount}</Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            {unreadCount > 0 && (
              <Button variant="ghost" size="sm" onClick={markAllRead}>全部已读</Button>
            )}
            <Button variant="ghost" size="sm" onClick={clearAll}>清空</Button>
          </div>
        </div>

        {/* 分类标签 */}
        <TabsList variant="line" className="w-full justify-start border-0 px-3 py-2.5 gap-1 flex-shrink-0" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          {categories.map((cat) => (
            <TabsTrigger key={cat} value={cat}>{cat}</TabsTrigger>
          ))}
        </TabsList>

        {/* 消息列表 */}
        <div className="panel-scroll p-3 space-y-2">
          {filtered.length === 0 ? (
            <div className="text-xs text-center py-8" style={{ color: 'var(--text-tertiary)' }}>
              暂无{category === '全部' ? '' : category}消息
            </div>
          ) : (
            filtered.map((n) => (
              <Card
                key={n.id}
                padding="sm"
                className={`group transition-all duration-200 animate-fade-in-up ${
                  n.read ? 'bg-[var(--bg-elevated)]' : 'bg-[var(--accent-dim)] border-[color-mix(in_srgb,var(--accent)_20%,transparent)]'
                }`}
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
                  <IconButton
                    variant="ghost"
                    size="sm"
                    onClick={() => removeNotification(n.id)}
                    className="opacity-0 group-hover:opacity-60 hover:opacity-100"
                    aria-label="删除通知"
                  >
                    <X size={12} />
                  </IconButton>
                </div>
              </Card>
            ))
          )}
        </div>
      </Tabs>
    </div>
  );
};

export default NotificationPanel;
