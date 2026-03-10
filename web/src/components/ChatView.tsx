import React, { useRef, useEffect, useState, useCallback } from 'react';
import { useChatStore } from '../stores/chatStore';
import MessageBubble from './MessageBubble';
import InputBar from './InputBar';
import WelcomeView from './WelcomeView';
import { Button, Card } from './ui';
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
    <div className="chat-view-fill relative" style={{ background: 'var(--bg-base)' }}>
      {/* Subtle gradient overlay at top */}
      <div
        className="absolute top-0 left-0 right-0 h-8 pointer-events-none z-10"
        style={{ background: 'linear-gradient(to bottom, var(--bg-base), transparent)' }}
      />

      {/* 消息列表 */}
      <div
        ref={containerRef}
        className="chat-view-scroll px-4 sm:px-6 py-4 sm:py-6"
        onScroll={handleScroll}
      >
        <div className="chat-view-inner">
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <Card padding="md" className="text-sm text-[var(--text-tertiary)]">
                开始输入消息吧…
              </Card>
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
          <Button
            variant="outline"
            size="sm"
            icon={<ChevronDown size={14} />}
            onClick={() => {
              messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
              setUserScrolledUp(false);
            }}
            className="shadow-md backdrop-blur-[12px] hover:scale-105 text-[var(--accent)] border-[var(--border)] bg-[var(--bg-elevated)]"
          >
            回到底部
          </Button>
        </div>
      )}

      {/* 输入栏 */}
      <InputBar />
    </div>
  );
};

export default ChatView;
