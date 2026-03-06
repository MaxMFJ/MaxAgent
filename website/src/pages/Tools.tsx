import { motion } from 'framer-motion'
import { Wrench, Zap, Cpu, Box } from 'lucide-react'

const coreTools = [
  { name: 'file_operations', desc: '文件读写、搜索、目录遍历' },
  { name: 'terminal', desc: '终端命令执行，支持 cwd 与输出记录' },
  { name: 'app_control', desc: '应用启动、切换、AppleScript 控制' },
  { name: 'system_info', desc: '系统信息、磁盘、内存' },
  { name: 'clipboard', desc: '剪贴板读写' },
  { name: 'script / multi_script', desc: '脚本执行、多步编排' },
  { name: 'screenshot', desc: '全屏/窗口截图' },
  { name: 'browser', desc: '浏览器控制、页面操作' },
  { name: 'mail', desc: '邮件发送、读取' },
  { name: 'calendar', desc: '日历事件' },
  { name: 'notification', desc: '系统通知' },
]

const extendedTools = [
  { name: 'docker', desc: 'Docker 容器管理' },
  { name: 'network', desc: '网络诊断、ping、curl' },
  { name: 'database', desc: '数据库查询（SQL）' },
  { name: 'developer', desc: '开发工具、代码分析' },
  { name: 'web_search', desc: 'DuckDuckGo / 维基百科搜索' },
  { name: 'vision', desc: '视觉理解、图像分析' },
  { name: 'input_control', desc: '鼠标键盘模拟（CGEvent、cliclick）' },
]

const agentTools = [
  { name: 'request_tool_upgrade', desc: '请求工具升级（Self-Upgrade 流程）' },
  { name: 'evomap', desc: 'EvoMap 技能网络（可选）' },
  { name: 'capsule', desc: '技能 Capsule：list / find / get / execute / reload / sync' },
]

const generatedTools = [
  { name: 'tunnel_monitor', desc: '隧道状态监控' },
  { name: 'tunnel_manager', desc: '隧道启停管理' },
  { name: 'interactive_mail', desc: '交互式邮件撰写' },
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
          <p className="font-display text-sm tracking-[0.2em] text-[var(--accent)] uppercase mb-2">Tool Registry</p>
          <h1 className="font-display text-4xl font-bold mb-4">工具落地</h1>
          <p className="text-lg text-[var(--text-muted)]">
            30+ 内置工具覆盖文件、终端、应用、网络、开发等场景。支持动态生成与 Self-Upgrade 自我升级，Agent 按需调用。
          </p>
        </motion.div>

        <div className="space-y-10">
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6"
          >
            <h2 className="font-display text-xl font-semibold mb-4 flex items-center gap-2">
              <Wrench className="size-5 text-[var(--accent)]" />
              基础工具
            </h2>
            <ul className="grid sm:grid-cols-2 gap-3">
              {coreTools.map((t) => (
                <li key={t.name} className="flex gap-2 text-sm">
                  <code className="text-[var(--accent)] font-mono shrink-0">{t.name}</code>
                  <span className="text-[var(--text-muted)]">— {t.desc}</span>
                </li>
              ))}
            </ul>
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6"
          >
            <h2 className="font-display text-xl font-semibold mb-4">扩展工具</h2>
            <ul className="grid sm:grid-cols-2 gap-3">
              {extendedTools.map((t) => (
                <li key={t.name} className="flex gap-2 text-sm">
                  <code className="text-[var(--accent)] font-mono shrink-0">{t.name}</code>
                  <span className="text-[var(--text-muted)]">— {t.desc}</span>
                </li>
              ))}
            </ul>
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6"
          >
            <h2 className="font-display text-xl font-semibold mb-4 flex items-center gap-2">
              <Cpu className="size-5 text-[var(--accent)]" />
              Agent 能力
            </h2>
            <ul className="space-y-3">
              {agentTools.map((t) => (
                <li key={t.name} className="flex gap-2 text-sm">
                  <code className="text-[var(--accent)] font-mono shrink-0">{t.name}</code>
                  <span className="text-[var(--text-muted)]">— {t.desc}</span>
                </li>
              ))}
            </ul>
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6"
          >
            <h2 className="font-display text-xl font-semibold mb-4 flex items-center gap-2">
              <Box className="size-5 text-[var(--accent)]" />
              动态生成工具
            </h2>
            <p className="text-sm text-[var(--text-muted)] mb-4">
              Self-Upgrade 产出 + 手写，运行时动态加载，无需重启后端
            </p>
            <ul className="space-y-2">
              {generatedTools.map((t) => (
                <li key={t.name} className="flex gap-2 text-sm">
                  <code className="text-[var(--accent)] font-mono">{t.name}</code>
                  <span className="text-[var(--text-muted)]">— {t.desc}</span>
                </li>
              ))}
            </ul>
          </motion.section>
        </div>
      </div>
    </div>
  )
}
