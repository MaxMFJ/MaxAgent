import React, { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { X, Plus, Download, Trash2, RefreshCw, Egg, Bird, Cpu } from 'lucide-react';
import { IconButton, Badge, StatusDot } from './ui';
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

  const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: 'ducks', label: 'Duck 列表', icon: <Bird size={14} /> },
    { id: 'chow', label: 'Chow Duck', icon: <span className="text-sm">🦆</span> },
    { id: 'eggs', label: 'Eggs', icon: <Egg size={14} /> },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={onClose}>
      <motion.div
        className={`overflow-hidden flex flex-col ${isMobile ? 'w-full h-full' : 'rounded-2xl'}`}
        style={{
          background: 'var(--bg-surface)',
          border: isMobile ? 'none' : '1px solid var(--border)',
          width: isMobile ? '100%' : 720,
          maxHeight: isMobile ? '100%' : '85vh',
          boxShadow: '0 24px 48px rgba(0,0,0,0.3)',
        }}
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 flex-shrink-0" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          <div className="flex items-center gap-3">
            <span className="text-xl">🦆</span>
            <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>Chow Duck 分身管理</h2>
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
            <IconButton variant="ghost" size="sm" onClick={onClose} title="关闭"><X size={14} /></IconButton>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex px-5 pt-3 gap-1 flex-shrink-0" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-lg transition-colors"
              style={{
                color: tab === t.id ? 'var(--accent)' : 'var(--text-secondary)',
                background: tab === t.id ? 'var(--bg-recessed)' : 'transparent',
                borderBottom: tab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
              }}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>

        {/* Error bar */}
        {error && (
          <div className="mx-5 mt-3 px-3 py-2 rounded-lg text-xs flex items-center justify-between" style={{ background: 'rgba(239,68,68,0.1)', color: '#ef4444' }}>
            {error}
            <button onClick={clearError} className="ml-2 underline">关闭</button>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5" style={{ minHeight: 0 }}>
          {loading && <div className="text-center py-8 text-xs" style={{ color: 'var(--text-tertiary)' }}>加载中...</div>}

          {/* ===== Duck 列表 Tab ===== */}
          {tab === 'ducks' && !loading && (
            <div className="space-y-3">
              {ducks.length === 0 ? (
                <div className="text-center py-12" style={{ color: 'var(--text-tertiary)' }}>
                  <span className="text-4xl block mb-3">🦆</span>
                  <p className="text-sm">还没有 Duck 分身</p>
                  <p className="text-xs mt-1">前往 Chow Duck 标签创建一个</p>
                </div>
              ) : (
                ducks.map((duck: DuckInfo) => (
                  <div
                    key={duck.duck_id}
                    className="flex items-center gap-3 p-3 rounded-xl"
                    style={{ background: 'var(--bg-recessed)', border: '1px solid var(--border-subtle)' }}
                  >
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
                        <button
                          onClick={() => startLocalDuck(duck.duck_id)}
                          className="px-2 py-1 rounded-lg text-xs font-medium"
                          style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
                        >
                          启动
                        </button>
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
                  </div>
                ))
              )}
            </div>
          )}

          {/* ===== Chow Duck Tab ===== */}
          {tab === 'chow' && !loading && (
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
                        border: `1px solid ${selectedTemplate === t.duck_type ? 'var(--accent)' : 'var(--border-subtle)'}`,
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

              {/* Egg 名称 */}
              <div>
                <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--text-secondary)' }}>Egg 名称（可选）</label>
                <input
                  type="text"
                  value={eggName}
                  onChange={(e) => setEggName(e.target.value)}
                  placeholder="留空使用默认名称"
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                  style={{
                    background: 'var(--bg-recessed)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)',
                  }}
                />
              </div>

              {/* 操作按钮 */}
              <div className="flex gap-3">
                <button
                  onClick={handleChowDuck}
                  disabled={isChowing}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all"
                  style={{
                    background: isChowing ? 'var(--bg-recessed)' : 'var(--gradient-accent)',
                    color: isChowing ? 'var(--text-tertiary)' : '#fff',
                    cursor: isChowing ? 'not-allowed' : 'pointer',
                  }}
                >
                  <Egg size={15} />
                  {(isChowing && chowMode === 'egg') ? '正在吃鸭子...' : '🦆 Chow Duck → 生成 Egg'}
                </button>
                <button
                  onClick={handleChowLocalDuck}
                  disabled={isChowing}
                  className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-medium transition-all"
                  style={{
                    background: 'var(--bg-recessed)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)',
                    cursor: isChowing ? 'not-allowed' : 'pointer',
                  }}
                >
                  <Plus size={14} />
                  {isChowing && chowMode === 'local' ? '正在吃鸭子...' : '本地 Duck'}
                </button>
              </div>
            </div>
          )}

          {/* ===== Eggs Tab ===== */}
          {tab === 'eggs' && !loading && (
            <div className="space-y-3">
              {eggs.length === 0 ? (
                <div className="text-center py-12" style={{ color: 'var(--text-tertiary)' }}>
                  <span className="text-4xl block mb-3">🥚</span>
                  <p className="text-sm">还没有 Egg</p>
                  <p className="text-xs mt-1">前往 Chow Duck 标签生成一个</p>
                </div>
              ) : (
                eggs.map((egg: EggRecord) => (
                  <div
                    key={egg.egg_id}
                    className="flex items-center gap-3 p-3 rounded-xl"
                    style={{ background: 'var(--bg-recessed)', border: '1px solid var(--border-subtle)' }}
                  >
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
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Footer stats */}
        {stats && (
          <div className="flex items-center justify-between px-5 py-3 text-[11px] flex-shrink-0" style={{ color: 'var(--text-quaternary)', borderTop: '1px solid var(--border-subtle)' }}>
            <span>总计 {stats.total} 个 Duck · {stats.total_completed} 任务完成</span>
            <span>{Object.entries(stats.by_type).map(([k, v]) => `${k}: ${v}`).join(' · ')}</span>
          </div>
        )}
      </motion.div>

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
    </div>
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
    <div className="fixed inset-0 z-[60] flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={onClose}>
      <div
        className="rounded-xl p-4 w-[360px]"
        style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>分身 LLM 配置</h3>
          <button onClick={onClose} className="text-xs" style={{ color: 'var(--text-secondary)' }}>关闭</button>
        </div>
        <p className="text-xs mb-4" style={{ color: 'var(--text-tertiary)' }}>
          为 {duck.name} 配置独立 LLM，使分身更有效运用大模型完成专项任务。
        </p>
        <div className="space-y-3">
          <div>
            <label className="text-[11px] font-medium block mb-1" style={{ color: 'var(--text-secondary)' }}>API Key</label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-xxx"
              className="w-full px-3 py-2 rounded-lg text-xs"
              style={{ background: 'var(--bg-recessed)', border: '1px solid var(--border-subtle)' }}
            />
          </div>
          <div>
            <label className="text-[11px] font-medium block mb-1" style={{ color: 'var(--text-secondary)' }}>Base URL</label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.example.com/v1"
              className="w-full px-3 py-2 rounded-lg text-xs"
              style={{ background: 'var(--bg-recessed)', border: '1px solid var(--border-subtle)' }}
            />
          </div>
          <div>
            <label className="text-[11px] font-medium block mb-1" style={{ color: 'var(--text-secondary)' }}>模型名称</label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="gpt-4o / deepseek-chat"
              className="w-full px-3 py-2 rounded-lg text-xs"
              style={{ background: 'var(--bg-recessed)', border: '1px solid var(--border-subtle)' }}
            />
          </div>
        </div>
        <div className="flex justify-end mt-4">
          <button
            onClick={async () => {
              setSaving(true);
              await onSave(apiKey, baseUrl, model);
              setSaving(false);
            }}
            disabled={saving}
            className="px-3 py-1.5 rounded-lg text-xs font-medium"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            {saving ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default DuckManagement;
