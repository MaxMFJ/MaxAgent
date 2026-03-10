import React from 'react';
import { useChatStore } from '../stores/chatStore';
import { Card } from './ui';
import {
  FolderOpen,
  Terminal,
  Rocket,
  Cpu,
  Clipboard,
  Bot,
  ArrowRight,
  Zap,
  Sparkles,
} from 'lucide-react';

const features = [
  { icon: <FolderOpen size={20} />, title: '文件管理', desc: '查看、整理和操作文件系统', color: 'var(--accent)', gradient: 'var(--gradient-warm)' },
  { icon: <Terminal size={20} />, title: '终端命令', desc: '执行 Shell 命令与管理进程', color: 'var(--green)', gradient: 'linear-gradient(135deg, rgba(74,222,128,0.15), rgba(74,222,128,0.05))' },
  { icon: <Rocket size={20} />, title: '应用控制', desc: '启动、关闭和操控应用程序', color: 'var(--purple)', gradient: 'linear-gradient(135deg, rgba(177,151,252,0.15), rgba(177,151,252,0.05))' },
  { icon: <Cpu size={20} />, title: '系统信息', desc: '查询 CPU、内存和磁盘状态', color: 'var(--orange)', gradient: 'linear-gradient(135deg, rgba(251,191,36,0.15), rgba(251,191,36,0.05))' },
  { icon: <Clipboard size={20} />, title: '剪贴板', desc: '读写剪贴板，跨应用传递', color: 'var(--teal)', gradient: 'linear-gradient(135deg, rgba(94,234,212,0.15), rgba(94,234,212,0.05))' },
  { icon: <Bot size={20} />, title: '自治模式', desc: '下达目标，Agent 自主执行', color: 'var(--green)', gradient: 'linear-gradient(135deg, rgba(74,222,128,0.15), rgba(74,222,128,0.05))' },
];

const quickPrompts = [
  { text: '帮我查看当前系统资源占用', emoji: '📊' },
  { text: '列出桌面上的所有文件', emoji: '📁' },
  { text: '打开 Safari 并搜索最新新闻', emoji: '🌐' },
  { text: '帮我清理 ~/Downloads 中的临时文件', emoji: '🧹' },
];

const WelcomeView: React.FC = () => {
  const createConversation = useChatStore((s) => s.createConversation);
  const setActive = useChatStore((s) => s.setActiveConversation);

  const handleQuickPrompt = (prompt: string) => {
    const id = createConversation();
    setActive(id);
    useChatStore.getState().addMessage(id, {
      id: crypto.randomUUID(),
      role: 'user',
      content: prompt,
      timestamp: Date.now(),
      isStreaming: false,
    });
  };

  return (
    <div className="welcome-view-fill select-none px-6">
      {/* Ambient Background */}
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[400px] pointer-events-none"
        style={{
          background: 'var(--gradient-hero)',
          filter: 'blur(100px)',
          opacity: 0.6,
        }}
      />

      {/* Hero */}
      <div className="flex flex-col items-center mt-8 mb-12 relative z-10 animate-fade-in-up">
        {/* Logo with organic glow */}
        <div className="relative mb-6">
          <div
            className="absolute inset-0 rounded-[var(--radius-2xl)]"
            style={{
              background: 'var(--gradient-accent)',
              filter: 'blur(24px)',
              opacity: 0.25,
              animation: 'ambientGlow 4s ease-in-out infinite',
            }}
          />
          <div
            className="relative w-[72px] h-[72px] rounded-[var(--radius-2xl)] flex items-center justify-center"
            style={{
              background: 'var(--gradient-accent)',
              boxShadow: 'var(--shadow-glow-accent)',
            }}
          >
            <Zap size={30} style={{ color: '#fff' }} />
          </div>
        </div>
        <h1
          className="font-display text-3xl sm:text-4xl font-bold tracking-wider mb-3"
          style={{ color: 'var(--accent)' }}
        >
          Mac Agent
        </h1>
        <p className="text-[15px] max-w-lg text-center leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
          AI 驱动的 macOS 自动化智能助手<br />
          <span style={{ color: 'var(--text-tertiary)' }}>通过自然语言对话，轻松完成系统操作</span>
        </p>
      </div>

      {/* Feature Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 max-w-2xl w-full mb-12 relative z-10">
        {features.map((f, i) => (
          <Card key={f.title} hover padding="md" className={`text-center group animate-fade-in-up stagger-${i + 1}`}>
            <div
              className="w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center mx-auto mb-3 transition-all duration-300 group-hover:scale-110 group-hover:shadow-lg"
              style={{ background: f.gradient, color: f.color }}
            >
              {f.icon}
            </div>
            <div className="text-[13px] font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>{f.title}</div>
            <div className="text-xs leading-relaxed" style={{ color: 'var(--text-tertiary)' }}>{f.desc}</div>
          </Card>
        ))}
      </div>

      {/* Quick Prompts */}
      <div className="max-w-2xl w-full mb-12 relative z-10 animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
        <div className="flex items-center gap-2 mb-4">
          <Sparkles size={14} style={{ color: 'var(--accent)' }} />
          <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
            快速开始
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {quickPrompts.map((p) => (
            <Card
              key={p.text}
              hover
              padding="md"
              className="group flex items-center gap-3 text-left text-sm cursor-pointer"
              onClick={() => handleQuickPrompt(p.text)}
            >
              <span className="text-base flex-shrink-0">{p.emoji}</span>
              <span className="flex-1 group-hover:text-[var(--text-primary)] transition-colors">{p.text}</span>
              <ArrowRight size={14} className="flex-shrink-0 opacity-0 group-hover:opacity-60 transition-all duration-200 -translate-x-1 group-hover:translate-x-0" style={{ color: 'var(--accent)' }} />
            </Card>
          ))}
        </div>
      </div>

      {/* Keyboard Shortcuts */}
      <div
        className="text-xs flex items-center gap-5 mb-8 relative z-10 animate-fade-in-up"
        style={{ color: 'var(--text-tertiary)', animationDelay: '0.4s' }}
      >
        <span className="flex items-center gap-1.5">
          <kbd className="px-2 py-1 rounded-[var(--radius-sm)] text-[10px] font-mono font-medium" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>⌘N</kbd>
          新建会话
        </span>
        <span className="flex items-center gap-1.5">
          <kbd className="px-2 py-1 rounded-[var(--radius-sm)] text-[10px] font-mono font-medium" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>⌘,</kbd>
          设置
        </span>
        <span className="flex items-center gap-1.5">
          <kbd className="px-2 py-1 rounded-[var(--radius-sm)] text-[10px] font-mono font-medium" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>⌘⇧↵</kbd>
          自治任务
        </span>
      </div>
    </div>
  );
};

export default WelcomeView;
