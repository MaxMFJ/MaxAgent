import { create } from 'zustand';
import type { ToolDefinition, ToolCall, TaskProgress } from '../types';

interface ToolState {
  tools: ToolDefinition[];
  callHistory: ToolCall[];
  activeTask: TaskProgress | null;

  setTools: (tools: ToolDefinition[]) => void;
  addCallToHistory: (call: ToolCall) => void;
  updateCallInHistory: (id: string, patch: Partial<ToolCall>) => void;
  setActiveTask: (task: TaskProgress | null) => void;
  updateTaskProgress: (patch: Partial<TaskProgress>) => void;
  clearHistory: () => void;
}

export const useToolStore = create<ToolState>((set) => ({
  tools: [],
  callHistory: [],
  activeTask: null,

  setTools(tools) { set({ tools }); },

  addCallToHistory(call) {
    set((s) => ({ callHistory: [...s.callHistory.slice(-100), call] }));
  },

  updateCallInHistory(id, patch) {
    set((s) => ({
      callHistory: s.callHistory.map((c) => c.id === id ? { ...c, ...patch } : c),
    }));
  },

  setActiveTask(task) { set({ activeTask: task }); },

  updateTaskProgress(patch) {
    set((s) => ({
      activeTask: s.activeTask ? { ...s.activeTask, ...patch } : null,
    }));
  },

  clearHistory() { set({ callHistory: [] }); },
}));
