import React, { useEffect, useState } from 'react';
import { useToolStore } from '../stores/toolStore';
import { useMonitorStore } from '../stores/monitorStore';
import { getTools } from '../services/api';
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui';
import { Card, Button, Badge } from './ui';

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

  return (
    <div className="panel-fill" style={{ background: 'var(--bg-surface)' }}>
      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
        {/* 标题 + Tab 切换 */}
        <div className="flex-shrink-0" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="flex items-center justify-between px-4 py-2.5">
            <span className="font-display text-sm font-semibold tracking-wider" style={{ color: 'var(--accent)' }}>
              🔧 工具面板
            </span>
            <Badge variant="default">{tools.length} 个工具</Badge>
          </div>
          <TabsList variant="line" className="w-full justify-start border-0 px-3 pb-2.5 gap-1">
            <TabsTrigger value="matrix">⬡ 矩阵</TabsTrigger>
            <TabsTrigger value="history">📋 历史</TabsTrigger>
            <TabsTrigger value="task">🎯 任务</TabsTrigger>
            <TabsTrigger value="logs">📜 日志</TabsTrigger>
          </TabsList>
        </div>

      {/* 内容区 */}
      <div className="panel-scroll p-3">
        {/* 矩阵 Tab */}
        <TabsContent value="matrix" className="mt-0">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1.5 min-w-0">
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
                    <Card
                      padding="sm"
                      hover
                      className={`text-xs cursor-pointer transition-all duration-200 hover:scale-[1.02] ${isExpanded ? 'border-[var(--accent)] bg-[var(--accent-dim)] shadow-[var(--shadow-glow-accent)]' : ''}`}
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
                    </Card>
                    {isExpanded && (
                      <Card padding="sm" className="mt-1 mb-1 text-xs animate-fade-in-up min-w-0 break-words bg-[var(--bg-base)]">
                        <div style={{ color: 'var(--text-primary)' }} className="break-words">{tool.description}</div>
                        <div className="mt-1" style={{ color: 'var(--text-tertiary)' }}>
                          参数: {Array.isArray(tool.parameters) ? tool.parameters.length : Object.keys(tool.parameters ?? {}).length} 个
                          {tool.category && ` · ${tool.category}`}
                        </div>
                      </Card>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </TabsContent>

        {/* 历史 Tab */}
        <TabsContent value="history" className="mt-0">
          {callHistory.length === 0 ? (
            <div className="text-xs text-center py-8" style={{ color: 'var(--text-tertiary)' }}>暂无调用记录</div>
          ) : (
            <>
              <div className="flex justify-end mb-2">
                <Button variant="ghost" size="sm" onClick={clearHistory}>清除</Button>
              </div>
              <div className="space-y-1.5">
                {callHistory.slice().reverse().slice(0, 20).map((call) => (
                  <Card key={call.id} padding="sm" className="text-xs transition-all duration-200 bg-[var(--bg-elevated)]">
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
                  </Card>
                ))}
              </div>
            </>
          )}
        </TabsContent>

        {/* 任务 Tab */}
        <TabsContent value="task" className="mt-0">
          {!activeTask ? (
            <div className="text-xs text-center py-8" style={{ color: 'var(--text-tertiary)' }}>
              暂无活动任务
              <div className="mt-1" style={{ opacity: 0.5 }}>使用 🤖 按钮发起自主任务</div>
            </div>
          ) : (
            <div className="space-y-3">
              <Card padding="md" className="bg-[var(--bg-elevated)]">
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
              </Card>
            </div>
          )}
        </TabsContent>

        {/* 日志 Tab */}
        <TabsContent value="logs" className="mt-0">
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
        </TabsContent>
      </div>
      </Tabs>
    </div>
  );
};

export default ToolPanel;
