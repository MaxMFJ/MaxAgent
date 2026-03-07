import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, Sparkles, Cpu, Zap, Shield, Bot, Settings2, Network } from 'lucide-react'
import TerminalAnimation from '../components/TerminalAnimation'
import AnimatedGrid from '../components/AnimatedGrid'

export default function Home() {
  return (
    <div>
      <section className="relative min-h-[90vh] flex items-center justify-center overflow-hidden">
        <AnimatedGrid />
        {/* 赛博朋克背景层 */}
        <div className="absolute inset-0 bg-gradient-to-b from-[var(--accent)]/10 via-transparent to-transparent" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,var(--neon-purple)/20%,transparent_50%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_40%_at_80%_20%,var(--accent)/8%,transparent)]" />
        <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-[var(--bg)] to-transparent" />

        <div className="relative mx-auto max-w-6xl px-6 flex flex-col lg:flex-row items-center justify-center gap-12 lg:gap-16">
        <div className="flex-1 text-center lg:text-left">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <p className="font-display text-sm tracking-[0.3em] text-[var(--accent)] uppercase mb-4">
              macOS Native AI Agent
            </p>
            <h1 className="font-display text-5xl md:text-7xl font-bold tracking-tight text-white neon-text neon-breathe">
              Chow Duck
            </h1>
            <p className="mt-6 text-lg md:text-xl text-[var(--text-muted)] max-w-2xl mx-auto leading-relaxed">
              本地部署的智能体引擎 · ReAct 推理链 · 自主多步执行 · MCP 生态 · 5700+ 技能 Capsule · 工具自进化
            </p>
            <p className="mt-3 text-sm text-[var(--text-muted)]/80 max-w-xl mx-auto">
              不是简单的聊天机器人，而是能理解意图、规划步骤、调用工具、自我修复的 <span className="text-[var(--accent)]">AI Agent</span>
            </p>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="mt-12 flex flex-col sm:flex-row gap-4 justify-center"
          >
            <Link
              to="/features"
              className="btn-neon inline-flex items-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold text-black transition-all duration-300 hover:scale-105"
            >
              探索能力
              <ArrowRight size={16} />
            </Link>
            <Link
              to="/help"
              className="inline-flex items-center gap-2 rounded-lg border-2 border-[var(--accent)]/50 px-6 py-3 text-sm font-medium text-[var(--accent)] transition-all duration-300 hover:border-[var(--accent)] hover:shadow-[0_0_20px_rgba(0,245,255,0.2)]"
            >
              快速部署
            </Link>
          </motion.div>
        </div>
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="w-full max-w-md shrink-0"
        >
          <TerminalAnimation />
        </motion.div>
        </div>
      </section>

      <section className="py-24 px-6">
        <div className="mx-auto max-w-6xl">
          <motion.h2
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            className="font-display text-3xl font-bold text-center mb-4"
          >
            <span className="text-[var(--accent)]">为什么选择</span> Chow Duck
          </motion.h2>
          <motion.p
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            className="text-center text-[var(--text-muted)] mb-16 max-w-2xl mx-auto"
          >
            专为 macOS 打造的 AI Agent 框架，具备完整的推理、执行、监控与自愈能力
          </motion.p>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              {
                icon: Bot,
                title: '双模式执行',
                desc: 'ReAct 流式对话：按需调用工具，实时反馈；Autonomous 自主长任务：多步规划、反思、模型切换、自适应停止',
              },
              {
                icon: Settings2,
                title: '多模型编排',
                desc: 'DeepSeek、OpenAI、Ollama、LM Studio 统一接入；按任务复杂度自动选择本地/云端，支持 Extended Thinking',
              },
              {
                icon: Network,
                title: '技能网络',
                desc: '本地 Capsule + 开放技能源（ClawHub 5700+）；热重载、按需拉取；工具 Self-Upgrade 自动扩展能力',
              },
              {
                icon: Shield,
                title: '自愈与沙箱',
                desc: '诊断引擎、修复计划、沙箱执行；危险命令拦截；EventBus 解耦，错误不中断主循环',
              },
            ].map((item, i) => (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="card-cyber card-float rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6 transition-all duration-300"
              >
                <item.icon className="size-10 text-[var(--accent)] mb-4 drop-shadow-[0_0_10px_rgba(0,245,255,0.4)]" />
                <h3 className="font-display text-lg font-semibold mb-2 text-white">{item.title}</h3>
                <p className="text-sm text-[var(--text-muted)] leading-relaxed">{item.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <section className="py-24 px-6">
        <div className="mx-auto max-w-6xl">
          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-8 md:p-12 relative overflow-hidden"
          >
            <div className="absolute top-0 right-0 w-64 h-64 bg-[var(--accent)]/5 rounded-full blur-3xl" />
            <div className="relative">
              <h2 className="font-display text-2xl font-bold mb-2 flex items-center gap-2">
                <Sparkles className="size-6 text-[var(--accent)]" />
                立即开始
              </h2>
              <p className="text-[var(--text-muted)] mb-6 max-w-2xl">
                安装 Python 依赖、配置 LLM API、启动后端与 Mac 应用，数分钟内即可让 Agent 运行在你的 Mac 上。
                支持内置后端打包，用户零配置即可使用。
              </p>
              <div className="flex flex-wrap gap-4">
                <Link
                  to="/help"
                  className="inline-flex items-center gap-2 text-[var(--accent)] hover:underline font-medium"
                >
                  查看部署指南
                  <ArrowRight size={16} />
                </Link>
                <Link
                  to="/docs"
                  className="inline-flex items-center gap-2 text-[var(--text-muted)] hover:text-[var(--text)]"
                >
                  完整文档
                </Link>
              </div>
            </div>
          </motion.div>
        </div>
      </section>
    </div>
  )
}
