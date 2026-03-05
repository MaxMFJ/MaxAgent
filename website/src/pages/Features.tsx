import { motion } from 'framer-motion'
import { MessageSquare, Brain, Mic, BarChart3, Settings, Cloud } from 'lucide-react'
import { Link } from 'react-router-dom'

const features = [
  {
    icon: MessageSquare,
    title: '流式对话 (ReAct)',
    desc: '按需调用工具，支持断线重连与输出恢复。文件、终端、应用、截图、邮件等工具实时响应。',
  },
  {
    icon: Brain,
    title: '自主任务 (Autonomous)',
    desc: '长 horizon 多步执行，可选反思、模型选择（本地/云端）、自适应停止（任务完成/无进展/循环检测）。',
  },
  {
    icon: Mic,
    title: '语音与 TTS',
    desc: '实时语音识别（中/英）、静音自动提交、流式按句朗读、支持中英文，可随时停止。',
  },
  {
    icon: BarChart3,
    title: '监控仪表板',
    desc: '执行时间线、系统状态、历史分析、实时日志流、Token/RPM/TPM 统计、模型分布。',
  },
  {
    icon: Settings,
    title: '权限管理',
    desc: '辅助功能、屏幕录制、自动化、cliclick、Quartz、osascript 状态检测与引导。',
  },
  {
    icon: Cloud,
    title: 'Cloudflare Tunnel',
    desc: '隧道自动启停、局域网信息、自动启动配置，支持远程访问 Web 端。',
  },
]

export default function Features() {
  return (
    <div className="py-16 px-6">
      <div className="mx-auto max-w-4xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-16"
        >
          <h1 className="font-display text-4xl font-bold mb-4">功能特性</h1>
          <p className="text-lg text-[var(--text-muted)]">
            Chow Duck 提供完整的对话、执行、监控与扩展能力。支持 Mac 客户端与 Web 端多端同步。
          </p>
        </motion.div>

        <div className="space-y-12">
          {features.map((item, i) => (
            <motion.div
              key={item.title}
              initial={{ opacity: 0, x: -20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.05 }}
              className="flex gap-6 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 hover:border-[var(--accent)]/20 transition-colors"
            >
              <div className="flex-shrink-0 rounded-xl bg-[var(--accent)]/10 p-4">
                <item.icon className="size-8 text-[var(--accent)]" />
              </div>
              <div>
                <h2 className="font-display text-xl font-semibold mb-2">{item.title}</h2>
                <p className="text-[var(--text-muted)]">{item.desc}</p>
              </div>
            </motion.div>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="mt-16 text-center"
        >
          <p className="text-[var(--text-muted)] mb-4">了解更多技术实现</p>
          <Link
            to="/technology"
            className="inline-flex items-center gap-2 text-[var(--accent)] hover:underline"
          >
            技术架构
          </Link>
        </motion.div>
      </div>
    </div>
  )
}
