import { create } from 'zustand';
import type { ActionLogEntry, ExecutionLogEntry } from '../types';

export interface ExecutionStep {
  id: string;
  action: string;
  target?: string;
  status: 'pending' | 'executing' | 'success' | 'failed';
  startTime: number;
  endTime?: number;
  result?: string;
}

export interface SystemHealth {
  backend: 'online' | 'offline' | 'unknown';
  websocket: 'connected' | 'disconnected' | 'connecting';
  vectorStore: 'online' | 'offline' | 'unknown';
  localLlm: 'online' | 'offline' | 'unknown';
  evomap: 'online' | 'offline' | 'unknown';
}

export interface UsageStats {
  totalRequests: number;
  successCount: number;
  totalTokens: number;
  inputTokens: number;
  outputTokens: number;
}

interface MonitorState {
  executionSteps: ExecutionStep[];
  neuralStream: string;
  isStreaming: boolean;
  systemHealth: SystemHealth;
  usageStats: UsageStats;
  logs: ExecutionLogEntry[];
  actionLogs: ActionLogEntry[];

  addStep: (step: ExecutionStep) => void;
  updateStep: (id: string, patch: Partial<ExecutionStep>) => void;
  clearSteps: () => void;
  appendNeuralStream: (chunk: string) => void;
  clearNeuralStream: () => void;
  setIsStreaming: (v: boolean) => void;
  setSystemHealth: (patch: Partial<SystemHealth>) => void;
  updateUsageStats: (patch: Partial<UsageStats>) => void;
  addLog: (log: ExecutionLogEntry) => void;
  addActionLog: (log: ActionLogEntry) => void;
  clearLogs: () => void;
}

export const useMonitorStore = create<MonitorState>((set) => ({
  executionSteps: [],
  neuralStream: '',
  isStreaming: false,
  systemHealth: {
    backend: 'unknown',
    websocket: 'disconnected',
    vectorStore: 'unknown',
    localLlm: 'unknown',
    evomap: 'unknown',
  },
  usageStats: {
    totalRequests: 0, successCount: 0, totalTokens: 0, inputTokens: 0, outputTokens: 0,
  },
  logs: [],
  actionLogs: [],

  addStep(step) {
    set((s) => ({ executionSteps: [...s.executionSteps.slice(-200), step] }));
  },
  updateStep(id, patch) {
    set((s) => ({
      executionSteps: s.executionSteps.map((st) => st.id === id ? { ...st, ...patch } : st),
    }));
  },
  clearSteps() { set({ executionSteps: [] }); },
  appendNeuralStream(chunk) {
    set((s) => ({ neuralStream: s.neuralStream + chunk }));
  },
  clearNeuralStream() { set({ neuralStream: '' }); },
  setIsStreaming(v) { set({ isStreaming: v }); },
  setSystemHealth(patch) {
    set((s) => ({ systemHealth: { ...s.systemHealth, ...patch } }));
  },
  updateUsageStats(patch) {
    set((s) => ({ usageStats: { ...s.usageStats, ...patch } }));
  },
  addLog(log) {
    set((s) => ({ logs: [...s.logs.slice(-500), log] }));
  },
  addActionLog(log) {
    set((s) => ({ actionLogs: [...s.actionLogs.slice(-500), log] }));
  },
  clearLogs() { set({ logs: [], actionLogs: [] }); },
}));
