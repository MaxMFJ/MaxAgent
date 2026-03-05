import React from 'react';

type Status = 'online' | 'offline' | 'connecting' | 'warning';

interface StatusDotProps {
  status: Status;
  size?: 'sm' | 'md';
  pulse?: boolean;
  label?: string;
}

const colorMap: Record<Status, string> = {
  online: 'var(--green)',
  offline: 'var(--red)',
  connecting: 'var(--orange)',
  warning: 'var(--orange)',
};

export const StatusDot: React.FC<StatusDotProps> = ({
  status,
  size = 'sm',
  pulse = true,
  label,
}) => {
  const dotSize = size === 'sm' ? 'w-2 h-2' : 'w-2.5 h-2.5';
  const color = colorMap[status];

  return (
    <div className="inline-flex items-center gap-1.5">
      <span
        className={`${dotSize} rounded-full flex-shrink-0`}
        style={{
          background: color,
          boxShadow: pulse ? `0 0 6px ${color}` : 'none',
        }}
      />
      {label && (
        <span className="text-xs text-[var(--text-secondary)]">{label}</span>
      )}
    </div>
  );
};
