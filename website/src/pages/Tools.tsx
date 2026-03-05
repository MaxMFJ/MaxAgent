import { motion } from 'framer-motion'
import { Wrench, Zap } from 'lucide-react'

const coreTools = [
  'file_operations — 文件操作',
  'terminal — 终端命令',
  'app_control — 应用控制',
  'system_info — 系统信息',
  'clipboard — 剪贴板',
  'script / multi_script — 脚本执行',
  'screenshot — 截图',
  'browser — 浏览器',
  'mail — 邮件',
  'calendar — 日历',
  'notification — 通知',
]

const extendedTools = [
  'docker — Docker 管理',
  'network — 网络诊断',
  'database — 数据库查询',
  'developer — 开发工具',
  'web_search — DuckDuckGo 搜索',
  'wikipedia — 维基百科',
  'vision — 视觉理解',
  'input_control — 鼠标键盘模拟',
]

const agentTools = [
  'request_tool_upgrade — 请求工具升级（Self-Upgrade）',
  'evomap — EvoMap 技能网络（可选）',
  'capsule — 技能 Capsule（list/find/get/execute/reload/sync）',
]

const generatedTools = [
  'tunnel_monitor — 隧道监控',
  'tunnel_manager — 隧道管理',
  'interactive_mail — 交互式邮件',
]

export default function Tools() {
  return (
    <div className="py-16 px-6">
      <div className="mx-auto max-w-4xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-16"
        >
          <h1 className="font-display text-4xl font-bold mb-4">工具落地</h1>
          <p className="text-lg text-[var(--text-muted)]">
            30+ 内置工具覆盖文件、终端、应用、网络、开发等场景。支持动态生成与自我升级。
          </p>
        </motion.div>

        <div className="space-y-12">
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6"
          >
            <h2 className="font-display text-xl font-semibold mb-4 flex items-center gap-2">
              <Wrench className="size-5 text-[var(--accent)]" />
              基础工具
            </h2>
            <ul className="grid sm:grid-cols-2 gap-2 text-sm text-[var(--text-muted)]">
              {coreTools.map((t) => (
                <li key={t} className="font-mono">{t}</li>
              ))}
            </ul>
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6"
          >
            <h2 className="font-display text-xl font-semibold mb-4">扩展工具</h2>
            <ul className="grid sm:grid-cols-2 gap-2 text-sm text-[var(--text-muted)]">
              {extendedTools.map((t) => (
                <li key={t} className="font-mono">{t}</li>
              ))}
            </ul>
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6"
          >
            <h2 className="font-display text-xl font-semibold mb-4 flex items-center gap-2">
              <Zap className="size-5 text-[var(--accent)]" />
              Agent 能力
            </h2>
            <ul className="space-y-2 text-sm text-[var(--text-muted)]">
              {agentTools.map((t) => (
                <li key={t} className="font-mono">{t}</li>
              ))}
            </ul>
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6"
          >
            <h2 className="font-display text-xl font-semibold mb-4">动态生成工具</h2>
            <p className="text-sm text-[var(--text-muted)] mb-4">
              Self-Upgrade 产出 + 手写，运行时动态加载
            </p>
            <ul className="space-y-2 text-sm text-[var(--text-muted)] font-mono">
              {generatedTools.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </motion.section>
        </div>
      </div>
    </div>
  )
}
