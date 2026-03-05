import React, { useRef, useEffect } from 'react';
import { useMonitorStore, type ExecutionStep } from '../../stores/monitorStore';

const statusColor = (status: ExecutionStep['status']) => {
  switch (status) {
    case 'executing': return 'var(--orange)';
    case 'success': return 'var(--green)';
    case 'failed': return 'var(--red)';
    default: return 'var(--text-tertiary)';
  }
};

const statusIcon = (status: ExecutionStep['status']) => {
  switch (status) {
    case 'executing': return '⟳';
    case 'success': return '✓';
    case 'failed': return '✗';
    default: return '○';
  }
};

const ExecutionTimeline: React.FC = () => {
  const steps = useMonitorStore((s) => s.executionSteps);
  const clearSteps = useMonitorStore((s) => s.clearSteps);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [steps.length]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <span className="text-xs font-medium" style={{ color: 'var(--accent)' }}>EXEC — 执行时间轴</span>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{steps.length} 步</span>
          <button onClick={clearSteps} className="text-xs cursor-pointer transition-colors hover:opacity-80" style={{ color: 'var(--text-tertiary)' }}>清除</button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-2">
        {steps.length === 0 ? (
          <div className="text-xs text-center py-8" style={{ color: 'var(--text-tertiary)' }}>暂无执行步骤</div>
        ) : (
          <div className="relative">
            {/* 竖线 */}
            <div className="absolute left-3 top-0 bottom-0 w-px" style={{ background: 'var(--border-subtle)' }} />
            {steps.map((step) => (
              <div key={step.id} className="relative pl-8 pb-3">
                {/* 节点 */}
                <div
                  className="absolute left-1.5 top-1 w-3 h-3 rounded-full flex items-center justify-center text-xs"
                  style={{
                    background: 'var(--bg-surface)',
                    border: `2px solid ${statusColor(step.status)}`,
                    boxShadow: step.status === 'executing' ? `0 0 8px ${statusColor(step.status)}` : 'none',
                  }}
                />
                <div
                  className="px-3 py-2 rounded-[var(--radius-md)] text-xs"
                  style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}
                >
                  <div className="flex items-center justify-between">
                    <span style={{ color: 'var(--text-primary)' }}>{step.action}</span>
                    <span style={{ color: statusColor(step.status) }}>{statusIcon(step.status)}</span>
                  </div>
                  {step.target && (
                    <div className="mt-0.5 truncate" style={{ color: 'var(--text-tertiary)' }}>{step.target}</div>
                  )}
                  {step.result && (
                    <div className="mt-0.5 truncate" style={{ color: 'var(--text-tertiary)', opacity: 0.6 }}>{step.result.slice(0, 150)}</div>
                  )}
                  <div className="mt-1" style={{ color: 'var(--text-tertiary)', opacity: 0.5 }}>
                    {new Date(step.startTime).toLocaleTimeString()}
                    {step.endTime && ` → ${((step.endTime - step.startTime) / 1000).toFixed(1)}s`}
                  </div>
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>
        )}
      </div>
    </div>
  );
};

export default ExecutionTimeline;
