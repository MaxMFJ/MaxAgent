import React from 'react';
import { useWSStore } from '../stores/wsStore';
import { useSettingsStore } from '../stores/settingsStore';
import { useNotificationStore } from '../stores/notificationStore';
import { IconButton, StatusDot } from './ui';
import {
  Menu,
  Wrench,
  Bell,
  Settings,
  BarChart3,
  Zap,
  Bird,
} from 'lucide-react';

interface Props {
  rightTab: 'tools' | 'notifications';
  onRightTabChange: (tab: 'tools' | 'notifications') => void;
  onOpenSettings: () => void;
  onOpenMonitor: () => void;
  onOpenDuck: () => void;
  isMobile?: boolean;
}

const Toolbar: React.FC<Props> = ({ rightTab, onRightTabChange, onOpenSettings, onOpenMonitor, onOpenDuck, isMobile }) => {
  const status = useWSStore((s) => s.status);
  const toggleRightPanel = useSettingsStore((s) => s.toggleRightPanel);
  const showRightPanel = useSettingsStore((s) => s.showRightPanel);
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const setMobileSidebarOpen = useSettingsStore((s) => s.setMobileSidebarOpen);
  const mobileSidebarOpen = useSettingsStore((s) => s.mobileSidebarOpen);
  const setMobilePanelOpen = useSettingsStore((s) => s.setMobilePanelOpen);

  const wsStatus: 'online' | 'offline' | 'connecting' =
    status === 'connected' ? 'online' :
    status === 'connecting' ? 'connecting' :
    'offline';

  const statusLabel =
    status === 'connected' ? '已连接' :
    status === 'connecting' ? '连接中…' :
    '未连接';

  // ---- 移动端工具栏 ----
  if (isMobile) {
    return (
      <div
        className="flex items-center justify-between px-3 h-13 flex-shrink-0 select-none"
        style={{
          background: 'var(--glass-bg)',
          backdropFilter: 'var(--glass-blur)',
          WebkitBackdropFilter: 'var(--glass-blur)',
          borderBottom: '1px solid var(--border)',
          boxShadow: '0 0 24px rgba(0,245,255,0.06)',
        }}
      >
        <IconButton variant="ghost" size="md" onClick={() => setMobileSidebarOpen(!mobileSidebarOpen)} title="会话列表" className="mobile-touch-target" aria-label="打开会话列表">
          <Menu size={18} />
        </IconButton>

        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-2">
            <div
              className="w-7 h-7 rounded-[var(--radius-md)] flex items-center justify-center"
              style={{ background: 'var(--gradient-accent)', boxShadow: '0 0 12px var(--accent-glow)' }}
            >
              <Zap size={14} style={{ color: '#fff' }} />
            </div>
            <span className="font-display text-sm font-semibold tracking-wider" style={{ color: 'var(--accent)' }}>Mac Agent</span>
          </div>
          <StatusDot status={wsStatus} size="sm" />
        </div>

        <div className="flex items-center gap-0.5">
          <IconButton variant="ghost" onClick={onOpenDuck} title="Duck 分身" className="mobile-touch-target" aria-label="Duck 分身管理"><Bird size={17} /></IconButton>
          <IconButton variant="ghost" onClick={onOpenMonitor} title="监控" className="mobile-touch-target" aria-label="监控仪表板"><BarChart3 size={17} /></IconButton>
          <IconButton variant="ghost" onClick={() => setMobilePanelOpen(true, 'tools')} title="工具" className="mobile-touch-target" aria-label="工具面板"><Wrench size={17} /></IconButton>
          <IconButton variant="ghost" onClick={() => setMobilePanelOpen(true, 'notifications')} title="通知" badge={unreadCount} className="mobile-touch-target" aria-label="通知面板"><Bell size={17} /></IconButton>
          <IconButton variant="ghost" onClick={onOpenSettings} title="设置" className="mobile-touch-target" aria-label="设置"><Settings size={17} /></IconButton>
        </div>
      </div>
    );
  }

  // ---- 桌面端工具栏 (与官方站 header 风格一致) ----
  return (
    <div
      className="flex items-center justify-between px-4 h-13 flex-shrink-0 select-none"
      style={{
        background: 'var(--glass-bg)',
        backdropFilter: 'var(--glass-blur)',
        WebkitBackdropFilter: 'var(--glass-blur)',
        borderBottom: '1px solid var(--border)',
        boxShadow: '0 0 30px rgba(0,245,255,0.08)',
      }}
    >
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div
            className="w-7 h-7 rounded-[var(--radius-md)] flex items-center justify-center"
            style={{ background: 'var(--gradient-accent)', boxShadow: '0 0 12px var(--accent-glow)' }}
          >
            <Zap size={14} style={{ color: '#fff' }} />
          </div>
          <span className="font-display text-sm font-bold tracking-wider" style={{ color: 'var(--accent)' }}>
            Mac Agent
          </span>
        </div>
        <span
          className="font-display text-[10px] font-semibold px-2 py-0.5 rounded-[var(--radius-full)] tracking-wider"
          style={{ background: 'var(--accent-dim)', color: 'var(--accent)', border: '1px solid rgba(0,245,255,0.2)' }}
        >
          WEB
        </span>
      </div>

      <div className="flex items-center gap-2.5">
        <StatusDot status={wsStatus} size="sm" />
        <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{statusLabel}</span>
      </div>

      <div className="flex items-center gap-1">
        <IconButton variant="subtle" size="sm" onClick={onOpenDuck} title="Duck 分身" aria-label="Duck 分身管理"><Bird size={14} /></IconButton>
        <IconButton variant="subtle" size="sm" onClick={onOpenMonitor} title="监控仪表板" aria-label="监控仪表板"><BarChart3 size={14} /></IconButton>
        <IconButton variant="subtle" size="sm" active={showRightPanel && rightTab === 'tools'} onClick={() => { if (!showRightPanel) toggleRightPanel(); onRightTabChange('tools'); }} title="工具面板" aria-label="工具面板"><Wrench size={14} /></IconButton>
        <IconButton variant="subtle" size="sm" active={showRightPanel && rightTab === 'notifications'} badge={unreadCount} onClick={() => { if (!showRightPanel) toggleRightPanel(); onRightTabChange('notifications'); }} title="系统消息" aria-label="系统消息"><Bell size={14} /></IconButton>
        <div className="w-px h-5 mx-1.5" style={{ background: 'var(--border)' }} />
        <IconButton variant="subtle" size="sm" onClick={onOpenSettings} title="设置" aria-label="设置"><Settings size={14} /></IconButton>
      </div>
    </div>
  );
};

export default Toolbar;
