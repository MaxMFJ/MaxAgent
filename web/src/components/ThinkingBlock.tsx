import React, { useState } from 'react';

interface Props {
  thinking: string;
}

const ThinkingBlock: React.FC<Props> = ({ thinking }) => {
  const [expanded, setExpanded] = useState(false);

  if (!thinking) return null;

  return (
    <div className="mb-3 rounded-[var(--radius-lg)] overflow-hidden" style={{ border: '1px solid rgba(177,151,252,0.12)' }}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3.5 py-2 text-xs cursor-pointer transition-all duration-200 hover:brightness-110"
        style={{ background: 'rgba(177,151,252,0.06)', color: 'var(--purple)' }}
        aria-expanded={expanded}
        aria-label="展开思考过程"
      >
        <span className="transition-transform duration-200" style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0)' }}>▶</span>
        <span className="font-medium">思考过程</span>
        <span style={{ color: 'var(--text-tertiary)' }}>({thinking.length} 字)</span>
      </button>
      {expanded && (
        <div
          className="px-3.5 py-2.5 text-xs leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto animate-fade-in-up"
          style={{ background: 'rgba(177,151,252,0.03)', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
        >
          {thinking}
        </div>
      )}
    </div>
  );
};

export default ThinkingBlock;
