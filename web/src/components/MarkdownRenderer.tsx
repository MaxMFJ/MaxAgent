import React, { useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
interface Props {
  content: string;
}

const CodeBlock: React.FC<{
  className?: string;
  children: React.ReactNode;
}> = ({ className, children }) => {
  const [copied, setCopied] = useState(false);
  const match = /language-(\w+)/.exec(className ?? '');
  const lang = match?.[1] ?? '';
  const codeStr = String(children).replace(/\n$/, '');

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(codeStr).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [codeStr]);

  return (
    <div className="relative my-2 rounded-[var(--radius-lg)] overflow-hidden max-w-full" style={{ background: 'var(--bg-base)', border: '1px solid var(--border-subtle)' }}>
      <div
        className="flex items-center justify-between px-3 py-1"
        style={{ background: 'var(--bg-overlay)', borderBottom: '1px solid var(--border-subtle)' }}
      >
        <span className="text-xs" style={{ color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
          {lang || 'code'}
        </span>
        <button
          onClick={handleCopy}
          className="text-xs px-2 py-0.5 rounded-[var(--radius-sm)] cursor-pointer transition-colors"
          style={{ color: copied ? 'var(--green)' : 'var(--text-tertiary)', background: 'transparent' }}
        >
          {copied ? '已复制 ✓' : '复制'}
        </button>
      </div>
      <pre className="p-3 overflow-x-auto" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85em' }}>
        <code className={className}>{children}</code>
      </pre>
    </div>
  );
};

const components = {
  code({ className, children }: { className?: string; children?: React.ReactNode }) {
    const isInline = !className && typeof children === 'string' && !children.includes('\n');
    if (isInline) {
      return <code className={className}>{children}</code>;
    }
    return <CodeBlock className={className}>{children}</CodeBlock>;
  },
};

const MarkdownRenderer: React.FC<Props> = ({ content }) => {
  return (
    <div className="markdown-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};

export default React.memo(MarkdownRenderer);
