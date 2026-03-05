import React, { useState, useRef, useEffect } from 'react';
import { useMonitorStore } from '../../stores/monitorStore';

type LogSource = 'all' | 'tool' | 'system' | 'notification';
type LogLevel = 'all' | 'info' | 'warn' | 'error' | 'debug';

const LogStream: React.FC = () => {
  const logs = useMonitorStore((s) => s.logs);
  const actionLogs = useMonitorStore((s) => s.actionLogs);
  const clearLogs = useMonitorStore((s) => s.clearLogs);
  const [source, setSource] = useState<LogSource>('all');
  const [level, setLevel] = useState<LogLevel>('all');
  const [search, setSearch] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs.length, actionLogs.length]);

  const allLogs = [
    ...logs.map((l) => ({ ...l, logType: 'system' as const })),
    ...actionLogs.map((l) => ({ timestamp: l.timestamp, level: 'info' as const, message: `[${l.action}] ${l.target ?? ''} ${l.result ?? ''}`, source: 'tool', logType: 'tool' as const })),
  ].sort((a, b) => a.timestamp - b.timestamp);

  const filtered = allLogs.filter((l) => {
    if (source !== 'all' && l.logType !== source) return false;
    if (level !== 'all' && l.level !== level) return false;
    if (search && !l.message.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const levelColor = (lv: string) => {
    switch (lv) {
      case 'error': return 'var(--red)';
      case 'warn': return 'var(--orange)';
      case 'debug': return 'var(--purple)';
      default: return 'var(--text-tertiary)';
    }
  };

  const sources: LogSource[] = ['all', 'tool', 'system'];
  const levels: LogLevel[] = ['all', 'info', 'warn', 'error', 'debug'];

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 space-y-2" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium" style={{ color: 'var(--accent)' }}>LOGS — 日志流</span>
          <div className="flex items-center gap-2">
            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{filtered.length} 条</span>
            <button onClick={clearLogs} className="text-xs cursor-pointer transition-colors hover:opacity-80" style={{ color: 'var(--text-tertiary)' }}>清除</button>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Source filter */}
          <div className="flex gap-1">
            {sources.map((s) => (
              <button
                key={s}
                onClick={() => setSource(s)}
                className="text-xs px-2 py-0.5 rounded-[var(--radius-md)] cursor-pointer transition-all duration-200 font-medium"
                style={{
                  background: source === s ? 'var(--accent-dim)' : 'transparent',
                  color: source === s ? 'var(--accent)' : 'var(--text-tertiary)',
                  border: `1px solid ${source === s ? 'color-mix(in srgb, var(--accent) 15%, transparent)' : 'var(--border-subtle)'}`,
                }}
              >
                {s === 'all' ? '全部' : s === 'tool' ? '工具' : '系统'}
              </button>
            ))}
          </div>
          {/* Level filter */}
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value as LogLevel)}
            className="text-xs px-2 py-0.5 rounded-[var(--radius-md)] outline-none cursor-pointer"
            style={{ background: 'var(--bg-base)', color: 'var(--text-tertiary)', border: '1px solid var(--border-subtle)' }}
          >
            {levels.map((l) => (
              <option key={l} value={l}>{l === 'all' ? '全级别' : l.toUpperCase()}</option>
            ))}
          </select>
          {/* Search */}
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索…"
            className="flex-1 text-xs px-2 py-0.5 rounded-[var(--radius-md)] outline-none"
            style={{ background: 'var(--bg-base)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
          />
        </div>
      </div>

      <div
        className="flex-1 overflow-y-auto px-4 py-2 text-xs"
        style={{ fontFamily: 'var(--font-mono)', background: 'var(--bg-base)' }}
      >
        {filtered.length === 0 ? (
          <div className="text-center py-8" style={{ color: 'var(--text-tertiary)' }}>暂无日志</div>
        ) : (
          filtered.map((log, i) => (
            <div key={i} className="flex gap-2 py-0.5 leading-relaxed hover:bg-white/[0.02]">
              <span style={{ color: 'var(--text-tertiary)', opacity: 0.5, flexShrink: 0 }}>
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
              <span style={{ color: levelColor(log.level), flexShrink: 0, width: 40 }}>
                {log.level.toUpperCase().padEnd(5)}
              </span>
              <span style={{ color: 'var(--text-primary)' }}>{log.message}</span>
            </div>
          ))
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
};

export default LogStream;
