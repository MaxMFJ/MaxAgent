import React from 'react';

type Variant = 'default' | 'accent' | 'success' | 'warning' | 'danger' | 'purple';

interface BadgeProps {
  variant?: Variant;
  children: React.ReactNode;
  dot?: boolean;
  className?: string;
}

const variantStyles: Record<Variant, string> = {
  default: 'bg-[var(--bg-overlay)] text-[var(--text-secondary)]',
  accent: 'bg-[var(--accent-dim)] text-[var(--accent)]',
  success: 'bg-[var(--green-dim)] text-[var(--green)]',
  warning: 'bg-[var(--orange-dim)] text-[var(--orange)]',
  danger: 'bg-[var(--red-dim)] text-[var(--red)]',
  purple: 'bg-[var(--purple-dim)] text-[var(--purple)]',
};

export const Badge: React.FC<BadgeProps> = ({
  variant = 'default',
  children,
  dot,
  className = '',
}) => {
  return (
    <span
      className={`
        inline-flex items-center gap-1.5 px-2 py-0.5
        text-[11px] font-medium leading-tight
        rounded-[var(--radius-full)]
        ${variantStyles[variant]}
        ${className}
      `}
    >
      {dot && (
        <span
          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
          style={{ background: 'currentColor' }}
        />
      )}
      {children}
    </span>
  );
};
