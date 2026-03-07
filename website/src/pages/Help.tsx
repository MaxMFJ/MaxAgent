import { motion } from 'framer-motion'
import { Settings, Zap, Server, Cpu, Shield, Package, Key, AlertCircle, Network } from 'lucide-react'

const steps = [
  {
    title: '1. 安装 Python 依赖',
    code: 'cd MacAgent/backend\npip install -r requirements.txt',
  },
  {
    title: '2. 配置 LLM',
    desc: '方式一：环境变量 export DEEPSEEK_API_KEY="your-api-key"。方式二：在 Mac 应用设置中选择 Provider（DeepSeek / New API / Ollama / LM Studio）并填写 API Key、Base URL、模型名。',
  },
  {
    title: '3. 启动后端',
    code: 'cd MacAgent/backend\npython main.py',
  },
  {
    title: '4. 启动 Mac 应用',
    desc: 'Xcode 打开 MacAgentApp.xcworkspace（使用 CocoaPods 时务必用 workspace），运行。工具栏可控制后端/Ollama 启停，打开监控仪表板、工具面板、系统消息。或启动 Web 端：cd website && npm run dev。',
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
          <p className="font-display text-sm tracking-[0.2em] text-[var(--accent)] uppercase mb-2">Quick Start</p>
          <h1 className="font-display text-4xl font-bold mb-4">使用帮助</h1>
          <p className="text-lg text-[var(--text-muted)]">
            快速开始、常见问题与配置说明。后端支持内置到 Mac App 打包，用户无需单独部署。
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
                className="card-cyber rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6 transition-all duration-300"
              >
                <h3 className="font-display text-lg font-semibold mb-3 text-white">{step.title}</h3>
                {step.code && (
                  <pre className="rounded-lg bg-[var(--bg)] border border-[var(--border)] p-4 text-sm font-mono text-[var(--accent)] overflow-x-auto">
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
            <Server className="size-6 text-[var(--accent)]" />
            服务地址
          </h2>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6">
            <p className="text-sm text-[var(--text-muted)] mb-2">HTTP API</p>
            <code className="text-[var(--accent)] font-mono">http://127.0.0.1:8765</code>
            <p className="text-sm text-[var(--text-muted)] mt-4 mb-2">WebSocket</p>
            <code className="text-[var(--accent)] font-mono">ws://127.0.0.1:8765/ws</code>
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mb-16"
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <Settings className="size-6 text-[var(--accent)]" />
            系统要求
          </h2>
          <ul className="space-y-2 text-[var(--text-muted)]">
            <li>macOS 14.0+</li>
            <li>Python 3.10+</li>
            <li>Node.js 18+（MCP 服务器需要，自动发现 Homebrew keg-only 安装如 node@22）</li>
            <li>Xcode 15.0+（编译 SwiftUI 应用）</li>
          </ul>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mb-16"
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <Cpu className="size-6 text-[var(--accent)]" />
            Ollama / LM Studio 本地模型
          </h2>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6 space-y-3 text-sm text-[var(--text-muted)]">
            <p>1. 安装 <a href="https://ollama.ai/" target="_blank" rel="noopener noreferrer" className="text-[var(--accent)] hover:underline">Ollama</a> 或 LM Studio，并拉取模型（如 <code className="text-[var(--accent)]">ollama pull qwen2.5-coder:7b</code>）</p>
            <p>2. 在应用设置中选择「Ollama」或「LM Studio」，配置对应地址与模型名</p>
            <p>3. 自主任务可勾选「自动选模型」，由后端按任务复杂度选择本地/云端</p>
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mb-16"
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <Network className="size-6 text-[var(--accent)]" />
            MCP 服务器管理
          </h2>
          <p className="text-sm text-[var(--text-muted)] mb-4">Mac App 内置 6 个 MCP 服务一键连接：GitHub、Brave Search、Sequential Thinking、Puppeteer、Filesystem、Memory。支持自定义添加。</p>
          <pre className="rounded-lg bg-[var(--bg)] border border-[var(--border)] p-4 text-sm font-mono text-[var(--accent)] overflow-x-auto">
{`# 添加 MCP 服务器
curl -X POST http://127.0.0.1:8765/mcp/servers \\
  -H 'Content-Type: application/json' \\
  -d '{"name": "memory", "transport": "stdio", "command": ["npx", "-y", "@modelcontextprotocol/server-memory"]}'

# 查看已连接
curl http://127.0.0.1:8765/mcp/servers`}
          </pre>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mb-16"
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <Shield className="size-6 text-[var(--accent)]" />
            权限管理
          </h2>
          <p className="text-sm text-[var(--text-muted)] mb-4">权限配置在 <strong>设置 → 权限</strong> 中完成。快捷入口：工具栏齿轮 → 设置 → 权限。</p>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="text-left p-3 text-[var(--accent)]">权限</th>
                  <th className="text-left p-3 text-[var(--accent)]">用途</th>
                </tr>
              </thead>
              <tbody className="text-[var(--text-muted)]">
                <tr className="border-b border-[var(--border)]"><td className="p-3">App 辅助功能</td><td className="p-3">MacAgentApp 自身控制键鼠</td></tr>
                <tr className="border-b border-[var(--border)]"><td className="p-3">Python 辅助功能</td><td className="p-3">后端模拟键鼠（Agent 核心）</td></tr>
                <tr className="border-b border-[var(--border)]"><td className="p-3">屏幕录制</td><td className="p-3">截图、视觉感知</td></tr>
                <tr><td className="p-3">自动化 (System Events)</td><td className="p-3">AppleScript 控制其他应用</td></tr>
              </tbody>
            </table>
          </div>
          <p className="text-xs text-[var(--text-muted)] mt-3">Python 路径在 .app 包内时，使用 ⌘⇧G 在「前往文件夹」中粘贴完整路径。cliclick 未安装时执行 <code className="text-[var(--accent)]">brew install cliclick</code>。</p>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mb-16"
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <Key className="size-6 text-[var(--accent)]" />
            打包与后台内置
          </h2>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6 space-y-3 text-sm text-[var(--text-muted)]">
            <p><strong className="text-white">后台已内置到 Mac App</strong>：构建时通过 Build Phase 将 backend/ 复制到 MacAgentApp.app/Contents/Resources/backend/，用户无需单独部署。</p>
            <p>体积约 180MB（仅核心依赖）。RAG/向量搜索（约 600MB）在用户首次启用时自动安装到 Application Support。</p>
            <p>可写数据：Bundle 内 data/ 只读，配置持久化到 <code className="text-[var(--accent)]">~/Library/Application Support/com.macagent.app/backend_data/</code></p>
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mb-16"
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <AlertCircle className="size-6 text-[var(--accent)]" />
            Xcode 运行后权限保留
          </h2>
          <p className="text-sm text-[var(--text-muted)] mb-4">从 Xcode 运行若每次都要重新授权，是因为默认构建到 DerivedData，路径会变。建议固定构建路径：</p>
          <ol className="list-decimal list-inside space-y-2 text-sm text-[var(--text-muted)]">
            <li>File → Workspace Settings → Build Location 选 Custom，选 Relative to Workspace 或固定目录</li>
            <li>重新编译运行，在系统设置中对该路径下的 MacAgentApp 授权一次</li>
          </ol>
          <p className="text-xs text-[var(--text-muted)] mt-3">若出现「Framework Pods_MacAgentApp not found」，请确认已用 .xcworkspace 打开并执行过 <code className="text-[var(--accent)]">pod install</code>。</p>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
        >
          <h2 className="font-display text-2xl font-semibold mb-6 flex items-center gap-2">
            <Shield className="size-6 text-[var(--accent)]" />
            安全说明
          </h2>
          <ul className="space-y-2 text-sm text-[var(--text-muted)]">
            <li>危险终端命令会被拒绝（如 rm -rf /）；Self-Upgrade 在沙箱内执行</li>
            <li>API Key 与配置存于本地（backend/data/），不会上传</li>
            <li>建议在沙盒或测试环境中验证新工具与升级流程</li>
          </ul>
        </motion.section>
      </div>
    </div>
  )
}
