import { create } from 'zustand';
import type { BackendConfig } from '../types';

interface SettingsState {
  config: BackendConfig;
  sidebarWidth: number;
  rightPanelWidth: number;
  showRightPanel: boolean;
  theme: 'dark';

  /** 移动端：侧边栏是否可见（抽屉模式） */
  mobileSidebarOpen: boolean;
  /** 移动端：右侧面板是否可见（抽屉模式） */
  mobilePanelOpen: boolean;
  /** 移动端面板类型 */
  mobilePanelTab: 'tools' | 'notifications';

  updateConfig: (patch: Partial<BackendConfig>) => void;
  setConfig: (config: BackendConfig) => void;
  setSidebarWidth: (w: number) => void;
  setRightPanelWidth: (w: number) => void;
  toggleRightPanel: () => void;
  setMobileSidebarOpen: (v: boolean) => void;
  setMobilePanelOpen: (v: boolean, tab?: 'tools' | 'notifications') => void;
}

const SETTINGS_KEY = 'macagent-web-settings';

function loadSettings(): Partial<SettingsState> {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

function saveSettings(state: Pick<SettingsState, 'config' | 'sidebarWidth' | 'rightPanelWidth' | 'showRightPanel'>) {
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(state)); } catch {}
}

const saved = loadSettings();

export const useSettingsStore = create<SettingsState>((set, get) => ({
  config: {
    serverUrl: 'http://127.0.0.1:8765',
    provider: 'deepseek',
    model: '',
    apiKey: '',
    baseUrl: '',
    temperature: 0.7,
    maxTokens: 4096,
    autonomousMode: false,
    maxAutonomousSteps: 25,
    ...(saved as any)?.config,
  },
  sidebarWidth: (saved as any)?.sidebarWidth ?? 260,
  rightPanelWidth: (saved as any)?.rightPanelWidth ?? 320,
  showRightPanel: (saved as any)?.showRightPanel ?? false,
  theme: 'dark' as const,

  mobileSidebarOpen: false,
  mobilePanelOpen: false,
  mobilePanelTab: 'tools' as const,

  updateConfig(patch) {
    set((s) => {
      const config = { ...s.config, ...patch };
      saveSettings({ ...s, config });
      return { config };
    });
  },

  setConfig(config) {
    set((s) => {
      saveSettings({ ...s, config });
      return { config };
    });
  },

  setSidebarWidth(w) {
    set({ sidebarWidth: w });
    saveSettings(get());
  },

  setRightPanelWidth(w) {
    set({ rightPanelWidth: w });
    saveSettings(get());
  },

  toggleRightPanel() {
    set((s) => {
      const next = !s.showRightPanel;
      saveSettings({ ...s, showRightPanel: next });
      return { showRightPanel: next };
    });
  },

  setMobileSidebarOpen(v) {
    set({ mobileSidebarOpen: v, mobilePanelOpen: false });
  },

  setMobilePanelOpen(v, tab) {
    set((s) => ({
      mobilePanelOpen: v,
      mobilePanelTab: tab ?? s.mobilePanelTab,
      mobileSidebarOpen: false,
    }));
  },
}));
