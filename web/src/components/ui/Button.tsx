import React from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: React.ReactNode;
  loading?: boolean;
}

const variants: Record<Variant, string> = {
  primary: 'bg-[var(--accent-solid)] text-white hover:brightness-110 shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)]',
  secondary: 'bg-[var(--bg-elevated)] text-[var(--text-primary)] border border-[var(--border)] hover:bg-[var(--bg-hover)] hover:border-[var(--border-hover)]',
  ghost: 'bg-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]',
  danger: 'bg-[var(--red-dim)] text-[var(--red)] border border-[rgba(251,113,133,0.15)] hover:bg-[rgba(251,113,133,0.18)]',
};

const sizes: Record<Size, string> = {
  sm: 'h-7 px-3 text-xs gap-1.5 rounded-[var(--radius-md)]',
  md: 'h-9 px-4 text-sm gap-2 rounded-[var(--radius-md)]',
  lg: 'h-11 px-5 text-sm gap-2 rounded-[var(--radius-lg)]',
};

export const Button: React.FC<ButtonProps> = ({
  variant = 'secondary',
  size = 'md',
  icon,
  loading,
  disabled,
  children,
  className = '',
  ...props
}) => {
  return (
    <button
      className={`
        inline-flex items-center justify-center font-semibold
        transition-all duration-[var(--duration-normal)]
        cursor-pointer select-none
        disabled:opacity-35 disabled:cursor-not-allowed disabled:pointer-events-none
        active:scale-[0.97]
        ${variants[variant]}
        ${sizes[size]}
        ${className}
      `}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="60" strokeDashoffset="20" strokeLinecap="round" />
        </svg>
      ) : icon ? (
        <span className="flex-shrink-0 flex items-center">{icon}</span>
      ) : null}
      {children && <span>{children}</span>}
    </button>
  );
};
