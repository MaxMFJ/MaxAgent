import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, Sparkles, Cpu, Zap, Shield } from 'lucide-react'

export default function Home() {
  return (
    <div>
      <section className="relative min-h-[90vh] flex items-center justify-center overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-[var(--accent)]/5 via-transparent to-transparent" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,var(--accent)/15%,transparent)]" />
        <div className="relative mx-auto max-w-4xl px-6 text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <h1 className="font-display text-5xl md:text-7xl font-bold tracking-tight text-white">
              Chow Duck
            </h1>
            <p className="mt-4 text-xl md:text-2xl text-[var(--text-muted)] max-w-2xl mx-auto">
              macOS 本地 AI 智能助手 · 流式对话 · 自主长任务 · 技能扩展
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
              className="inline-flex items-center gap-2 rounded-lg bg-[var(--accent)] px-6 py-3 text-sm font-medium text-black transition hover:bg-[var(--accent)]/90"
            >
              探索功能
              <ArrowRight size={16} />
            </Link>
            <Link
              to="/help"
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] px-6 py-3 text-sm font-medium transition hover:bg-[var(--bg-card)]"
            >
              快速开始
            </Link>
          </motion.div>
        </div>
      </section>

      <section className="py-24 px-6">
        <div className="mx-auto max-w-6xl">
          <motion.h2
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            className="font-display text-3xl font-bold text-center mb-16"
          >
            为什么选择 Chow Duck
          </motion.h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
            {[
              {
                icon: Sparkles,
                title: '双模式执行',
                desc: '支持 ReAct 流式对话与 Autonomous 自主长任务，按需切换',
              },
              {
                icon: Cpu,
                title: '多模型支持',
                desc: 'DeepSeek、New API、Ollama、LM Studio，本地与云端灵活切换',
              },
              {
                icon: Zap,
                title: '技能 Capsule',
                desc: '本地 + 开放技能源（5700+），热重载，工具自升级',
              },
              {
                icon: Shield,
                title: '自愈与沙箱',
                desc: '诊断引擎、修复计划、沙箱执行、危险动作拦截',
              },
            ].map((item, i) => (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 hover:border-[var(--accent)]/30 transition-colors"
              >
                <item.icon className="size-10 text-[var(--accent)] mb-4" />
                <h3 className="font-display text-lg font-semibold mb-2">{item.title}</h3>
                <p className="text-sm text-[var(--text-muted)]">{item.desc}</p>
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
            className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-8 md:p-12"
          >
            <h2 className="font-display text-2xl font-bold mb-6">立即开始</h2>
            <p className="text-[var(--text-muted)] mb-6 max-w-2xl">
              安装 Python 依赖、配置 LLM、启动后端与 Mac 应用，即可开始使用。
            </p>
            <div className="flex flex-wrap gap-4">
              <Link
                to="/help"
                className="inline-flex items-center gap-2 text-[var(--accent)] hover:underline"
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
          </motion.div>
        </div>
      </section>
    </div>
  )
}
