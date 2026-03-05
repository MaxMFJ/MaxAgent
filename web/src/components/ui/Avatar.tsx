import React from 'react';

type Size = 'sm' | 'md' | 'lg';

interface AvatarProps {
  icon?: React.ReactNode;
  size?: Size;
  variant?: 'accent' | 'purple' | 'green' | 'warning';
  className?: string;
}

const sizeMap: Record<Size, string> = {
  sm: 'w-7 h-7 text-xs',
  md: 'w-8 h-8 text-sm',
  lg: 'w-10 h-10 text-base',
};

const variantMap = {
  accent: 'bg-[var(--accent-dim)] text-[var(--accent)] border-[rgba(124,156,255,0.12)]',
  purple: 'bg-[var(--purple-dim)] text-[var(--purple)] border-[rgba(177,151,252,0.12)]',
  green: 'bg-[var(--green-dim)] text-[var(--green)] border-[rgba(74,222,128,0.12)]',
  warning: 'bg-[var(--orange-dim)] text-[var(--orange)] border-[rgba(251,191,36,0.12)]',
};

export const Avatar: React.FC<AvatarProps> = ({
  icon,
  size = 'md',
  variant = 'accent',
  className = '',
}) => {
  return (
    <div
      className={`
        flex-shrink-0 rounded-[var(--radius-lg)] border
        flex items-center justify-center
        transition-all duration-200
        ${sizeMap[size]}
        ${variantMap[variant]}
        ${className}
      `}
    >
      {icon}
    </div>
  );
};
