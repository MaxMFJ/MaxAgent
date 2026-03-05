import React, { useState } from 'react';
import ExecutionTimeline from './dashboard/ExecutionTimeline';
import NeuralStream from './dashboard/NeuralStream';
import SystemStatus from './dashboard/SystemStatus';
import LogStream from './dashboard/LogStream';

type Tab = 'exec' | 'sys' | 'logs';

interface Props {
  onClose: () => void;
  isMobile?: boolean;
}

const MonitorDashboard: React.FC<Props> = ({ onClose, isMobile }) => {
  const [tab, setTab] = useState<Tab>('exec');

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'exec', label: '执行', icon: '⚡' },
    { id: 'sys', label: '系统', icon: '💻' },
    { id: 'logs', label: '日志', icon: '📜' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center mobile-overlay-bg animate-fade-in-up" style={{ animationDuration: '0.2s' }}>
      <div
        className={isMobile
          ? "w-full h-full flex flex-col"
          : "w-[90vw] max-w-[1200px] h-[80vh] rounded-[var(--radius-2xl)] overflow-hidden flex flex-col animate-scale-in"
        }
        style={{ background: 'var(--bg-surface)', border: isMobile ? 'none' : '1px solid var(--border)', boxShadow: 'var(--shadow-lg)' }}
      >
        {/* 顶部 */}
        <div
          className="flex items-center justify-between px-5 py-3.5 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--border-subtle)' }}
        >
          <div className="flex items-center gap-4">
            <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>📊 监控仪表板</span>
            <div className="flex gap-1">
              {tabs.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className="text-xs px-3.5 py-1.5 rounded-[var(--radius-md)] cursor-pointer transition-all duration-200 font-medium"
                  style={{
                    background: tab === t.id ? 'var(--accent-dim)' : 'transparent',
                    color: tab === t.id ? 'var(--accent)' : 'var(--text-tertiary)',
                    border: `1px solid ${tab === t.id ? 'rgba(124,156,255,0.12)' : 'transparent'}`,
                  }}
                >
                  {t.icon} {t.label}
                </button>
              ))}
            </div>
          </div>
          <button onClick={onClose} className="text-lg cursor-pointer w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-all duration-200 hover:bg-[var(--bg-hover)]" style={{ color: 'var(--text-tertiary)' }} aria-label="关闭监控">✕</button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-hidden">
          {tab === 'exec' && (
            <div className={isMobile ? "flex flex-col h-full overflow-auto" : "flex h-full"}>
              <div className={isMobile ? "" : "flex-1"} style={isMobile ? {} : { borderRight: '1px solid var(--border-subtle)' }}>
                <ExecutionTimeline />
              </div>
              <div className={isMobile ? "" : "w-[400px] flex-shrink-0"} style={isMobile ? { borderTop: '1px solid var(--border-subtle)' } : {}}>
                <NeuralStream />
              </div>
            </div>
          )}
          {tab === 'sys' && <SystemStatus />}
          {tab === 'logs' && <LogStream />}
        </div>

        {/* 底部状态栏 */}
        <div
          className="flex items-center justify-between px-4 py-1.5 text-xs flex-shrink-0"
          style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-tertiary)', opacity: 0.6 }}
        >
          <span>Mac Agent Monitor</span>
          <span>{new Date().toLocaleTimeString()}</span>
        </div>
      </div>
    </div>
  );
};

export default MonitorDashboard;
