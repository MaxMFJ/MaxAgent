import React, { useRef, useEffect } from 'react';
import { useMonitorStore } from '../../stores/monitorStore';

const NeuralStream: React.FC = () => {
  const neuralStream = useMonitorStore((s) => s.neuralStream);
  const isStreaming = useMonitorStore((s) => s.isStreaming);
  const clearNeuralStream = useMonitorStore((s) => s.clearNeuralStream);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [neuralStream]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium" style={{ color: 'var(--accent)' }}>EXEC — Neural Stream</span>
          {isStreaming && (
            <span
              className="text-xs px-1.5 py-0.5 rounded-[var(--radius-sm)]"
              style={{ background: 'color-mix(in srgb, var(--red) 20%, transparent)', color: 'var(--red)' }}
            >
              LIVE
            </span>
          )}
        </div>
        <button onClick={clearNeuralStream} className="text-xs cursor-pointer transition-colors hover:opacity-80" style={{ color: 'var(--text-tertiary)' }}>清除</button>
      </div>
      <div
        className="flex-1 overflow-y-auto px-4 py-3 whitespace-pre-wrap text-xs leading-relaxed"
        style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', background: 'var(--bg-base)' }}
      >
        {neuralStream || (
          <span style={{ color: 'var(--text-tertiary)' }}>等待 LLM 输出…</span>
        )}
        {isStreaming && (
          <span className="inline-block w-2 h-4 ml-0.5 animate-pulse" style={{ background: 'var(--accent)' }} />
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
};

export default NeuralStream;
