import { create } from 'zustand';
import wsService from '../services/websocket';
import type { WSMessage } from '../types';

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected';

interface WSState {
  status: ConnectionStatus;
  sessionId: string | null;
  hasRunningTask: boolean;
  hasRunningChat: boolean;
  connect: () => void;
  disconnect: () => void;
  reconnect: () => void;
  sendChat: (content: string, sessionId?: string) => void;
  stopGeneration: () => void;
  sendAutonomousTask: (task: string) => void;
  sendResumeTask: (sessionId: string) => void;
  sendResumeChat: (sessionId: string) => void;
  onMessage: (type: string, fn: (msg: WSMessage) => void) => () => void;
}

export const useWSStore = create<WSState>((set) => ({
  status: 'disconnected',
  sessionId: null,
  hasRunningTask: false,
  hasRunningChat: false,

  connect() {
    set({ status: 'connecting' });
    wsService.connect();

    wsService.on('session_init', (msg) => {
      const s = (msg as any)._status as string;
      if (s === 'connected') {
        set({
          status: 'connected',
          sessionId: wsService.sessionId,
          hasRunningTask: wsService.hasRunningTask,
          hasRunningChat: wsService.hasRunningChat,
        });
      } else {
        set({ status: 'disconnected', sessionId: null });
      }
    });
  },

  disconnect() {
    wsService.disconnect();
    set({ status: 'disconnected', sessionId: null });
  },

  reconnect() {
    set({ status: 'connecting' });
    wsService.reconnect();
  },

  sendChat(content, sessionId) {
    wsService.sendChat(content, sessionId);
  },

  stopGeneration() {
    wsService.sendStopGeneration();
  },

  sendAutonomousTask(task) {
    wsService.sendAutonomousTask(task);
  },

  sendResumeTask(sessionId) {
    wsService.sendResumeTask(sessionId);
  },

  sendResumeChat(sessionId) {
    wsService.sendResumeChat(sessionId);
  },

  onMessage(type, fn) {
    return wsService.on(type as any, fn);
  },
}));
