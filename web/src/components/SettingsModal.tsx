import React, { useState, useEffect } from 'react';
import { useSettingsStore } from '../stores/settingsStore';
import { useWSStore } from '../stores/wsStore';
import { getConfig, updateConfig as apiUpdateConfig, getHealth } from '../services/api';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Input,
  Label,
  Button,
  Card,
} from './ui';

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
      await apiUpdateConfig({
        provider: form.provider,
        model: form.model,
        api_key: form.apiKey,
        base_url: form.baseUrl,
      });
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

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        showCloseButton
        className={isMobile ? 'w-full h-full max-w-none max-h-none rounded-none' : 'w-[580px] max-h-[82vh]'}
      >
        <DialogHeader>
          <DialogTitle className="font-display text-[var(--accent)]">设置</DialogTitle>
        </DialogHeader>

        <Tabs value={tab} onValueChange={(v: string) => setTab(v as SettingsTab)}>
          <TabsList variant="line" className="w-full justify-start border-0 px-0">
            <TabsTrigger value="model">🧠 模型</TabsTrigger>
            <TabsTrigger value="general">⚙️ 通用</TabsTrigger>
            <TabsTrigger value="service">🖥️ 服务</TabsTrigger>
            <TabsTrigger value="about">ℹ️ 关于</TabsTrigger>
          </TabsList>

          <div className="flex-1 overflow-y-auto px-0 py-4 space-y-4 max-h-[50vh]">
            <TabsContent value="model" className="mt-0 space-y-4">
              <div className="space-y-2">
                <Label>AI 提供商</Label>
                <div className={isMobile ? 'grid grid-cols-3 gap-1.5' : 'grid grid-cols-4 gap-1.5'}>
                  {PROVIDERS.map(p => (
                    <Button
                      key={p.id}
                      variant={form.provider === p.id ? 'primary' : 'outline'}
                      size="sm"
                      className="text-xs"
                      onClick={() => handleProviderChange(p.id)}
                    >
                      {p.label}
                    </Button>
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <Label>Base URL</Label>
                <Input value={form.baseUrl ?? ''} onChange={(e) => setForm({ ...form, baseUrl: e.target.value })} placeholder="API 基础地址" />
              </div>
              <div className="space-y-2">
                <Label>模型名称</Label>
                <Input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} placeholder="例如 deepseek-chat, gpt-4" />
              </div>
              <div className="space-y-2">
                <Label>API Key</Label>
                <Input type="password" value={form.apiKey ?? ''} onChange={(e) => setForm({ ...form, apiKey: e.target.value })} placeholder="API 密钥" />
              </div>
              <div className="space-y-2">
                <Label>Temperature: {form.temperature}</Label>
                <input
                  type="range" min="0" max="2" step="0.1"
                  value={form.temperature}
                  onChange={(e) => setForm({ ...form, temperature: parseFloat(e.target.value) })}
                  className="w-full"
                />
              </div>
              <div className="space-y-2">
                <Label>Max Tokens</Label>
                <Input type="number" value={form.maxTokens} onChange={(e) => setForm({ ...form, maxTokens: parseInt(e.target.value) || 4096 })} />
              </div>
            </TabsContent>

            <TabsContent value="general" className="mt-0 space-y-4">
              <Card padding="md">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: wsStatus === 'connected' ? 'var(--green)' : wsStatus === 'connecting' ? 'var(--orange)' : 'var(--red)' }} />
                    <span className="text-sm">WebSocket: {wsStatus === 'connected' ? '已连接' : wsStatus === 'connecting' ? '连接中…' : '未连接'}</span>
                  </div>
                  {wsStatus !== 'connected' && <Button variant="outline" size="sm" onClick={reconnect}>重连</Button>}
                </div>
              </Card>
              <div className="space-y-2">
                <Label>服务器地址</Label>
                <Input value={form.serverUrl} onChange={(e) => setForm({ ...form, serverUrl: e.target.value })} />
              </div>
              <Card padding="md">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium">自主执行模式</div>
                    <div className="text-xs text-[var(--muted-foreground)]">允许 AI 自主规划并执行多步骤任务</div>
                  </div>
                  <button
                    onClick={() => setForm({ ...form, autonomousMode: !form.autonomousMode })}
                    className="w-10 h-5 rounded-full flex items-center p-0.5 transition-colors border border-[var(--border)]"
                    style={{ background: form.autonomousMode ? 'var(--accent)' : 'var(--bg-base)', justifyContent: form.autonomousMode ? 'flex-end' : 'flex-start' }}
                  >
                    <div className="w-4 h-4 rounded-full bg-[var(--text-primary)]" />
                  </button>
                </div>
              </Card>
              {form.autonomousMode && (
                <div className="space-y-2">
                  <Label>最大自治步数</Label>
                  <Input type="number" value={form.maxAutonomousSteps} onChange={(e) => setForm({ ...form, maxAutonomousSteps: parseInt(e.target.value) || 25 })} />
                </div>
              )}
            </TabsContent>

            <TabsContent value="service" className="mt-0 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">服务状态检测</span>
                <Button variant="outline" size="sm" onClick={checkHealth} disabled={loadingHealth}>{loadingHealth ? '检测中…' : '检测'}</Button>
              </div>
              {healthStatus && (
                <Card padding="md" className="space-y-2">
                  {Object.entries(healthStatus).map(([key, value]) => (
                    <div key={key} className="flex justify-between text-xs">
                      <span className="text-[var(--muted-foreground)]">{key}</span>
                      <span style={{ color: value === 'ok' || value === 'running' ? 'var(--green)' : undefined }}>{typeof value === 'string' ? value : JSON.stringify(value)}</span>
                    </div>
                  ))}
                </Card>
              )}
              <Card padding="md" className="text-xs text-[var(--muted-foreground)]">
                <div className="font-medium text-[var(--foreground)] mb-1">后端服务</div>
                <div>地址: {form.serverUrl}</div>
                <div>WebSocket: ws://{new URL(form.serverUrl || 'http://127.0.0.1:8765').hostname}:8765/ws</div>
              </Card>
            </TabsContent>

            <TabsContent value="about" className="mt-0">
              <div className="text-center py-8">
                <div className="text-4xl mb-4">🤖</div>
                <h3 className="font-display text-lg font-semibold text-[var(--accent)] mb-1">Mac Agent Web</h3>
                <div className="text-sm text-[var(--muted-foreground)] mb-4">AI 驱动的 macOS 自动化智能助手</div>
                <div className="text-xs space-y-1 text-[var(--muted-foreground)]">
                  <div>💬 自然语言对话</div>
                  <div>🤖 自主任务执行</div>
                  <div>🔧 动态工具系统</div>
                  <div>📊 实时监控仪表板</div>
                  <div>📁 文件管理与下载</div>
                  <div>💻 终端命令执行</div>
                </div>
                <div className="text-xs mt-6 text-[var(--muted-foreground)] opacity-60">版本 3.1 · Web Client</div>
              </div>
            </TabsContent>
          </div>
        </Tabs>

        <DialogFooter className="border-t border-[var(--border)] pt-4">
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={handleSave} disabled={saving}>{saving ? '保存中…' : '保存'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default SettingsModal;
