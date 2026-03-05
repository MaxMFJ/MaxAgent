import { create } from 'zustand';
import { v4 as uuid } from 'uuid';
import type { Conversation, Message } from '../types';

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  isStreaming: boolean;

  /* actions */
  createConversation: (title?: string) => string;
  deleteConversation: (id: string) => void;
  setActiveConversation: (id: string | null) => void;
  renameConversation: (id: string, title: string) => void;

  addMessage: (convId: string, msg: Message) => void;
  updateMessage: (convId: string, msgId: string, patch: Partial<Message>) => void;
  appendToMessage: (convId: string, msgId: string, chunk: string) => void;
  appendThinking: (convId: string, msgId: string, chunk: string) => void;

  setStreaming: (v: boolean) => void;
  getActiveConversation: () => Conversation | undefined;
  getMessages: (convId: string) => Message[];
}

const STORAGE_KEY = 'macagent-web-conversations';

function persist(conversations: Conversation[]) {
  try {
    // 仅保存最近 50 个会话
    const toSave = conversations.slice(-50);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
  } catch { /* quota */ }
}

function loadPersisted(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: loadPersisted(),
  activeConversationId: null,
  isStreaming: false,

  createConversation(title) {
    const id = uuid();
    const conv: Conversation = {
      id,
      title: title ?? `新会话 ${get().conversations.length + 1}`,
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messages: [],
    };
    set((s) => {
      const next = [...s.conversations, conv];
      persist(next);
      return { conversations: next, activeConversationId: id };
    });
    return id;
  },

  deleteConversation(id) {
    set((s) => {
      const next = s.conversations.filter((c) => c.id !== id);
      persist(next);
      const activeId = s.activeConversationId === id ? (next[next.length - 1]?.id ?? null) : s.activeConversationId;
      return { conversations: next, activeConversationId: activeId };
    });
  },

  setActiveConversation(id) {
    set({ activeConversationId: id });
  },

  renameConversation(id, title) {
    set((s) => {
      const next = s.conversations.map((c) => c.id === id ? { ...c, title, updatedAt: Date.now() } : c);
      persist(next);
      return { conversations: next };
    });
  },

  addMessage(convId, msg) {
    set((s) => {
      const next = s.conversations.map((c) => {
        if (c.id !== convId) return c;
        return { ...c, messages: [...c.messages, msg], updatedAt: Date.now() };
      });
      persist(next);
      return { conversations: next };
    });
  },

  updateMessage(convId, msgId, patch) {
    set((s) => {
      const next = s.conversations.map((c) => {
        if (c.id !== convId) return c;
        return {
          ...c,
          messages: c.messages.map((m) => m.id === msgId ? { ...m, ...patch } : m),
          updatedAt: Date.now(),
        };
      });
      persist(next);
      return { conversations: next };
    });
  },

  appendToMessage(convId, msgId, chunk) {
    set((s) => {
      const next = s.conversations.map((c) => {
        if (c.id !== convId) return c;
        return {
          ...c,
          messages: c.messages.map((m) => m.id === msgId ? { ...m, content: m.content + chunk } : m),
        };
      });
      // 流式传输时不频繁写 localStorage
      return { conversations: next };
    });
  },

  appendThinking(convId, msgId, chunk) {
    set((s) => {
      const next = s.conversations.map((c) => {
        if (c.id !== convId) return c;
        return {
          ...c,
          messages: c.messages.map((m) =>
            m.id === msgId ? { ...m, thinking: (m.thinking ?? '') + chunk } : m,
          ),
        };
      });
      return { conversations: next };
    });
  },

  setStreaming(v) { set({ isStreaming: v }); },

  getActiveConversation() {
    const s = get();
    return s.conversations.find((c) => c.id === s.activeConversationId);
  },

  getMessages(convId) {
    return get().conversations.find((c) => c.id === convId)?.messages ?? [];
  },
}));
