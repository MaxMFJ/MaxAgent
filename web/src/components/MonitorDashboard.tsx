import React, { useState } from 'react';
import ExecutionTimeline from './dashboard/ExecutionTimeline';
import NeuralStream from './dashboard/NeuralStream';
import SystemStatus from './dashboard/SystemStatus';
import LogStream from './dashboard/LogStream';
import { Dialog, DialogContent, DialogHeader, DialogTitle, Tabs, TabsList, TabsTrigger, TabsContent } from './ui';

type Tab = 'exec' | 'sys' | 'logs';

interface Props {
  onClose: () => void;
  isMobile?: boolean;
}

const MonitorDashboard: React.FC<Props> = ({ onClose, isMobile }) => {
  const [tab, setTab] = useState<Tab>('exec');

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        showCloseButton
        className={isMobile ? 'w-full h-full max-w-none max-h-none rounded-none' : 'w-[90vw] max-w-[1200px] h-[80vh]'}
      >
        <DialogHeader>
          <DialogTitle className="font-display text-[var(--accent)]">📊 监控仪表板</DialogTitle>
        </DialogHeader>

        <Tabs value={tab} onValueChange={(v: string) => setTab(v as Tab)}>
          <TabsList variant="line" className="w-full justify-start border-0 px-0">
            <TabsTrigger value="exec">⚡ 执行</TabsTrigger>
            <TabsTrigger value="sys">💻 系统</TabsTrigger>
            <TabsTrigger value="logs">📜 日志</TabsTrigger>
          </TabsList>

          <div className="flex-1 overflow-hidden min-h-0">
            <TabsContent value="exec" className="mt-0 h-full">
              <div className={isMobile ? 'flex flex-col h-full overflow-auto' : 'flex h-full'}>
                <div className={isMobile ? '' : 'flex-1'} style={isMobile ? {} : { borderRight: '1px solid var(--border)' }}>
                  <ExecutionTimeline />
                </div>
                <div className={isMobile ? '' : 'w-[400px] flex-shrink-0'} style={isMobile ? { borderTop: '1px solid var(--border)' } : {}}>
                  <NeuralStream />
                </div>
              </div>
            </TabsContent>
            <TabsContent value="sys" className="mt-0 h-full">
              <SystemStatus />
            </TabsContent>
            <TabsContent value="logs" className="mt-0 h-full">
              <LogStream />
            </TabsContent>
          </div>
        </Tabs>

        <div className="flex items-center justify-between px-4 py-1.5 text-xs border-t border-[var(--border)] text-[var(--muted-foreground)] opacity-60">
          <span>Mac Agent Monitor</span>
          <span>{new Date().toLocaleTimeString()}</span>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default MonitorDashboard;
