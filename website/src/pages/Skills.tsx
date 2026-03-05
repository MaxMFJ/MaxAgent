import { motion } from 'framer-motion'
import { BookOpen, Github, Package } from 'lucide-react'

const skillSources = [
  {
    name: '本地 Capsule',
    desc: 'backend/capsules/ 下的 JSON 文件，热重载',
    examples: ['example_screenshot', 'example_terminal', 'example_multi_step', 'stock_query_capsule'],
  },
  {
    name: 'anthropics/skills',
    desc: 'Anthropic 官方示例',
    examples: ['PDF 处理', '文档分析', '设计辅助'],
  },
  {
    name: 'skillcreatorai/Ai-Agent-Skills',
    desc: '社区技能库',
    examples: ['47+ 技能'],
  },
  {
    name: 'openclaw/skills',
    desc: 'ClawHub 技能库',
    examples: ['5700+ 技能'],
  },
]

const capsuleCapabilities = [
  'list — 列出所有可用技能',
  'find — 按关键词搜索技能',
  'get — 获取技能详情',
  'execute — 执行技能',
  'reload — 热重载技能',
  'sync — 从开放源同步',
  'stats — 统计信息',
]

const exampleSkills = [
  '截取桌面/窗口截图',
  '执行终端命令',
  '多步流程编排',
  '并行步骤执行',
  '重试与回退',
  '股票查询',
]

export default function Skills() {
  return (
    <div className="py-16 px-6">
      <div className="mx-auto max-w-4xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-16"
        >
          <h1 className="font-display text-4xl font-bold mb-4">技能实际能力</h1>
          <p className="text-lg text-[var(--text-muted)]">
            Capsule 技能系统支持本地 + 开放源，可执行、可组合、可热重载。Agent 按需调用。
          </p>
        </motion.div>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mb-12"
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <Github className="size-6 text-[var(--accent)]" />
            技能来源
          </h2>
          <div className="space-y-6">
            {skillSources.map((src, i) => (
              <motion.div
                key={src.name}
                initial={{ opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.05 }}
                className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6"
              >
                <h3 className="font-display text-lg font-semibold mb-2">{src.name}</h3>
                <p className="text-sm text-[var(--text-muted)] mb-4">{src.desc}</p>
                <div className="flex flex-wrap gap-2">
                  {src.examples.map((ex) => (
                    <span
                      key={ex}
                      className="rounded-md bg-[var(--accent)]/10 px-2 py-1 text-xs text-[var(--accent)]"
                    >
                      {ex}
                    </span>
                  ))}
                </div>
              </motion.div>
            ))}
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mb-12"
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <Package className="size-6 text-[var(--accent)]" />
            Capsule 工具能力
          </h2>
          <ul className="space-y-2 font-mono text-sm text-[var(--text-muted)]">
            {capsuleCapabilities.map((c) => (
              <li key={c} className="flex items-center gap-2">
                <span className="text-[var(--accent)]">$</span> {c}
              </li>
            ))}
          </ul>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <BookOpen className="size-6 text-[var(--accent)]" />
            示例技能
          </h2>
          <div className="flex flex-wrap gap-3">
            {exampleSkills.map((s) => (
              <span
                key={s}
                className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm"
              >
                {s}
              </span>
            ))}
          </div>
        </motion.section>
      </div>
    </div>
  )
}
