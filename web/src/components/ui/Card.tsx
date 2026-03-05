import React from 'react';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  active?: boolean;
  onClick?: () => void;
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

const paddings = {
  none: '',
  sm: 'p-2.5',
  md: 'p-3.5',
  lg: 'p-5',
};

export const Card: React.FC<CardProps> = ({
  children,
  className = '',
  hover = false,
  active = false,
  onClick,
  padding = 'md',
}) => {
  return (
    <div
      className={`
        rounded-[var(--radius-lg)] border border-[var(--border)]
        bg-[var(--bg-elevated)] relative overflow-hidden
        ${paddings[padding]}
        ${hover ? 'transition-all duration-[var(--duration-normal)] hover:border-[var(--border-hover)] hover:bg-[var(--bg-hover)] hover:shadow-[var(--shadow-sm)] hover:-translate-y-0.5' : ''}
        ${active ? 'border-[var(--border-focus)] bg-[var(--bg-hover)] shadow-[var(--shadow-glow)]' : ''}
        ${onClick ? 'cursor-pointer active:scale-[0.98]' : ''}
        ${className}
      `}
      onClick={onClick}
    >
      {children}
    </div>
  );
};
