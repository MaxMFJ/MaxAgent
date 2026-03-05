import { motion } from 'framer-motion'
import { Terminal, Settings, Zap } from 'lucide-react'

const steps = [
  {
    title: '1. 安装 Python 依赖',
    code: 'cd MacAgent/backend\npip install -r requirements.txt',
  },
  {
    title: '2. 配置 LLM',
    desc: '环境变量 DEEPSEEK_API_KEY，或在 Mac 应用设置中选择 Provider（DeepSeek / New API / Ollama / LM Studio）',
  },
  {
    title: '3. 启动后端',
    code: 'cd MacAgent/backend\npython main.py',
  },
  {
    title: '4. 启动 Mac 应用',
    desc: 'Xcode 打开 MacAgentApp，运行。或启动 Web 端：cd web && npm run dev',
  },
]

export default function Help() {
  return (
    <div className="py-16 px-6">
      <div className="mx-auto max-w-4xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-16"
        >
          <h1 className="font-display text-4xl font-bold mb-4">使用帮助</h1>
          <p className="text-lg text-[var(--text-muted)]">
            快速开始、常见问题与配置说明。
          </p>
        </motion.div>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mb-16"
        >
          <h2 className="font-display text-2xl font-semibold mb-8 flex items-center gap-2">
            <Zap className="size-6 text-[var(--accent)]" />
            快速开始
          </h2>
          <div className="space-y-8">
            {steps.map((step, i) => (
              <motion.div
                key={step.title}
                initial={{ opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.05 }}
                className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6"
              >
                <h3 className="font-display text-lg font-semibold mb-3">{step.title}</h3>
                {step.code && (
                  <pre className="rounded-lg bg-[var(--bg)] p-4 text-sm font-mono text-[var(--text-muted)] overflow-x-auto">
                    <code>{step.code}</code>
                  </pre>
                )}
                {step.desc && (
                  <p className="text-sm text-[var(--text-muted)]">{step.desc}</p>
                )}
              </motion.div>
            ))}
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mb-16"
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <Terminal className="size-6 text-[var(--accent)]" />
            服务地址
          </h2>
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6">
            <p className="text-sm text-[var(--text-muted)] mb-2">HTTP API</p>
            <code className="text-[var(--accent)]">http://127.0.0.1:8765</code>
            <p className="text-sm text-[var(--text-muted)] mt-4 mb-2">WebSocket</p>
            <code className="text-[var(--accent)]">ws://127.0.0.1:8765/ws</code>
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <Settings className="size-6 text-[var(--accent)]" />
            系统要求
          </h2>
          <ul className="space-y-2 text-[var(--text-muted)]">
            <li>macOS 14.0+</li>
            <li>Python 3.10+</li>
            <li>Xcode 15.0+（编译 SwiftUI 应用）</li>
          </ul>
        </motion.section>
      </div>
    </div>
  )
}
