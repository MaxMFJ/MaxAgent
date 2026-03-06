import { motion } from 'framer-motion'
import { Server, Database, Cpu, Layers, GitBranch, Zap } from 'lucide-react'

const techStack = [
  { layer: '后端', tech: 'Python 3.10+, FastAPI, uvicorn, websockets', icon: Server },
  { layer: 'LLM', tech: 'OpenAI SDK（兼容 DeepSeek / New API / Ollama / LM Studio），支持 Extended Thinking', icon: Cpu },
  { layer: '向量与记忆', tech: 'sentence-transformers, faiss-cpu, BGE 嵌入，情景记忆（v3.2 重要性加权）', icon: Database },
  { layer: '前端', tech: 'React 19, Vite 7, TypeScript, Tailwind CSS 4, Zustand', icon: Layers },
]

const architecture = [
  'EventBus 解耦：错误收集、自愈建议、升级触发通过事件总线，不侵入主循环',
  '工具自我升级：Planner → Strategy → Executor → Validation → Activation，沙箱执行（resource_dispatcher）',
  '三阶段 Prompt：Gather → Act → Verify，可选 Plan-and-Execute',
  '上下文优化：Token 上限 2000，工具 schema 按查询语义裁剪（最多 8 个），LITE/FULL system prompt 按复杂度切换',
  'Trace 可观测：v3.2 span 级 token 统计、工具调用记录、REST API 查询',
]

export default function Technology() {
  return (
    <div className="py-16 px-6">
      <div className="mx-auto max-w-4xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-16"
        >
          <p className="font-display text-sm tracking-[0.2em] text-[var(--accent)] uppercase mb-2">Architecture</p>
          <h1 className="font-display text-4xl font-bold mb-4">技术架构</h1>
          <p className="text-lg text-[var(--text-muted)]">
            基于 FastAPI + WebSocket 的实时架构，支持多客户端、会话持久化、可扩展工具系统与深度健康检查（/health/deep 8 子系统）。
          </p>
        </motion.div>

        <motion.section
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="mb-16"
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <Zap className="size-6 text-[var(--accent)]" />
            技术栈
          </h2>
          <div className="grid gap-4">
            {techStack.map((item, i) => (
              <motion.div
                key={item.layer}
                initial={{ opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="card-cyber flex items-center gap-4 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-4 transition-all duration-300"
              >
                <item.icon className="size-6 text-[var(--accent)] flex-shrink-0" />
                <div>
                  <span className="font-semibold text-white">{item.layer}</span>
                  <span className="text-[var(--text-muted)] ml-2">— {item.tech}</span>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <GitBranch className="size-6 text-[var(--accent)]" />
            架构设计
          </h2>
          <ul className="space-y-4">
            {architecture.map((item, i) => (
              <motion.li
                key={i}
                initial={{ opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.05 }}
                className="flex items-start gap-3 text-[var(--text-muted)] rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-4"
              >
                <span className="size-2 rounded-full bg-[var(--accent)] mt-1.5 flex-shrink-0" />
                {item}
              </motion.li>
            ))}
          </ul>
        </motion.section>
      </div>
    </div>
  )
}
