import React from 'react';

interface SkeletonProps {
  width?: string;
  height?: string;
  rounded?: boolean;
  className?: string;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  width,
  height = '12px',
  rounded = false,
  className = '',
}) => {
  return (
    <div
      className={`animate-pulse bg-[var(--bg-hover)] ${rounded ? 'rounded-full' : 'rounded-[var(--radius-sm)]'} ${className}`}
      style={{ width, height }}
    />
  );
};
