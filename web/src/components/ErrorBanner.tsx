import React, { useState, useEffect } from 'react';
import { IconButton } from './ui';
import { X } from 'lucide-react';

interface Props {
  message: string;
  type?: 'error' | 'warning' | 'info';
  onDismiss?: () => void;
  autoDismiss?: number; // ms
}

const ErrorBanner: React.FC<Props> = ({ message, type = 'error', onDismiss, autoDismiss }) => {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (autoDismiss && autoDismiss > 0) {
      const t = setTimeout(() => { setVisible(false); onDismiss?.(); }, autoDismiss);
      return () => clearTimeout(t);
    }
  }, [autoDismiss, onDismiss]);

  if (!visible) return null;

  const colors = {
    error: { bg: 'rgba(251,113,133,0.08)', border: 'rgba(251,113,133,0.20)', text: 'var(--red)', icon: '⚠️' },
    warning: { bg: 'rgba(251,191,36,0.08)', border: 'rgba(251,191,36,0.20)', text: 'var(--orange)', icon: '⚡' },
    info: { bg: 'var(--accent-dim)', border: 'var(--border-glow)', text: 'var(--accent)', icon: 'ℹ️' },
  }[type];

  return (
    <div
      className="flex items-center gap-2 px-4 py-2 text-sm"
      style={{ background: colors.bg, borderBottom: `1px solid ${colors.border}`, color: colors.text }}
    >
      <span>{colors.icon}</span>
      <span className="flex-1">{message}</span>
      {onDismiss && (
        <IconButton
          variant="ghost"
          size="sm"
          onClick={() => { setVisible(false); onDismiss(); }}
          className="opacity-60 hover:opacity-100"
          style={{ color: colors.text }}
          aria-label="关闭"
        >
          <X size={12} />
        </IconButton>
      )}
    </div>
  );
};

export default ErrorBanner;
