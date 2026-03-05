import React, { useState, useEffect } from 'react';
import { useSettingsStore } from '../stores/settingsStore';
import { useWSStore } from '../stores/wsStore';
import { getConfig, updateConfig as apiUpdateConfig, getHealth } from '../services/api';

interface Props {
  onClose: () => void;
  isMobile?: boolean;
}

type SettingsTab = 'model' | 'general' | 'service' | 'about';

const PROVIDERS = [
  { id: 'deepseek', label: 'DeepSeek', defaultUrl: 'https://api.deepseek.com/v1', defaultModel: 'deepseek-chat' },
  { id: 'newapi', label: 'NewAPI', defaultUrl: '', defaultModel: '' },
  { id: 'openai', label: 'ChatGPT', defaultUrl: 'https://api.openai.com/v1', defaultModel: 'gpt-4' },
  { id: 'gemini', label: 'Gemini', defaultUrl: '', defaultModel: 'gemini-pro' },
  { id: 'claude', label: 'Claude', defaultUrl: 'https://api.anthropic.com', defaultModel: 'claude-3-opus' },
  { id: 'ollama', label: 'Ollama', defaultUrl: 'http://127.0.0.1:11434', defaultModel: 'qwen2.5' },
  { id: 'lmstudio', label: 'LM Studio', defaultUrl: 'http://127.0.0.1:1234/v1', defaultModel: '' },
];

const SettingsModal: React.FC<Props> = ({ onClose, isMobile }) => {
  const config = useSettingsStore((s) => s.config);
  const updateConfig = useSettingsStore((s) => s.updateConfig);
  const wsStatus = useWSStore((s) => s.status);
  const reconnect = useWSStore((s) => s.reconnect);

  const [tab, setTab] = useState<SettingsTab>('model');
  const [form, setForm] = useState({ ...config });
  const [saving, setSaving] = useState(false);
  const [healthStatus, setHealthStatus] = useState<Record<string, unknown> | null>(null);
  const [loadingHealth, setLoadingHealth] = useState(false);

  // 加载后端配置
  useEffect(() => {
    getConfig().then((data) => {
      const p = data as any;
      setForm(prev => ({
        ...prev,
        provider: p.provider ?? prev.provider,
        model: p.model ?? prev.model,
        baseUrl: p.base_url ?? prev.baseUrl,
      }));
    }).catch(() => {});
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      // 保存到后端
      await apiUpdateConfig({
        provider: form.provider,
        model: form.model,
        api_key: form.apiKey,
        base_url: form.baseUrl,
      });
      // 保存到本地
      updateConfig(form);
    } catch (e) {
      console.error('Save failed:', e);
    } finally {
      setSaving(false);
    }
  };

  const handleProviderChange = (providerId: string) => {
    const p = PROVIDERS.find(x => x.id === providerId);
    setForm({
      ...form,
      provider: providerId,
      model: p?.defaultModel ?? '',
      baseUrl: p?.defaultUrl ?? '',
    });
  };

  const checkHealth = async () => {
    setLoadingHealth(true);
    try {
      const data = await getHealth();
      setHealthStatus(data);
    } catch (e) {
      setHealthStatus({ error: (e as Error).message });
    } finally {
      setLoadingHealth(false);
    }
  };

  const inputClass = 'w-full px-3 py-2 rounded-[var(--radius-md)] text-sm outline-none transition-all duration-200 focus:ring-2 focus:ring-[var(--accent-dim)]';
  const inputStyle = {
    background: 'var(--bg-base)',
    color: 'var(--text-primary)',
    border: '1px solid var(--border-subtle)',
  };

  const tabs: { id: SettingsTab; label: string; icon: string }[] = [
    { id: 'model', label: '模型', icon: '🧠' },
    { id: 'general', label: '通用', icon: '⚙️' },
    { id: 'service', label: '服务', icon: '🖥️' },
    { id: 'about', label: '关于', icon: 'ℹ️' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center mobile-overlay-bg animate-fade-in-up" style={{ animationDuration: '0.2s' }}>
      <div
        className={isMobile
          ? "w-full h-full flex flex-col"
          : "w-[580px] max-h-[82vh] rounded-[var(--radius-2xl)] overflow-hidden flex flex-col animate-scale-in"
        }
        style={{ background: 'var(--bg-surface)', border: isMobile ? 'none' : '1px solid var(--border)', boxShadow: 'var(--shadow-lg)' }}
      >
        {/* 标题 */}
        <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>设置</h2>
          <button onClick={onClose} className="cursor-pointer text-lg w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-all duration-200 hover:bg-[var(--bg-hover)]" style={{ color: 'var(--text-tertiary)' }} aria-label="关闭设置">✕</button>
        </div>

        {/* Tab 导航 */}
        <div className="flex px-6 pt-3 gap-1" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="text-sm px-3.5 pb-2.5 cursor-pointer transition-all duration-200 font-medium"
              style={{
                color: tab === t.id ? 'var(--accent)' : 'var(--text-tertiary)',
                borderBottom: tab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
              }}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {/* 模型 Tab */}
          {tab === 'model' && (
            <>
              {/* AI 提供商 */}
              <div>
                <label className="text-xs mb-2 block font-medium" style={{ color: 'var(--text-tertiary)' }}>AI 提供商</label>
                <div className={isMobile ? "grid grid-cols-3 gap-1.5" : "grid grid-cols-4 gap-1.5"}>
                  {PROVIDERS.map(p => (
                    <button
                      key={p.id}
                      onClick={() => handleProviderChange(p.id)}
                      className="text-xs py-2 rounded-[var(--radius-md)] cursor-pointer transition-all duration-200 font-medium"
                      style={{
                        background: form.provider === p.id ? 'var(--accent-dim)' : 'var(--bg-elevated)',
                        color: form.provider === p.id ? 'var(--accent)' : 'var(--text-tertiary)',
                        border: `1px solid ${form.provider === p.id ? 'color-mix(in srgb, var(--accent) 20%, transparent)' : 'var(--border-subtle)'}`,
                      }}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Base URL */}
              <div>
                <label className="text-xs mb-1 block" style={{ color: 'var(--text-tertiary)' }}>Base URL</label>
                <input
                  className={inputClass}
                  style={inputStyle}
                  value={form.baseUrl ?? ''}
                  onChange={(e) => setForm({ ...form, baseUrl: e.target.value })}
                  placeholder="API 基础地址"
                />
              </div>

              {/* Model */}
              <div>
                <label className="text-xs mb-1 block" style={{ color: 'var(--text-tertiary)' }}>模型名称</label>
                <input
                  className={inputClass}
                  style={inputStyle}
                  value={form.model}
                  onChange={(e) => setForm({ ...form, model: e.target.value })}
                  placeholder="例如 deepseek-chat, gpt-4"
                />
              </div>

              {/* API Key */}
              <div>
                <label className="text-xs mb-1 block" style={{ color: 'var(--text-tertiary)' }}>API Key</label>
                <input
                  className={inputClass}
                  style={inputStyle}
                  type="password"
                  value={form.apiKey ?? ''}
                  onChange={(e) => setForm({ ...form, apiKey: e.target.value })}
                  placeholder="API 密钥"
                />
              </div>

              {/* Temperature */}
              <div>
                <label className="text-xs mb-1 block" style={{ color: 'var(--text-tertiary)' }}>
                  Temperature: {form.temperature}
                </label>
                <input
                  type="range" min="0" max="2" step="0.1"
                  value={form.temperature}
                  onChange={(e) => setForm({ ...form, temperature: parseFloat(e.target.value) })}
                  className="w-full"
                />
              </div>

              {/* Max Tokens */}
              <div>
                <label className="text-xs mb-1 block" style={{ color: 'var(--text-tertiary)' }}>Max Tokens</label>
                <input
                  className={inputClass}
                  style={inputStyle}
                  type="number"
                  value={form.maxTokens}
                  onChange={(e) => setForm({ ...form, maxTokens: parseInt(e.target.value) || 4096 })}
                />
              </div>
            </>
          )}

          {/* 通用 Tab */}
          {tab === 'general' && (
            <>
              {/* 连接状态 */}
              <div className="px-3 py-3 rounded-[var(--radius-lg)]" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{
                        background: wsStatus === 'connected' ? 'var(--green)' : wsStatus === 'connecting' ? 'var(--orange)' : 'var(--red)',
                        boxShadow: `0 0 6px ${wsStatus === 'connected' ? 'var(--green)' : 'var(--red)'}`,
                      }}
                    />
                    <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                      WebSocket: {wsStatus === 'connected' ? '已连接' : wsStatus === 'connecting' ? '连接中…' : '未连接'}
                    </span>
                  </div>
                  {wsStatus !== 'connected' && (
                    <button
                      onClick={reconnect}
                      className="text-xs px-3 py-1 rounded-[var(--radius-md)] cursor-pointer transition-all duration-200"
                      style={{ background: 'var(--accent-dim)', color: 'var(--accent)', border: '1px solid var(--border-subtle)' }}
                    >
                      重连
                    </button>
                  )}
                </div>
              </div>

              {/* 服务器地址 */}
              <div>
                <label className="text-xs mb-1 block" style={{ color: 'var(--text-tertiary)' }}>服务器地址</label>
                <input
                  className={inputClass}
                  style={inputStyle}
                  value={form.serverUrl}
                  onChange={(e) => setForm({ ...form, serverUrl: e.target.value })}
                />
              </div>

              {/* 自治模式 */}
              <div className="flex items-center justify-between px-3 py-2 rounded-[var(--radius-lg)]" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
                <div>
                  <div className="text-sm" style={{ color: 'var(--text-primary)' }}>自主执行模式</div>
                  <div className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>允许 AI 自主规划并执行多步骤任务</div>
                </div>
                <button
                  onClick={() => setForm({ ...form, autonomousMode: !form.autonomousMode })}
                  className="w-10 h-5 rounded-full cursor-pointer transition-colors flex items-center"
                  style={{
                    background: form.autonomousMode ? 'var(--accent)' : 'var(--bg-base)',
                    border: '1px solid var(--border-subtle)',
                    justifyContent: form.autonomousMode ? 'flex-end' : 'flex-start',
                    padding: 2,
                  }}
                >
                  <div className="w-4 h-4 rounded-full" style={{ background: 'var(--text-primary)' }} />
                </button>
              </div>

              {form.autonomousMode && (
                <div>
                  <label className="text-xs mb-1 block" style={{ color: 'var(--text-tertiary)' }}>最大自治步数</label>
                  <input
                    className={inputClass}
                    style={inputStyle}
                    type="number"
                    value={form.maxAutonomousSteps}
                    onChange={(e) => setForm({ ...form, maxAutonomousSteps: parseInt(e.target.value) || 25 })}
                  />
                </div>
              )}
            </>
          )}

          {/* 服务 Tab */}
          {tab === 'service' && (
            <>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm" style={{ color: 'var(--text-primary)' }}>服务状态检测</span>
                <button
                  onClick={checkHealth}
                  disabled={loadingHealth}
                  className="text-xs px-3 py-1 rounded-[var(--radius-md)] cursor-pointer transition-all duration-200"
                  style={{ background: 'var(--accent-dim)', color: 'var(--accent)', border: '1px solid var(--border-subtle)' }}
                >
                  {loadingHealth ? '检测中…' : '检测'}
                </button>
              </div>

              {healthStatus && (
                <div className="px-3 py-3 rounded-[var(--radius-lg)] space-y-2" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
                  {Object.entries(healthStatus).map(([key, value]) => (
                    <div key={key} className="flex items-center justify-between text-xs">
                      <span style={{ color: 'var(--text-tertiary)' }}>{key}</span>
                      <span style={{ color: value === 'ok' || value === 'running' ? 'var(--green)' : 'var(--text-primary)' }}>
                        {typeof value === 'string' ? value : JSON.stringify(value)}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              <div className="text-xs px-3 py-2 rounded-[var(--radius-lg)]" style={{ background: 'var(--bg-elevated)', color: 'var(--text-tertiary)', border: '1px solid var(--border-subtle)' }}>
                <div className="mb-1 font-medium" style={{ color: 'var(--text-primary)' }}>后端服务</div>
                <div>地址: {form.serverUrl}</div>
                <div>WebSocket: ws://{new URL(form.serverUrl || 'http://127.0.0.1:8765').hostname}:8765/ws</div>
              </div>
            </>
          )}

          {/* 关于 Tab */}
          {tab === 'about' && (
            <div className="text-center py-8">
              <div className="text-4xl mb-4">🤖</div>
              <h3 className="text-lg font-semibold mb-1" style={{ color: 'var(--accent)' }}>Mac Agent Web</h3>
              <div className="text-sm mb-4" style={{ color: 'var(--text-tertiary)' }}>AI 驱动的 macOS 自动化智能助手</div>
              <div className="text-xs space-y-1" style={{ color: 'var(--text-tertiary)' }}>
                <div>💬 自然语言对话</div>
                <div>🤖 自主任务执行</div>
                <div>🔧 动态工具系统</div>
                <div>📊 实时监控仪表板</div>
                <div>📁 文件管理与下载</div>
                <div>💻 终端命令执行</div>
              </div>
              <div className="text-xs mt-6" style={{ color: 'var(--text-tertiary)', opacity: 0.4 }}>
                版本 3.1 · Web Client
              </div>
            </div>
          )}
        </div>

        {/* 底部按钮 */}
        <div className="flex justify-end gap-3 px-6 py-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded-[var(--radius-md)] text-sm cursor-pointer transition-all duration-200 hover:bg-[var(--bg-hover)]"
            style={{ color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2.5 rounded-[var(--radius-md)] text-sm font-semibold cursor-pointer disabled:opacity-40 transition-all duration-200 hover:shadow-lg active:scale-[0.97]"
            style={{ background: 'var(--gradient-accent)', color: '#fff' }}
          >
            {saving ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SettingsModal;
