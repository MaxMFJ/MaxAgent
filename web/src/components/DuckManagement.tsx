import React, { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Plus, Download, Trash2, RefreshCw, Egg, Bird, Cpu } from 'lucide-react';
import { IconButton, Badge, StatusDot, Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, Tabs, TabsList, TabsTrigger, TabsContent, Card, Button, Input, Label } from './ui';
import ChowDuckAnimation from './ChowDuckAnimation';
import { useDuckStore } from '../stores/duckStore';
import type { DuckTemplate, DuckInfo, EggRecord } from '../stores/duckStore';
import { getEggDownloadUrl } from '../services/api';

type TabId = 'ducks' | 'chow' | 'eggs';

interface Props {
  onClose: () => void;
  isMobile?: boolean;
}

const DuckManagement: React.FC<Props> = ({ onClose, isMobile }) => {
  const [tab, setTab] = useState<TabId>('ducks');
  const {
    ducks, templates, eggs, stats, loading, error,
    fetchAll, createLocalDuck, destroyLocalDuck, startLocalDuck, updateDuckLLMConfig, removeDuck,
    createEgg, deleteEgg, clearError,
  } = useDuckStore();

  const [llmConfigDuck, setLlmConfigDuck] = useState<DuckInfo | null>(null);

  // ─── Chow Duck state ─────────────────────────────
  const [selectedTemplate, setSelectedTemplate] = useState<string>('general');
  const [eggName, setEggName] = useState('');
  const [isChowing, setIsChowing] = useState(false);
  const [chowMode, setChowMode] = useState<'egg' | 'local'>('egg');
  const [chowResult, setChowResult] = useState<EggRecord | null>(null);
  const [localDuckCreated, setLocalDuckCreated] = useState(false);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleChowDuck = useCallback(() => {
    setIsChowing(true);
    setChowResult(null);
    setLocalDuckCreated(false);
    setChowMode('egg');
  }, []);

  const handleChowLocalDuck = useCallback(() => {
    setIsChowing(true);
    setChowResult(null);
    setLocalDuckCreated(false);
    setChowMode('local');
  }, []);

  const handleAnimationComplete = useCallback(async () => {
    try {
      if (chowMode === 'egg') {
        const egg = await createEgg(selectedTemplate, eggName || undefined);
        setChowResult(egg);
      } else {
        const t = templates.find(tpl => tpl.duck_type === selectedTemplate) || templates[0];
        if (t) {
          await createLocalDuck(t.name, t.duck_type, t.skills);
          setLocalDuckCreated(true);
        }
      }
    } catch {
      // error handled in store
    }
    setIsChowing(false);
  }, [chowMode, createEgg, createLocalDuck, selectedTemplate, eggName, templates]);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        showCloseButton
        className={isMobile ? 'w-full h-full max-w-none max-h-none rounded-none' : 'w-[720px] max-h-[85vh]'}
      >
        <DialogHeader>
          <div className="flex items-center gap-3">
            <span className="text-xl">🦆</span>
            <DialogTitle className="font-display text-[var(--accent)]">Chow Duck 分身管理</DialogTitle>
            {stats && (
              <div className="flex items-center gap-2 ml-2">
                <Badge variant="success">{stats.online} 在线</Badge>
                <Badge variant="warning">{stats.busy} 忙碌</Badge>
                <Badge variant="default">{stats.offline} 离线</Badge>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <IconButton variant="ghost" size="sm" onClick={() => fetchAll()} title="刷新"><RefreshCw size={14} /></IconButton>
          </div>
        </DialogHeader>

        <Tabs value={tab} onValueChange={(v: string) => setTab(v as TabId)}>
          <TabsList variant="line" className="w-full justify-start border-0 px-0">
            <TabsTrigger value="ducks"><Bird size={14} className="inline mr-1" />Duck 列表</TabsTrigger>
            <TabsTrigger value="chow"><span className="mr-1">🦆</span>Chow Duck</TabsTrigger>
            <TabsTrigger value="eggs"><Egg size={14} className="inline mr-1" />Eggs</TabsTrigger>
          </TabsList>

        {error && (
          <Card padding="sm" className="mx-0 mt-3 bg-[rgba(239,68,68,0.1)] border-red-500/30">
            <div className="flex items-center justify-between text-xs text-red-400">
              {error}
              <Button variant="ghost" size="sm" onClick={clearError}>关闭</Button>
            </div>
          </Card>
        )}

        <div className="flex-1 overflow-y-auto p-5 min-h-0">
          {loading && <div className="text-center py-8 text-xs text-[var(--muted-foreground)]">加载中...</div>}

          <TabsContent value="ducks" className="mt-0">
          {!loading && (
            <div className="space-y-3">
              {ducks.length === 0 ? (
                <div className="text-center py-12" style={{ color: 'var(--text-tertiary)' }}>
                  <span className="text-4xl block mb-3">🦆</span>
                  <p className="text-sm">还没有 Duck 分身</p>
                  <p className="text-xs mt-1">前往 Chow Duck 标签创建一个</p>
                </div>
              ) : (
                ducks.map((duck: DuckInfo) => (
                  <Card key={duck.duck_id} padding="md" className="flex items-center gap-3">
                    <StatusDot status={duck.status === 'online' ? 'online' : duck.status === 'busy' ? 'connecting' : 'offline'} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{duck.name}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}>{duck.duck_type}</span>
                        {duck.is_local && <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(59,130,246,0.15)', color: '#3b82f6' }}>本地</span>}
                      </div>
                      <div className="text-[11px] mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                        {duck.hostname} · 完成 {duck.completed_tasks} · 失败 {duck.failed_tasks}
                        {duck.current_task_id && <span className="ml-2" style={{ color: 'var(--color-warning, #f59e0b)' }}>执行中: {duck.current_task_id}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      {duck.is_local && (
                        <IconButton
                          variant="ghost"
                          size="sm"
                          onClick={() => setLlmConfigDuck(duck)}
                          title="LLM 配置"
                        >
                          <Cpu size={13} />
                        </IconButton>
                      )}
                      {duck.is_local && duck.status === 'offline' && (
                        <Button variant="outline" size="sm" onClick={() => startLocalDuck(duck.duck_id)}>启动</Button>
                      )}
                      <IconButton
                        variant="ghost"
                        size="sm"
                        onClick={() => duck.is_local ? destroyLocalDuck(duck.duck_id) : removeDuck(duck.duck_id)}
                        title="删除"
                      >
                        <Trash2 size={13} />
                      </IconButton>
                    </div>
                  </Card>
                ))
              )}
            </div>
          )}
          </TabsContent>

          <TabsContent value="chow" className="mt-0">
          {!loading && (
            <div className="space-y-5">
              {/* 动画区域（强制至少 3s 吃鸭子，给后端创建配置争取时间） */}
              <ChowDuckAnimation
                isActive={isChowing}
                duckType={selectedTemplate}
                mode={chowMode}
                onComplete={handleAnimationComplete}
              />

              {/* Egg 结果 */}
              {chowResult && (
                <motion.div
                  className="p-4 rounded-xl"
                  style={{ background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)' }}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xl">🥚</span>
                    <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Egg 生成成功！</span>
                  </div>
                  <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    ID: {chowResult.egg_id} · 类型: {chowResult.duck_type}
                  </div>
                  <a
                    href={getEggDownloadUrl(chowResult.egg_id)}
                    className="inline-flex items-center gap-1.5 mt-2 px-3 py-1.5 rounded-lg text-xs font-medium"
                    style={{ background: 'var(--accent)', color: '#fff' }}
                  >
                    <Download size={12} /> 下载 Egg
                  </a>
                </motion.div>
              )}

              {/* 本地 Duck 结果 */}
              {localDuckCreated && (
                <motion.div
                  className="p-4 rounded-xl"
                  style={{ background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)' }}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xl">🦆</span>
                    <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>本地 Duck 已创建！</span>
                  </div>
                  <div className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>已加入分身列表，可前往 Duck 列表查看</div>
                </motion.div>
              )}

              {/* 模板选择 */}
              <div>
                <label className="text-xs font-medium block mb-2" style={{ color: 'var(--text-secondary)' }}>选择鸭子类型</label>
                <div className="grid grid-cols-2 gap-2">
                  {templates.map((t: DuckTemplate) => (
                    <button
                      key={t.duck_type}
                      onClick={() => setSelectedTemplate(t.duck_type)}
                      className="flex items-start gap-2 p-3 rounded-xl text-left transition-all"
                      style={{
                        background: selectedTemplate === t.duck_type ? 'var(--accent-dim)' : 'var(--bg-recessed)',
                        border: `1px solid ${selectedTemplate === t.duck_type ? 'var(--accent)' : 'var(--border)'}`,
                      }}
                    >
                      <span className="text-lg flex-shrink-0">{t.icon}</span>
                      <div className="min-w-0">
                        <div className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>{t.name}</div>
                        <div className="text-[10px] mt-0.5 line-clamp-2" style={{ color: 'var(--text-tertiary)' }}>{t.description}</div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <Label>Egg 名称（可选）</Label>
                <Input value={eggName} onChange={(e) => setEggName(e.target.value)} placeholder="留空使用默认名称" />
              </div>

              <div className="flex gap-3">
                <Button variant="primary" className="flex-1" onClick={handleChowDuck} disabled={isChowing} icon={<Egg size={15} />}>
                  {(isChowing && chowMode === 'egg') ? '正在吃鸭子...' : '🦆 Chow Duck → 生成 Egg'}
                </Button>
                <Button variant="outline" onClick={handleChowLocalDuck} disabled={isChowing} icon={<Plus size={14} />}>
                  {isChowing && chowMode === 'local' ? '正在吃鸭子...' : '本地 Duck'}
                </Button>
              </div>
            </div>
          )}
          </TabsContent>

          <TabsContent value="eggs" className="mt-0">
          {!loading && (
            <div className="space-y-3">
              {eggs.length === 0 ? (
                <div className="text-center py-12" style={{ color: 'var(--text-tertiary)' }}>
                  <span className="text-4xl block mb-3">🥚</span>
                  <p className="text-sm">还没有 Egg</p>
                  <p className="text-xs mt-1">前往 Chow Duck 标签生成一个</p>
                </div>
              ) : (
                eggs.map((egg: EggRecord) => (
                  <Card key={egg.egg_id} padding="md" className="flex items-center gap-3">
                    <span className="text-xl flex-shrink-0">🥚</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{egg.name}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}>{egg.duck_type}</span>
                        {egg.connected && <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(34,197,94,0.15)', color: '#22c55e' }}>已连接</span>}
                        {egg.downloaded && !egg.connected && <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(59,130,246,0.15)', color: '#3b82f6' }}>已下载</span>}
                      </div>
                      <div className="text-[11px] mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                        {egg.egg_id} · {new Date(egg.created_at * 1000).toLocaleString()}
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <a
                        href={getEggDownloadUrl(egg.egg_id)}
                        className="p-1.5 rounded-lg transition-colors hover:opacity-80"
                        style={{ color: 'var(--accent)' }}
                        title="下载"
                      >
                        <Download size={14} />
                      </a>
                      <IconButton variant="ghost" size="sm" onClick={() => deleteEgg(egg.egg_id)} title="删除">
                        <Trash2 size={13} />
                      </IconButton>
                    </div>
                  </Card>
                ))
              )}
            </div>
          )}
          </TabsContent>
        </div>
        </Tabs>

        {stats && (
          <div className="flex items-center justify-between px-5 py-3 text-[11px] border-t border-[var(--border)] text-[var(--muted-foreground)]">
            <span>总计 {stats.total} 个 Duck · {stats.total_completed} 任务完成</span>
            <span>{Object.entries(stats.by_type).map(([k, v]) => `${k}: ${v}`).join(' · ')}</span>
          </div>
        )}
      </DialogContent>

      {/* LLM 配置弹窗 */}
      {llmConfigDuck && (
        <DuckLLMConfigModal
          duck={llmConfigDuck}
          onSave={async (apiKey, baseUrl, model) => {
            await updateDuckLLMConfig(llmConfigDuck.duck_id, apiKey, baseUrl, model);
            setLlmConfigDuck(null);
          }}
          onClose={() => setLlmConfigDuck(null)}
        />
      )}
    </Dialog>
  );
};

function DuckLLMConfigModal({ duck, onSave, onClose }: {
  duck: DuckInfo;
  onSave: (apiKey: string, baseUrl: string, model: string) => Promise<void>;
  onClose: () => void;
}) {
  const [apiKey, setApiKey] = useState(duck.llm_api_key ?? '');
  const [baseUrl, setBaseUrl] = useState(duck.llm_base_url ?? '');
  const [model, setModel] = useState(duck.llm_model ?? '');
  const [saving, setSaving] = useState(false);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent showCloseButton className="w-[360px]">
        <DialogHeader>
          <DialogTitle>分身 LLM 配置</DialogTitle>
        </DialogHeader>
        <p className="text-xs mb-4 text-[var(--muted-foreground)]">为 {duck.name} 配置独立 LLM，使分身更有效运用大模型完成专项任务。</p>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label>API Key</Label>
            <Input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-xxx" />
          </div>
          <div className="space-y-2">
            <Label>Base URL</Label>
            <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.example.com/v1" />
          </div>
          <div className="space-y-2">
            <Label>模型名称</Label>
            <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-4o / deepseek-chat" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="primary" onClick={async () => { setSaving(true); await onSave(apiKey, baseUrl, model); setSaving(false); }} disabled={saving}>
            {saving ? '保存中…' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default DuckManagement;
