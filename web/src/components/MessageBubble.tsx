import React, { useMemo, useState, useCallback } from 'react';
import type { Message } from '../types';
import MarkdownRenderer from './MarkdownRenderer';
import ThinkingBlock from './ThinkingBlock';
import FileDownloadCard from './FileDownloadCard';
import { Avatar, Badge, Card, IconButton } from './ui';
import { extractFilePaths } from '../utils/filePaths';
import { Bot, User, AlertTriangle, Copy, Check, Trash2, Wrench, Clock } from 'lucide-react';

interface Props {
  message: Message;
  onDelete?: (msgId: string) => void;
}

const MessageBubble: React.FC<Props> = ({ message, onDelete }) => {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const [copied, setCopied] = useState(false);
  const [showActions, setShowActions] = useState(false);

  const filePaths = useMemo(() => {
    if (isUser) return [];
    return extractFilePaths(message.content);
  }, [message.content, isUser]);

  const showTyping = message.isStreaming && !message.content;

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [message.content]);

  return (
    <div
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-6 group animate-fade-in-up w-full min-w-0`}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      {/* Assistant Avatar */}
      {!isUser && (
        <Avatar
          icon={isSystem ? <AlertTriangle size={14} /> : <Bot size={14} />}
          size="sm"
          variant={isSystem ? 'warning' : message.isAutonomous ? 'purple' : 'default'}
          className="mt-1.5 mr-2.5 flex-shrink-0"
        />
      )}

      <div className={`${isUser ? 'max-w-[80%] sm:max-w-[65%]' : 'max-w-[90%] sm:max-w-[80%]'} relative min-w-0 ${isUser ? 'ml-auto' : ''}`}>
        <Card
          padding="none"
          className={`
            overflow-hidden break-words transition-all duration-[var(--duration-fast)]
            ${isUser ? 'rounded-[20px] rounded-br-[6px] px-5 py-4 sm:px-6 sm:py-5' : 'rounded-[20px] rounded-bl-[6px] px-6 py-5 sm:px-7 sm:py-6'}
            ${isUser ? 'bg-[var(--bg-card)] border-[var(--border)]' : isSystem ? 'bg-[var(--red-dim)] border-[rgba(251,113,133,0.2)]' : 'bg-[var(--card)] border-[var(--border)]'}
          `}
        >
          {/* Role Label */}
          {!isUser ? (
            <div className="flex items-center gap-2 mb-3">
              <Badge variant={isSystem ? 'danger' : message.isAutonomous ? 'purple' : 'accent'}>
                {isSystem ? '系统' : message.isAutonomous ? 'AI 自主执行' : '助手'}
              </Badge>
              {message.isAutonomous && <Badge variant="purple">自治</Badge>}
            </div>
          ) : null}

          {/* Thinking Block */}
          {message.thinking && <ThinkingBlock thinking={message.thinking} />}

          {/* Content */}
          {showTyping ? (
            <div className="flex gap-2 py-2.5 px-1">
              <span className="typing-dot w-2 h-2 rounded-full" style={{ background: 'var(--accent)' }} />
              <span className="typing-dot w-2 h-2 rounded-full" style={{ background: 'var(--accent)' }} />
              <span className="typing-dot w-2 h-2 rounded-full" style={{ background: 'var(--accent)' }} />
            </div>
          ) : isUser ? (
            <div className="text-sm whitespace-pre-wrap leading-relaxed tracking-wide" style={{ color: 'var(--text-primary)', overflowWrap: 'anywhere' }}>
              {message.content}
            </div>
          ) : (
            <div className="text-sm min-w-0 break-words" style={{ overflowWrap: 'break-word', paddingRight: 4 }}>
              <MarkdownRenderer content={message.content} />
            </div>
          )}

          {/* Images */}
          {message.images && message.images.length > 0 && (
            <div className="mt-3.5 space-y-2.5">
              {message.images.map((img, i) => (
                <div key={i} className="rounded-[var(--radius-lg)] overflow-hidden" style={{ border: '1px solid var(--border)' }}>
                  <img
                    src={`data:${img.mimeType};base64,${img.base64}`}
                    alt={img.path ?? `Image ${i + 1}`}
                    className="max-w-full max-h-96 object-contain"
                    style={{ background: 'var(--bg-base)' }}
                    loading="lazy"
                  />
                  {img.path && (
                    <div className="px-3 py-2 text-xs truncate" style={{ color: 'var(--text-tertiary)', background: 'var(--bg-overlay)' }}>
                      {img.path}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* File Download Cards */}
          {filePaths.length > 0 && (
            <div className="mt-3.5 space-y-2">
              {filePaths.map((fp) => (
                <FileDownloadCard key={fp} filePath={fp} />
              ))}
            </div>
          )}

          {/* Tool Calls */}
          {message.toolCalls && message.toolCalls.length > 0 && (
            <div className="mt-3.5 space-y-2">
              {message.toolCalls.map((tc) => (
                <Card key={tc.id} padding="sm" className="text-xs bg-[var(--green-dim)] border-[rgba(74,222,128,0.2)]">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 font-medium" style={{ color: 'var(--green)' }}>
                      <Wrench size={12} />
                      {tc.toolName}
                    </span>
                    {tc.status === 'running' && (
                      <Badge variant="warning" dot>运行中</Badge>
                    )}
                    {tc.status === 'success' && (
                      <span className="flex items-center gap-1" style={{ color: 'var(--green)' }}>
                        <Check size={12} />
                        {tc.endTime && tc.startTime ? `${((tc.endTime - tc.startTime) / 1000).toFixed(1)}s` : ''}
                      </span>
                    )}
                    {tc.status === 'error' && (
                      <Badge variant="danger">失败</Badge>
                    )}
                  </div>
                  {tc.result && tc.status !== 'running' && (
                    <div className="mt-2 line-clamp-2 text-[var(--text-tertiary)]">
                      {tc.result.slice(0, 200)}
                    </div>
                  )}
                </Card>
              ))}
            </div>
          )}

          {/* Footer: Timestamp + Model Info */}
          {(message.modelName || message.tokenUsage || true) && (
            <div className="flex items-center justify-between mt-3 pt-2.5 flex-wrap gap-y-1" style={{ borderTop: message.modelName ? '1px solid var(--border-subtle)' : 'none', paddingBottom: 2 }}>
              <div className="flex items-center gap-2 text-[11px] min-w-0" style={{ color: 'var(--text-tertiary)' }}>
                {!isUser && message.modelName && (
                  <Badge variant="default">{message.modelName}</Badge>
                )}
                {!isUser && message.tokenUsage && (
                  <span className="flex items-center gap-1">
                    <Clock size={10} />
                    {message.tokenUsage.totalTokens} tokens
                  </span>
                )}
              </div>
              <span className="text-[11px] flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
                {new Date(message.timestamp).toLocaleTimeString()}
              </span>
            </div>
          )}
        </Card>

        {/* Hover Actions */}
        {showActions && !message.isStreaming && message.content && (
          <Card padding="sm" className="absolute -top-3 right-2 flex items-center gap-0.5 rounded-[var(--radius-lg)] animate-scale-in z-10 bg-[var(--bg-overlay)] border-[var(--border)] shadow-md backdrop-blur-[12px]">
            <IconButton
              variant="ghost"
              size="sm"
              onClick={handleCopy}
              title="复制"
              aria-label="复制消息"
              className={copied ? 'text-[var(--green)]' : ''}
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
            </IconButton>
            {onDelete && (
              <IconButton
                variant="ghost"
                size="sm"
                onClick={() => onDelete(message.id)}
                title="删除"
                aria-label="删除消息"
                className="hover:text-[var(--red)]"
              >
                <Trash2 size={12} />
              </IconButton>
            )}
          </Card>
        )}
      </div>

      {/* User Avatar */}
      {isUser && (
        <Avatar
          icon={<User size={14} />}
          size="sm"
          variant="default"
          className="mt-1.5 ml-3 flex-shrink-0"
        />
      )}
    </div>
  );
};

export default React.memo(MessageBubble);
