import React, { useRef, useEffect, useState, useCallback } from 'react';
import { useChatStore } from '../stores/chatStore';
import MessageBubble from './MessageBubble';
import InputBar from './InputBar';
import WelcomeView from './WelcomeView';
import { ChevronDown } from 'lucide-react';

const ChatView: React.FC = () => {
  const activeConvId = useChatStore((s) => s.activeConversationId);
  const conversations = useChatStore((s) => s.conversations);
  const conv = conversations.find((c) => c.id === activeConvId);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [userScrolledUp, setUserScrolledUp] = useState(false);

  const messages = conv?.messages ?? [];

  // 检测用户是否手动上滚
  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setUserScrolledUp(distFromBottom > 100);
  }, []);

  // 新消息时自动滚到底部（除非用户手动上滚）
  useEffect(() => {
    if (!userScrolledUp) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length, messages[messages.length - 1]?.content, userScrolledUp]);

  const handleDeleteMessage = useCallback((msgId: string) => {
    if (!activeConvId) return;
    const store = useChatStore.getState();
    const conv = store.conversations.find(c => c.id === activeConvId);
    if (!conv) return;
    const filtered = conv.messages.filter(m => m.id !== msgId);
    useChatStore.setState(s => ({
      conversations: s.conversations.map(c =>
        c.id === activeConvId ? { ...c, messages: filtered, updatedAt: Date.now() } : c
      ),
    }));
  }, [activeConvId]);

  if (!activeConvId) {
    return <WelcomeView />;
  }

  return (
    <div className="flex flex-col h-full min-h-0 relative" style={{ background: 'var(--bg-base)' }}>
      {/* Subtle gradient overlay at top */}
      <div
        className="absolute top-0 left-0 right-0 h-8 pointer-events-none z-10"
        style={{ background: 'linear-gradient(to bottom, var(--bg-base), transparent)' }}
      />

      {/* 消息列表 */}
      <div
        ref={containerRef}
        className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 sm:px-6 py-4 sm:py-6"
        onScroll={handleScroll}
      >
        <div className="w-full max-w-3xl mx-auto min-w-0">
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div
                className="text-sm px-5 py-3 rounded-[var(--radius-xl)]"
                style={{ color: 'var(--text-tertiary)', background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
              >
                开始输入消息吧…
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                onDelete={handleDeleteMessage}
              />
            ))
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* 用户上滚时显示"回到底部"按钮 */}
      {userScrolledUp && messages.length > 0 && (
        <div className="absolute bottom-[80px] left-1/2 -translate-x-1/2 z-20 animate-fade-in-up">
          <button
            onClick={() => {
              messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
              setUserScrolledUp(false);
            }}
            className="flex items-center gap-1.5 text-xs px-4 py-2 rounded-[var(--radius-full)] cursor-pointer transition-all duration-200 hover:scale-105"
            style={{
              background: 'var(--bg-elevated)',
              color: 'var(--accent)',
              border: '1px solid var(--border)',
              boxShadow: 'var(--shadow-md)',
              backdropFilter: 'blur(12px)',
            }}
          >
            <ChevronDown size={14} />
            回到底部
          </button>
        </div>
      )}

      {/* 输入栏 */}
      <InputBar />
    </div>
  );
};

export default ChatView;
