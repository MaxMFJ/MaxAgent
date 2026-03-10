import React, { useCallback, useRef, useEffect, useState, lazy, Suspense } from 'react';
import Sidebar from './Sidebar';
import ChatView from './ChatView';
import Toolbar from './Toolbar';
import ErrorBanner from './ErrorBanner';
import { useSettingsStore } from '../stores/settingsStore';
import { useWSStore } from '../stores/wsStore';
import { useChatStore } from '../stores/chatStore';
import { useResponsive } from '../hooks/useResponsive';

const ToolPanel = lazy(() => import('./ToolPanel'));
const NotificationPanel = lazy(() => import('./NotificationPanel'));
const SettingsModal = lazy(() => import('./SettingsModal'));
const MonitorDashboard = lazy(() => import('./MonitorDashboard'));
const DuckManagement = lazy(() => import('./DuckManagement'));

const Layout: React.FC = () => {
  const sidebarWidth = useSettingsStore((s) => s.sidebarWidth);
  const setSidebarWidth = useSettingsStore((s) => s.setSidebarWidth);
  const showRightPanel = useSettingsStore((s) => s.showRightPanel);
  const rightPanelWidth = useSettingsStore((s) => s.rightPanelWidth);
  const connect = useWSStore((s) => s.connect);
  const wsStatus = useWSStore((s) => s.status);

  const mobileSidebarOpen = useSettingsStore((s) => s.mobileSidebarOpen);
  const setMobileSidebarOpen = useSettingsStore((s) => s.setMobileSidebarOpen);
  const mobilePanelOpen = useSettingsStore((s) => s.mobilePanelOpen);
  const mobilePanelTab = useSettingsStore((s) => s.mobilePanelTab);
  const setMobilePanelOpen = useSettingsStore((s) => s.setMobilePanelOpen);

  const { isMobile, isTablet } = useResponsive();

  const [rightTab, setRightTab] = useState<'tools' | 'notifications'>('tools');
  const [showSettings, setShowSettings] = useState(false);
  const [showMonitor, setShowMonitor] = useState(false);
  const [showDuck, setShowDuck] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dragging = useRef<'sidebar' | 'right' | null>(null);

  useEffect(() => { connect(); }, [connect]);

  // 全局键盘快捷键
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key === 'n') {
        e.preventDefault();
        useChatStore.getState().createConversation();
      } else if (meta && e.key === ',') {
        e.preventDefault();
        setShowSettings((v) => !v);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // 连接失败提示
  useEffect(() => {
    if (wsStatus === 'disconnected') {
      setError('未连接到后端服务，请确保 backend 正在运行');
    } else {
      setError(null);
    }
  }, [wsStatus]);

  // 窗口变大时自动关闭移动端抽屉
  useEffect(() => {
    if (!isMobile) {
      setMobileSidebarOpen(false);
      setMobilePanelOpen(false);
    }
  }, [isMobile, setMobileSidebarOpen, setMobilePanelOpen]);

  const onSidebarDragStart = useCallback(() => { dragging.current = 'sidebar'; }, []);
  const onRightDragStart = useCallback(() => { dragging.current = 'right'; }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      if (dragging.current === 'sidebar') {
        const w = Math.max(180, Math.min(e.clientX, 500));
        setSidebarWidth(w);
      } else if (dragging.current === 'right') {
        const w = Math.max(250, Math.min(window.innerWidth - e.clientX, 500));
        useSettingsStore.getState().setRightPanelWidth(w);
      }
    };
    const onUp = () => { dragging.current = null; };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [setSidebarWidth]);

  // 同步移动端面板 tab 到桌面 tab
  const handleRightTabChange = useCallback((tab: 'tools' | 'notifications') => {
    setRightTab(tab);
    if (isMobile) {
      setMobilePanelOpen(true, tab);
    }
  }, [isMobile, setMobilePanelOpen]);

  // ---- 移动端布局 ----
  if (isMobile) {
    return (
      <div className="app-shell app-shell-mobile" style={{ background: 'var(--bg-base)' }}>
        <Toolbar
          rightTab={mobilePanelTab}
          onRightTabChange={handleRightTabChange}
          onOpenSettings={() => setShowSettings(true)}
          onOpenMonitor={() => setShowMonitor(true)}
          onOpenDuck={() => setShowDuck(true)}
          isMobile
        />
        {error && <ErrorBanner message={error} type="warning" onDismiss={() => setError(null)} />}

        {/* 聊天区域：可收缩 + 内部滚动 */}
        <div className="app-main app-main-mobile">
          <ChatView />
        </div>

        {/* 移动端侧边栏抽屉（从左滑入） */}
        {mobileSidebarOpen && (
          <div className="fixed inset-0 z-40 flex">
            {/* 背景遮罩 */}
            <div
              className="absolute inset-0 mobile-overlay-bg"
              onClick={() => setMobileSidebarOpen(false)}
            />
            {/* 侧边栏容器 */}
            <div
              className="relative z-10 h-full mobile-drawer-left"
              style={{ width: '80vw', maxWidth: 320 }}
            >
              <Sidebar onClose={() => setMobileSidebarOpen(false)} />
            </div>
          </div>
        )}

        {/* 移动端右侧面板抽屉（从右滑入） */}
        {mobilePanelOpen && (
          <div className="fixed inset-0 z-40 flex justify-end">
            {/* 背景遮罩 */}
            <div
              className="absolute inset-0 mobile-overlay-bg"
              onClick={() => setMobilePanelOpen(false)}
            />
            {/* 面板容器 */}
            <div
              className="relative z-10 h-full mobile-drawer-right"
              style={{ width: '85vw', maxWidth: 400 }}
            >
              <Suspense fallback={<div className="p-4 text-xs" style={{ color: 'var(--text-tertiary)' }}>加载中…</div>}>
                {mobilePanelTab === 'tools' ? <ToolPanel /> : <NotificationPanel />}
              </Suspense>
            </div>
          </div>
        )}

        {/* Modals */}
        <Suspense fallback={null}>
          {showSettings && <SettingsModal onClose={() => setShowSettings(false)} isMobile />}
          {showMonitor && <MonitorDashboard onClose={() => setShowMonitor(false)} isMobile />}
          {showDuck && <DuckManagement onClose={() => setShowDuck(false)} isMobile />}
        </Suspense>
      </div>
    );
  }

  // ---- 平板端布局（隐藏右侧面板改为叠加） ----
  const effectiveSidebarWidth = isTablet ? Math.min(sidebarWidth, 220) : sidebarWidth;
  const effectiveRightWidth = isTablet ? Math.min(rightPanelWidth, 280) : rightPanelWidth;

  // ---- 桌面端布局：三栏可收缩，避免截断 ----
  return (
    <div className="app-shell app-shell-desktop" style={{ background: 'var(--bg-base)' }}>
      <Toolbar
        rightTab={rightTab}
        onRightTabChange={handleRightTabChange}
        onOpenSettings={() => setShowSettings(true)}
        onOpenMonitor={() => setShowMonitor(true)}
        onOpenDuck={() => setShowDuck(true)}
      />
      {error && <ErrorBanner message={error} type="warning" onDismiss={() => setError(null)} />}
      <div className="app-main app-main-desktop">
        <div className="app-sidebar" style={{ width: effectiveSidebarWidth, minWidth: 180 }}>
          <Sidebar />
        </div>
        <div className="resizer" onMouseDown={onSidebarDragStart} />
        <div className="app-content">
          <ChatView />
        </div>
        {showRightPanel && (
          <>
            <div className="resizer" onMouseDown={onRightDragStart} />
            <div className="app-right-panel" style={{ width: effectiveRightWidth, minWidth: 250 }}>
              <Suspense fallback={<div className="p-4 text-xs" style={{ color: 'var(--text-tertiary)' }}>加载中…</div>}>
                {rightTab === 'tools' ? <ToolPanel /> : <NotificationPanel />}
              </Suspense>
            </div>
          </>
        )}
      </div>
      {/* Modals */}
      <Suspense fallback={null}>
        {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
        {showMonitor && <MonitorDashboard onClose={() => setShowMonitor(false)} />}
        {showDuck && <DuckManagement onClose={() => setShowDuck(false)} />}
      </Suspense>
    </div>
  );
};

export default Layout;
