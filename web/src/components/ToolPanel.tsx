import React, { useEffect, useState } from 'react';
import { useToolStore } from '../stores/toolStore';
import { useMonitorStore } from '../stores/monitorStore';
import { getTools } from '../services/api';

type Tab = 'matrix' | 'history' | 'task' | 'logs';

const ToolPanel: React.FC = () => {
  const tools = useToolStore((s) => s.tools);
  const callHistory = useToolStore((s) => s.callHistory);
  const setTools = useToolStore((s) => s.setTools);
  const clearHistory = useToolStore((s) => s.clearHistory);
  const activeTask = useToolStore((s) => s.activeTask);
  const logs = useMonitorStore((s) => s.logs);

  const [tab, setTab] = useState<Tab>('matrix');
  const [expandedTool, setExpandedTool] = useState<string | null>(null);

  useEffect(() => {
    getTools()
      .then((res) => setTools(res.tools as any))
      .catch(() => {});
  }, [setTools]);

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'matrix', label: '矩阵', icon: '⬡' },
    { id: 'history', label: '历史', icon: '📋' },
    { id: 'task', label: '任务', icon: '🎯' },
    { id: 'logs', label: '日志', icon: '📜' },
  ];

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg-surface)' }}>
      {/* 标题 + Tab 切换 */}
      <div className="flex-shrink-0" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <div className="flex items-center justify-between px-4 py-2.5">
          <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            🔧 工具面板
          </span>
          <span className="text-xs px-2 py-0.5 rounded-[var(--radius-full)]" style={{ color: 'var(--text-tertiary)', background: 'var(--bg-elevated)' }}>
            {tools.length} 个工具
          </span>
        </div>
        <div className="flex px-3 pb-2.5 gap-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="flex-1 text-xs py-1.5 rounded-[var(--radius-md)] cursor-pointer transition-all duration-200 font-medium"
              style={{
                background: tab === t.id ? 'var(--accent-dim)' : 'transparent',
                color: tab === t.id ? 'var(--accent)' : 'var(--text-tertiary)',
                border: `1px solid ${tab === t.id ? 'rgba(124,156,255,0.12)' : 'transparent'}`,
              }}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto p-3">
        {/* 矩阵 Tab: 3列网格 */}
        {tab === 'matrix' && (
          <div className="grid grid-cols-3 gap-1.5">
            {tools.length === 0 ? (
              <div className="col-span-3 text-xs text-center py-8" style={{ color: 'var(--text-tertiary)' }}>
                加载中…
              </div>
            ) : (
              tools.map((tool, i) => {
                const isExpanded = expandedTool === tool.name;
                const isSystem = !tool.source || tool.source === 'system';
                return (
                  <div key={i}>
                    <div
                      className="px-2 py-2 rounded-[var(--radius-md)] text-xs cursor-pointer transition-all duration-200 hover:scale-[1.02]"
                      style={{
                        background: isExpanded ? 'var(--accent-dim)' : 'var(--bg-elevated)',
                        border: `1px solid ${isExpanded ? 'color-mix(in srgb, var(--accent) 20%, transparent)' : 'var(--border-subtle)'}`,
                        boxShadow: isExpanded ? 'var(--shadow-glow-accent)' : 'none',
                      }}
                      onClick={() => setExpandedTool(isExpanded ? null : tool.name)}
                    >
                      <div className="font-medium truncate" style={{ color: 'var(--green)', fontSize: '0.7rem' }}>
                        {tool.name}
                      </div>
                      <div className="flex items-center justify-between mt-0.5">
                        <span className="text-xs" style={{
                          color: isSystem ? 'var(--accent)' : 'var(--purple)',
                          fontSize: '0.6rem',
                        }}>
                          {isSystem ? 'SYS' : 'GEN'}
                        </span>
                        <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: 'var(--green)' }} />
                      </div>
                    </div>
                    {/* 展开的详情 */}
                    {isExpanded && (
                      <div
                        className="col-span-3 mt-1 mb-1 px-3 py-2 rounded-[var(--radius-md)] text-xs animate-fade-in-up"
                        style={{ background: 'var(--bg-base)', border: '1px solid var(--border-subtle)' }}
                      >
                        <div style={{ color: 'var(--text-primary)' }}>{tool.description}</div>
                        <div className="mt-1" style={{ color: 'var(--text-tertiary)' }}>
                          参数: {Array.isArray(tool.parameters) ? tool.parameters.length : Object.keys(tool.parameters ?? {}).length} 个
                          {tool.category && ` · ${tool.category}`}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* 历史 Tab */}
        {tab === 'history' && (
          <div>
            {callHistory.length === 0 ? (
              <div className="text-xs text-center py-8" style={{ color: 'var(--text-tertiary)' }}>暂无调用记录</div>
            ) : (
              <>
                <div className="flex justify-end mb-2">
                  <button onClick={clearHistory} className="text-xs cursor-pointer transition-colors hover:opacity-80" style={{ color: 'var(--text-tertiary)' }}>清除</button>
                </div>
                <div className="space-y-1.5">
                  {callHistory.slice().reverse().slice(0, 20).map((call) => (
                    <div
                      key={call.id}
                      className="px-3 py-2.5 rounded-[var(--radius-md)] text-xs transition-all duration-200"
                      style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium" style={{ color: 'var(--green)' }}>{call.toolName}</span>
                        <span style={{
                          color: call.status === 'success' ? 'var(--green)' :
                                 call.status === 'error' ? 'var(--red)' :
                                 call.status === 'running' ? 'var(--orange)' : 'var(--text-tertiary)',
                        }}>
                          {call.status === 'success' ? '✓' : call.status === 'error' ? '✗' : call.status === 'running' ? '⟳' : '…'}
                          {call.endTime && call.startTime ? ` ${((call.endTime - call.startTime) / 1000).toFixed(1)}s` : ''}
                        </span>
                      </div>
                      {call.result && (
                        <div className="mt-1 line-clamp-2" style={{ color: 'var(--text-tertiary)' }}>
                          {call.result.slice(0, 150)}
                        </div>
                      )}
                      {call.startTime && (
                        <div className="mt-0.5" style={{ color: 'var(--text-tertiary)', opacity: 0.5 }}>
                          {new Date(call.startTime).toLocaleTimeString()}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {/* 任务 Tab */}
        {tab === 'task' && (
          <div>
            {!activeTask ? (
              <div className="text-xs text-center py-8" style={{ color: 'var(--text-tertiary)' }}>
                暂无活动任务
                <div className="mt-1" style={{ opacity: 0.5 }}>使用 🤖 按钮发起自主任务</div>
              </div>
            ) : (
              <div className="space-y-3">
                {/* 状态卡 */}
                <div className="px-3 py-3 rounded-[var(--radius-lg)]" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
                  <div className="flex items-center justify-between text-xs mb-2">
                    <span className="font-medium" style={{ color: 'var(--accent)' }}>任务状态</span>
                    <span style={{
                      color: activeTask.status === 'running' ? 'var(--green)' :
                             activeTask.status === 'completed' ? 'var(--accent)' :
                             activeTask.status === 'failed' ? 'var(--red)' : 'var(--text-tertiary)',
                    }}>
                      {activeTask.status === 'running' ? '⟳ 执行中' :
                       activeTask.status === 'completed' ? '✓ 已完成' :
                       activeTask.status === 'failed' ? '✗ 失败' : activeTask.status}
                    </span>
                  </div>
                  <div className="text-xs mb-2" style={{ color: 'var(--text-primary)' }}>
                    {activeTask.description}
                  </div>
                  {/* 进度条 */}
                  <div className="w-full h-1.5 rounded-full overflow-hidden mb-2" style={{ background: 'var(--bg-base)' }}>
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${activeTask.progress}%`,
                        background: activeTask.status === 'failed' ? 'var(--red)' : 'var(--gradient-accent)',
                      }}
                    />
                  </div>
                  {/* 统计 */}
                  <div className="grid grid-cols-3 gap-2">
                    <div className="text-center">
                      <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>总动作</div>
                      <div className="text-sm font-bold" style={{ color: 'var(--accent)' }}>{activeTask.totalActions ?? 0}</div>
                    </div>
                    <div className="text-center">
                      <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>成功</div>
                      <div className="text-sm font-bold" style={{ color: 'var(--green)' }}>{activeTask.successfulActions ?? 0}</div>
                    </div>
                    <div className="text-center">
                      <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>失败</div>
                      <div className="text-sm font-bold" style={{ color: 'var(--red)' }}>{activeTask.failedActions ?? 0}</div>
                    </div>
                  </div>
                  {/* 耗时 */}
                  {activeTask.startTime && (
                    <div className="text-xs mt-2 text-center" style={{ color: 'var(--text-tertiary)' }}>
                      耗时: {((activeTask.endTime ?? Date.now()) - activeTask.startTime) >= 60000
                        ? `${Math.floor(((activeTask.endTime ?? Date.now()) - activeTask.startTime) / 60000)}分${Math.floor((((activeTask.endTime ?? Date.now()) - activeTask.startTime) % 60000) / 1000)}秒`
                        : `${(((activeTask.endTime ?? Date.now()) - activeTask.startTime) / 1000).toFixed(1)}秒`
                      }
                      {activeTask.modelType && ` · 模型: ${activeTask.modelType}`}
                    </div>
                  )}
                  {activeTask.summary && (
                    <div className="mt-2 text-xs px-2 py-1.5 rounded-[var(--radius-sm)]" style={{ background: 'var(--bg-base)', color: 'var(--text-primary)' }}>
                      {activeTask.summary}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 日志 Tab */}
        {tab === 'logs' && (
          <div>
            {logs.length === 0 ? (
              <div className="text-xs text-center py-8" style={{ color: 'var(--text-tertiary)' }}>暂无日志</div>
            ) : (
              <div className="space-y-0.5" style={{ fontFamily: 'var(--font-mono)' }}>
                {logs.slice().reverse().slice(0, 50).map((log, i) => {
                  const lvColor = log.level === 'error' ? 'var(--red)' :
                                  log.level === 'warn' ? 'var(--orange)' :
                                  log.level === 'debug' ? 'var(--purple)' : 'var(--text-tertiary)';
                  return (
                    <div key={i} className="text-xs py-0.5 flex gap-1.5">
                      <span style={{ color: 'var(--text-tertiary)', opacity: 0.5, flexShrink: 0 }}>
                        {new Date(log.timestamp).toLocaleTimeString()}
                      </span>
                      <span style={{ color: lvColor, flexShrink: 0, width: 36 }}>
                        {log.level.toUpperCase()}
                      </span>
                      {log.toolName && (
                        <span style={{ color: 'var(--green)', flexShrink: 0 }}>[{log.toolName}]</span>
                      )}
                      <span style={{ color: 'var(--text-primary)' }}>{log.message}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ToolPanel;
