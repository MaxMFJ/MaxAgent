import React from 'react';
import { useMonitorStore } from '../../stores/monitorStore';

const SystemStatus: React.FC = () => {
  const health = useMonitorStore((s) => s.systemHealth);
  const stats = useMonitorStore((s) => s.usageStats);

  const services = [
    { name: '后端服务', status: health.backend },
    { name: 'WebSocket', status: health.websocket === 'connected' ? 'online' : health.websocket === 'connecting' ? 'unknown' : 'offline' },
    { name: '向量存储', status: health.vectorStore },
    { name: '本地 LLM', status: health.localLlm },
    { name: 'EvoMap', status: health.evomap },
  ] as const;

  const statusColor = (s: string) => {
    if (s === 'online' || s === 'connected') return 'var(--green)';
    if (s === 'offline' || s === 'disconnected') return 'var(--red)';
    return 'var(--orange)';
  };

  const statusLabel = (s: string) => {
    if (s === 'online' || s === 'connected') return '在线';
    if (s === 'offline' || s === 'disconnected') return '离线';
    return '检测中';
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <span className="text-xs font-medium" style={{ color: 'var(--accent)' }}>SYS — 系统状态</span>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* 服务健康 */}
        <div>
          <div className="text-xs font-medium mb-2" style={{ color: 'var(--text-tertiary)' }}>服务健康</div>
          <div className="space-y-1.5">
            {services.map((svc) => (
              <div
                key={svc.name}
                className="flex items-center justify-between px-3 py-1.5 rounded-[var(--radius-md)] text-xs"
                style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}
              >
                <span style={{ color: 'var(--text-primary)' }}>{svc.name}</span>
                <div className="flex items-center gap-1.5">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ background: statusColor(svc.status), boxShadow: `0 0 4px ${statusColor(svc.status)}` }}
                  />
                  <span style={{ color: statusColor(svc.status) }}>{statusLabel(svc.status)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 用量统计 */}
        <div>
          <div className="text-xs font-medium mb-2" style={{ color: 'var(--text-tertiary)' }}>用量统计</div>
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: '总请求', value: stats.totalRequests },
              { label: '成功', value: stats.successCount },
              { label: '总 Token', value: stats.totalTokens.toLocaleString() },
              { label: '输入 Token', value: stats.inputTokens.toLocaleString() },
              { label: '输出 Token', value: stats.outputTokens.toLocaleString() },
              { label: '成功率', value: stats.totalRequests > 0 ? `${((stats.successCount / stats.totalRequests) * 100).toFixed(1)}%` : '-' },
            ].map((item) => (
              <div
                key={item.label}
                className="px-3 py-2 rounded-[var(--radius-md)] text-xs"
                style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}
              >
                <div style={{ color: 'var(--text-tertiary)' }}>{item.label}</div>
                <div className="text-sm font-semibold mt-0.5" style={{ color: 'var(--accent)' }}>{item.value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SystemStatus;
