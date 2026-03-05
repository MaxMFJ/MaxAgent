import React, { useEffect, useState } from 'react';
import { getFileInfo, getFileDownloadUrl } from '../services/api';
import { getFileIcon } from '../utils/filePaths';
import type { FileInfo } from '../types';

interface Props {
  filePath: string;
}

const FileDownloadCard: React.FC<Props> = ({ filePath }) => {
  const [info, setInfo] = useState<FileInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [hover, setHover] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    getFileInfo(filePath)
      .then((data) => {
        if (!cancelled) setInfo(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [filePath]);

  const handleDownload = () => {
    const url = getFileDownloadUrl(filePath);
    const a = document.createElement('a');
    a.href = url;
    a.download = info?.name ?? filePath.split('/').pop() ?? 'file';
    a.click();
  };

  const ext = filePath.split('.').pop() ?? '';
  const icon = info?.icon ?? getFileIcon(ext);
  const name = info?.name ?? filePath.split('/').pop() ?? 'Unknown';

  if (loading) {
    return (
      <div
        className="flex items-center gap-3 px-4 py-3 rounded-[var(--radius-lg)] my-1 animate-pulse"
        style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}
      >
        <div className="w-10 h-10 rounded-[var(--radius-lg)]" style={{ background: 'var(--bg-overlay)' }} />
        <div className="flex-1">
          <div className="h-3 w-32 rounded-[var(--radius-sm)]" style={{ background: 'var(--bg-overlay)' }} />
          <div className="h-2 w-48 rounded-[var(--radius-sm)] mt-1.5" style={{ background: 'var(--bg-overlay)' }} />
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex items-center gap-3 px-4 py-3 rounded-[var(--radius-lg)] my-1 cursor-pointer transition-all duration-200"
      style={{
        background: hover ? 'var(--bg-overlay)' : 'var(--bg-elevated)',
        border: `1px solid ${hover ? 'color-mix(in srgb, var(--accent) 15%, transparent)' : 'var(--border-subtle)'}`,
        boxShadow: hover ? 'var(--shadow-glow-accent)' : 'none',
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={handleDownload}
    >
      {/* 图标 */}
      <div
        className="flex items-center justify-center w-10 h-10 rounded-[var(--radius-lg)] text-lg flex-shrink-0"
        style={{ background: 'var(--accent-dim)' }}
      >
        {icon}
      </div>

      {/* 信息 */}
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
          {name}
        </div>
        <div className="flex items-center gap-2 text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
          {info?.sizeFormatted && <span>{info.sizeFormatted}</span>}
          {ext && <span className="uppercase" style={{ color: 'var(--accent)', opacity: 0.7 }}>.{ext}</span>}
          {error && <span style={{ color: 'var(--red)' }}>{error}</span>}
        </div>
        <div className="text-xs mt-0.5 truncate" style={{ color: 'var(--text-tertiary)', opacity: 0.5 }}>
          {filePath}
        </div>
      </div>

      {/* 下载按钮 */}
      <div
        className="flex items-center justify-center w-8 h-8 rounded-[var(--radius-lg)] flex-shrink-0 transition-colors"
        style={{ background: hover ? 'var(--accent-dim)' : 'transparent' }}
      >
        <span style={{ color: 'var(--accent)', fontSize: '1.1em' }}>⬇</span>
      </div>
    </div>
  );
};

export default React.memo(FileDownloadCard);
