import React, { useRef, useState, useCallback } from 'react';
import type { KeyboardEvent } from 'react';
import { useChatStore } from '../stores/chatStore';
import { useWSStore } from '../stores/wsStore';
import { useResponsive } from '../hooks/useResponsive';
import { Button, IconButton, Textarea } from './ui';
import { Send, Square, Bot } from 'lucide-react';
import { v4 as uuid } from 'uuid';

const InputBar: React.FC = () => {
  const [text, setText] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const activeConvId = useChatStore((s) => s.activeConversationId);
  const createConversation = useChatStore((s) => s.createConversation);
  const addMessage = useChatStore((s) => s.addMessage);
  const sendChat = useWSStore((s) => s.sendChat);
  const stopGeneration = useWSStore((s) => s.stopGeneration);
  const sendAutonomousTask = useWSStore((s) => s.sendAutonomousTask);
  const wsStatus = useWSStore((s) => s.status);
  const { isMobile } = useResponsive();

  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }, []);

  const handleSend = useCallback((isAutonomous = false) => {
    const msg = text.trim();
    if (!msg || isStreaming) return;

    let convId = activeConvId;
    if (!convId) {
      convId = createConversation(msg.slice(0, 30));
    } else {
      const conv = useChatStore.getState().conversations.find(c => c.id === convId);
      if (conv && conv.messages.length === 0 && conv.title.startsWith('新会话')) {
        useChatStore.getState().renameConversation(convId, msg.slice(0, 30));
      }
    }

    const displayContent = isAutonomous ? `🤖 [自主任务] ${msg}` : msg;

    addMessage(convId, {
      id: uuid(),
      role: 'user',
      content: displayContent,
      timestamp: Date.now(),
      isAutonomous,
    });

    const assistantId = uuid();
    addMessage(convId, {
      id: assistantId,
      role: 'assistant',
      content: isAutonomous ? '' : '',
      timestamp: Date.now(),
      isStreaming: true,
      isAutonomous,
    });

    useChatStore.getState().setStreaming(true);

    if (isAutonomous) {
      sendAutonomousTask(msg);
    } else {
      sendChat(msg, convId);
    }

    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [text, isStreaming, activeConvId, createConversation, addMessage, sendChat, sendAutonomousTask]);

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend(false);
    }
    if (e.key === 'Enter' && e.shiftKey && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSend(true);
    }
  };

  const canSend = text.trim() && wsStatus === 'connected' && !isStreaming;

  return (
    <div
      className="flex-shrink-0 px-4 sm:px-6 py-3 sm:py-4"
      style={{ background: 'var(--bg-base)' }}
    >
      <div className="max-w-3xl mx-auto min-w-0">
        <div
          className="flex items-end gap-2 rounded-[var(--radius-xl)] px-4 sm:px-5 py-3 transition-all duration-[var(--duration-normal)] min-w-0"
          style={{
            background: 'var(--bg-elevated)',
            border: `1px solid ${isFocused ? 'var(--border-focus)' : 'var(--border)'}`,
            boxShadow: isFocused ? 'var(--shadow-glow-accent)' : 'var(--shadow-sm)',
          }}
        >
          <Textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => { setText(e.target.value); autoResize(); }}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={wsStatus === 'connected'
              ? (isMobile ? '输入消息…' : '输入消息… Shift+Enter 换行，⌘⇧↵ 自主任务')
              : '等待连接…'
            }
            disabled={wsStatus !== 'connected'}
            className="flex-1 min-w-0 bg-transparent resize-none border-0 shadow-none focus-visible:ring-0 min-h-0 py-0 text-sm leading-relaxed"
            style={{
              color: 'var(--text-primary)',
              minHeight: isMobile ? 32 : 24,
              maxHeight: 200,
              fontSize: isMobile ? 16 : undefined,
              paddingRight: 4,
            }}
            rows={1}
            aria-label="消息输入框"
          />

          <div className="flex items-center gap-2 flex-shrink-0 pb-0.5">
            {isStreaming ? (
              <Button
                variant="danger"
                size="sm"
                icon={<Square size={12} />}
                onClick={stopGeneration}
              >
                停止
              </Button>
            ) : (
              <>
                <IconButton
                  variant="ghost"
                  size="sm"
                  disabled={!canSend}
                  onClick={() => handleSend(true)}
                  title="自主任务 (⌘⇧↵)"
                  className="disabled:opacity-30 transition-transform duration-200 hover:scale-105"
                  aria-label="发送自主任务"
                >
                  <Bot size={16} style={{ color: canSend ? 'var(--purple)' : undefined }} />
                </IconButton>

                <Button
                  variant={canSend ? 'primary' : 'secondary'}
                  size="sm"
                  disabled={!canSend}
                  onClick={() => handleSend(false)}
                  icon={<Send size={13} />}
                  aria-label="发送消息"
                >
                  发送
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default InputBar;
