import { motion } from 'framer-motion'
import { Map, CheckCircle, Circle, AlertTriangle } from 'lucide-react'

const phases = [
  {
    name: 'Phase A',
    status: 'done',
    items: ['文档索引、MACAGENT.md', '首步解析加固', 'v3.1 全接通', '轻量 trace'],
  },
  {
    name: 'Phase B',
    status: 'done',
    items: ['三阶段 prompt', 'MACAGENT.md 注入', '内部 benchmark 文档'],
  },
  {
    name: 'Phase C',
    status: 'planned',
    items: ['可选 CoT/Extended Thinking', 'Subagent 设计', 'Resume/Fork/Checkpoint', '可观测与可评估增强'],
  },
]

const gaps = [
  '可观测：trace 已落盘，待补执行轨迹持久化、token 统计与聚合',
  '可评估：内部 benchmark 用例集已有，待自动化跑分与 CI 集成',
  '安全与运维：沙箱、统一审计、/health/deep 仍为规划/占位',
  '人机协同：HITL、回滚未做',
]

export default function Roadmap() {
  return (
    <div className="py-16 px-6">
      <div className="mx-auto max-w-4xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-16"
        >
          <p className="font-display text-sm tracking-[0.2em] text-[var(--accent)] uppercase mb-2">Roadmap</p>
          <h1 className="font-display text-4xl font-bold mb-4">待扩展</h1>
          <p className="text-lg text-[var(--text-muted)]">
            2026 标杆级 Agent 目标与 Claude Code 级体验进化路线图。v3.2 已实现 Trace、深度健康检查、Benchmark 自动化等。
          </p>
        </motion.div>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mb-16"
        >
          <h2 className="font-display text-2xl font-semibold mb-8 flex items-center gap-2">
            <Map className="size-6 text-[var(--accent)]" />
            阶段里程碑
          </h2>
          <div className="space-y-8">
            {phases.map((phase, i) => (
              <motion.div
                key={phase.name}
                initial={{ opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="card-cyber rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6 transition-all duration-300"
              >
                <div className="flex items-center gap-3 mb-4">
                  {phase.status === 'done' ? (
                    <CheckCircle className="size-5 text-emerald-500" />
                  ) : (
                    <Circle className="size-5 text-[var(--text-muted)]" />
                  )}
                  <h3 className="font-display text-lg font-semibold text-white">{phase.name}</h3>
                  <span className="text-xs text-[var(--text-muted)]">
                    {phase.status === 'done' ? '已完成' : '规划中'}
                  </span>
                </div>
                <ul className="space-y-2 text-sm text-[var(--text-muted)]">
                  {phase.items.map((item) => (
                    <li key={item} className="flex items-center gap-2">
                      <span className="size-1.5 rounded-full bg-[var(--accent)]" />
                      {item}
                    </li>
                  ))}
                </ul>
              </motion.div>
            ))}
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <AlertTriangle className="size-6 text-amber-500" />
            与 2026 标杆的差距
          </h2>
          <ul className="space-y-3">
            {gaps.map((g, i) => (
              <motion.li
                key={i}
                initial={{ opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.05 }}
                className="flex items-start gap-3 text-sm text-[var(--text-muted)] rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-4"
              >
                <span className="size-2 rounded-full bg-amber-500/70 mt-1.5 flex-shrink-0" />
                {g}
              </motion.li>
            ))}
          </ul>
        </motion.section>
      </div>
    </div>
  )
}
