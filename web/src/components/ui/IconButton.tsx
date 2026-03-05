import React from 'react';

type Variant = 'ghost' | 'subtle' | 'outlined';
type Size = 'sm' | 'md' | 'lg';

interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  active?: boolean;
  badge?: number;
}

const sizeMap: Record<Size, string> = {
  sm: 'w-7 h-7 rounded-[var(--radius-md)]',
  md: 'w-8 h-8 rounded-[var(--radius-md)]',
  lg: 'w-10 h-10 rounded-[var(--radius-lg)]',
};

export const IconButton: React.FC<IconButtonProps> = ({
  variant = 'ghost',
  size = 'md',
  active,
  badge,
  children,
  className = '',
  ...props
}) => {
  const baseClasses = `
    relative inline-flex items-center justify-center
    transition-all duration-[var(--duration-normal)]
    cursor-pointer select-none
    disabled:opacity-35 disabled:cursor-not-allowed
    active:scale-[0.92]
    ${sizeMap[size]}
  `;

  const variantClasses = {
    ghost: `text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] ${active ? 'text-[var(--accent)] bg-[var(--accent-dim)]' : ''}`,
    subtle: `text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] border border-[var(--border)] ${active ? 'text-[var(--accent)] border-[var(--border-focus)] bg-[var(--accent-dim)]' : ''}`,
    outlined: `text-[var(--text-secondary)] hover:text-[var(--text-primary)] border border-[var(--border)] hover:border-[var(--border-hover)] ${active ? 'text-[var(--accent)] border-[var(--border-focus)]' : ''}`,
  }[variant];

  return (
    <button className={`${baseClasses} ${variantClasses} ${className}`} {...props}>
      {children}
      {badge !== undefined && badge > 0 && (
        <span
          className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 flex items-center justify-center rounded-full text-[10px] font-semibold"
          style={{ background: 'var(--red)', color: '#fff' }}
        >
          {badge > 99 ? '99+' : badge}
        </span>
      )}
    </button>
  );
};
