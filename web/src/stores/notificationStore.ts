import { create } from 'zustand';
import { v4 as uuid } from 'uuid';
import type { SystemNotification } from '../types';

interface NotificationState {
  notifications: SystemNotification[];
  unreadCount: number;

  addNotification: (type: SystemNotification['type'], message: string) => void;
  markAllRead: () => void;
  clearAll: () => void;
  removeNotification: (id: string) => void;
}

export const useNotificationStore = create<NotificationState>((set) => ({
  notifications: [],
  unreadCount: 0,

  addNotification(type, message) {
    const n: SystemNotification = {
      id: uuid(),
      type,
      message,
      timestamp: Date.now(),
      read: false,
    };
    set((s) => ({
      notifications: [n, ...s.notifications].slice(0, 200),
      unreadCount: s.unreadCount + 1,
    }));
  },

  markAllRead() {
    set((s) => ({
      notifications: s.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    }));
  },

  clearAll() { set({ notifications: [], unreadCount: 0 }); },

  removeNotification(id) {
    set((s) => {
      const n = s.notifications.find((x) => x.id === id);
      return {
        notifications: s.notifications.filter((x) => x.id !== id),
        unreadCount: n && !n.read ? s.unreadCount - 1 : s.unreadCount,
      };
    });
  },
}));
