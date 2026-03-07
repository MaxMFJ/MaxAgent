import { motion } from 'framer-motion'
import { Wrench, Zap, Cpu, Box, Network, GitMerge } from 'lucide-react'

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
  { name: 'dynamic_tool_generator', desc: '动态工具生成' },
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
            30+ 内置工具覆盖文件、终端、应用、网络、开发等场景。支持 MCP 生态扩展、动态生成与 Self-Upgrade 自我升级。统一工具路由：内置优先，MCP 自动 fallback，LLM 无感知切换。
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

          <motion.section
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6"
          >
            <h2 className="font-display text-xl font-semibold mb-4 flex items-center gap-2">
              <Network className="size-5 text-[var(--accent)]" />
              MCP 生态
            </h2>
            <p className="text-sm text-[var(--text-muted)] mb-4">
              通过 Model Context Protocol 连接外部 MCP 服务器，即插即用。内置目录支持 GitHub、Brave Search、Sequential Thinking、Puppeteer、Filesystem、Memory 等，支持自定义添加。
            </p>
            <div className="grid sm:grid-cols-2 gap-2 text-sm">
              <div><code className="text-[var(--accent)] font-mono">@modelcontextprotocol/server-github</code> — 仓库/PR/Issues/代码搜索</div>
              <div><code className="text-[var(--accent)] font-mono">@modelcontextprotocol/server-brave-search</code> — 隐私优先网页搜索</div>
              <div><code className="text-[var(--accent)] font-mono">@modelcontextprotocol/server-sequential-thinking</code> — 增强推理</div>
              <div><code className="text-[var(--accent)] font-mono">@modelcontextprotocol/server-filesystem</code> — 沙箱文件操作</div>
              <div><code className="text-[var(--accent)] font-mono">@modelcontextprotocol/server-memory</code> — 知识图谱/跨会话记忆</div>
            </div>
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6"
          >
            <h2 className="font-display text-xl font-semibold mb-4 flex items-center gap-2">
              <GitMerge className="size-5 text-[var(--accent)]" />
              统一工具路由（Unified Tool Router）
            </h2>
            <p className="text-sm text-[var(--text-muted)] mb-4">
              Agent → ToolRouter → Builtin Tools → MCP Fallback
            </p>
            <ul className="space-y-2 text-sm text-[var(--text-muted)]">
              <li><span className="text-[var(--accent)]">内置工具优先</span> — Agent 执行时始终优先使用 20+ 内置工具</li>
              <li><span className="text-[var(--accent)]">MCP 自动 Fallback</span> — 内置工具执行失败时，自动尝试同名 MCP 替代</li>
              <li><span className="text-[var(--accent)]">MCP 独有工具</span> — 以 <code className="text-[var(--accent)]/80">{'{server}_{tool}'}</code> 格式对 LLM 可见</li>
              <li><span className="text-[var(--accent)]">LLM 无感知</span> — 重名 MCP 工具注册为 mcp/ 前缀（隐藏），不重复暴露</li>
            </ul>
          </motion.section>
        </div>
      </div>
    </div>
  )
}
