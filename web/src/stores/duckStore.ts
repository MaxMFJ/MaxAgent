import { create } from 'zustand';
import * as api from '../services/api';

export interface DuckInfo {
  duck_id: string;
  name: string;
  duck_type: string;
  status: 'online' | 'busy' | 'offline';
  skills: string[];
  hostname: string;
  platform: string;
  is_local: boolean;
  completed_tasks: number;
  failed_tasks: number;
  current_task_id: string | null;
}

export interface DuckTemplate {
  duck_type: string;
  name: string;
  description: string;
  skills: string[];
  icon: string;
}

export interface EggRecord {
  egg_id: string;
  duck_type: string;
  name: string;
  token: string;
  created_at: number;
  downloaded: boolean;
  connected: boolean;
}

export interface DuckStats {
  total: number;
  online: number;
  busy: number;
  offline: number;
  total_completed: number;
  total_failed: number;
  by_type: Record<string, number>;
}

interface DuckState {
  ducks: DuckInfo[];
  templates: DuckTemplate[];
  eggs: EggRecord[];
  stats: DuckStats | null;
  loading: boolean;
  error: string | null;

  fetchDucks: () => Promise<void>;
  fetchTemplates: () => Promise<void>;
  fetchEggs: () => Promise<void>;
  fetchStats: () => Promise<void>;
  fetchAll: () => Promise<void>;
  createLocalDuck: (name: string, duckType: string, skills?: string[]) => Promise<void>;
  destroyLocalDuck: (duckId: string) => Promise<void>;
  removeDuck: (duckId: string) => Promise<void>;
  createEgg: (duckType: string, name?: string) => Promise<EggRecord>;
  deleteEgg: (eggId: string) => Promise<void>;
  clearError: () => void;
}

export const useDuckStore = create<DuckState>((set, get) => ({
  ducks: [],
  templates: [],
  eggs: [],
  stats: null,
  loading: false,
  error: null,

  async fetchDucks() {
    try {
      const res = await api.getDuckList();
      set({ ducks: res.ducks });
    } catch (e: any) {
      set({ error: e.message });
    }
  },

  async fetchTemplates() {
    try {
      const res = await api.getDuckTemplates();
      set({ templates: res.templates });
    } catch (e: any) {
      set({ error: e.message });
    }
  },

  async fetchEggs() {
    try {
      const res = await api.getEggs();
      set({ eggs: res.eggs });
    } catch (e: any) {
      set({ error: e.message });
    }
  },

  async fetchStats() {
    try {
      const res = await api.getDuckStats();
      set({ stats: res });
    } catch (e: any) {
      set({ error: e.message });
    }
  },

  async fetchAll() {
    set({ loading: true, error: null });
    await Promise.all([
      get().fetchDucks(),
      get().fetchTemplates(),
      get().fetchEggs(),
      get().fetchStats(),
    ]);
    set({ loading: false });
  },

  async createLocalDuck(name, duckType, skills) {
    try {
      await api.createLocalDuck(name, duckType, skills ?? []);
      await get().fetchDucks();
      await get().fetchStats();
    } catch (e: any) {
      set({ error: e.message });
    }
  },

  async destroyLocalDuck(duckId) {
    try {
      await api.destroyLocalDuck(duckId);
      await get().fetchDucks();
      await get().fetchStats();
    } catch (e: any) {
      set({ error: e.message });
    }
  },

  async removeDuck(duckId) {
    try {
      await api.removeDuck(duckId);
      await get().fetchDucks();
      await get().fetchStats();
    } catch (e: any) {
      set({ error: e.message });
    }
  },

  async createEgg(duckType, name?) {
    try {
      const res = await api.createEgg(duckType, name);
      await get().fetchEggs();
      return res.egg;
    } catch (e: any) {
      set({ error: e.message });
      throw e;
    }
  },

  async deleteEgg(eggId) {
    try {
      await api.deleteEgg(eggId);
      await get().fetchEggs();
    } catch (e: any) {
      set({ error: e.message });
    }
  },

  clearError() {
    set({ error: null });
  },
}));
