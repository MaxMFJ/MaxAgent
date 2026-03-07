import { motion } from 'framer-motion'
import { MessageSquare, Brain, Mic, BarChart3, Settings, Cloud, Zap, Shield, Network, FileCheck, Flag, RotateCcw } from 'lucide-react'
import { Link } from 'react-router-dom'

const features = [
  {
    icon: MessageSquare,
    title: '流式对话 (ReAct)',
    desc: '基于 ReAct 推理链的流式对话：Agent 按需调用工具（文件、终端、应用、截图、邮件等），支持断线重连与输出恢复。三阶段 Prompt（Gather → Act → Verify）确保执行质量。简单查询用 LITE system prompt，复杂任务用 FULL；上下文 token 上限 2000，工具 schema 按查询语义裁剪（最多 8 个）。',
  },
  {
    icon: Brain,
    title: '自主任务 (Autonomous)',
    desc: '长 horizon 多步执行：三阶段主循环（Gather → Act → Verify），可选反思（失败分类 + 专用 prompt）、模型选择（本地/云端按任务复杂度）、自适应停止（任务完成/无进展/循环检测）。支持 Plan-and-Execute 模式。',
  },
  {
    icon: Network,
    title: 'MCP 生态集成',
    desc: '通过 Model Context Protocol 连接外部 MCP 服务器（GitHub、Brave Search、Sequential Thinking、Puppeteer、Filesystem、Memory 等），即插即用。支持 stdio（npx 子进程）和 HTTP 两种传输；配置持久化，启动自动重连。内置 6 个 MCP 服务一键连接，支持自定义添加。',
  },
  {
    icon: Mic,
    title: '语音与 TTS',
    desc: '实时语音识别（中/英）、静音自动提交、无说话超时提交；流式按句 TTS 朗读、支持中英文，可随时停止。Mac 客户端原生集成。',
  },
  {
    icon: BarChart3,
    title: '监控仪表板',
    desc: '执行时间线、系统状态、历史分析、实时日志流；Token/RPM/TPM 统计、模型分布；v3.2 Trace 级 span 统计与执行轨迹持久化。上下文可视化：Token 用量、文件清单、模型路由统计、Phase 阶段统计。',
  },
  {
    icon: Flag,
    title: 'v3.3 人机协同与安全',
    desc: 'FeatureFlag 体系化（REST API + 热更新 + 持久化）；HITL 人工审批（危险操作弹窗确认，可配超时 120s）；统一审计日志（全量操作记录，磁盘自动轮转）；会话恢复/分支（Session Resume / Fork）；SubAgent 并行（最多 3 个）；幂等任务（同一 task hash 24h 不重复执行）。',
  },
  {
    icon: RotateCcw,
    title: 'v3.4 可回滚与模型路由',
    desc: '可回滚操作：文件操作前自动快照（最多 500 条），支持 write/delete/move/copy 一键 undo。三级模型路由：Fast（本地/低延迟）/ Strong（旗舰远程）/ Cheap（性价比），按任务复杂度自动选择。上下文查询 API：/context 提供完整运行时状态快照。',
  },
  {
    icon: Settings,
    title: '权限管理',
    desc: '辅助功能、屏幕录制、自动化、cliclick、Quartz、osascript 状态检测与引导。快捷入口：工具栏齿轮 → 设置 → 权限，一键打开系统设置。',
  },
  {
    icon: Cloud,
    title: 'Cloudflare Tunnel',
    desc: '隧道自动启停、局域网信息、Token 认证；支持远程访问 Web 端与 iOS 客户端；生命周期管理完整。',
  },
  {
    icon: Zap,
    title: '工具自我升级',
    desc: 'Planner → Strategy → Executor → Validation → Activation 流程；沙箱执行（resource_dispatcher）；动态加载 generated 工具。',
  },
  {
    icon: Shield,
    title: '自愈能力',
    desc: '诊断引擎、修复计划与执行；HTTP 与 WebSocket 调用；v3.2 支持 7 种 FailureType 失败分类反思。',
  },
  {
    icon: FileCheck,
    title: 'Workspace 与终端增强',
    desc: 'Workspace 上下文：上报当前工作目录、打开文件，供 prompt 注入。终端会话增强：记录 cwd/输出，供后续命令和 prompt 复用。',
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
          <p className="font-display text-sm tracking-[0.2em] text-[var(--accent)] uppercase mb-2">Capabilities</p>
          <h1 className="font-display text-4xl font-bold mb-4">功能特性</h1>
          <p className="text-lg text-[var(--text-muted)]">
            Chow Duck 提供完整的 Agent 对话、执行、监控与扩展能力。支持 Mac 客户端与 Web 端多端同步，Mac/iOS 按 session 共享会话。可选 LangChain 兼容（与原生引擎并存、可随时切换）。
          </p>
        </motion.div>

        <div className="space-y-8">
          {features.map((item, i) => (
            <motion.div
              key={item.title}
              initial={{ opacity: 0, x: -20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.05 }}
              className="card-cyber flex gap-6 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6 transition-all duration-300"
            >
              <div className="flex-shrink-0 rounded-xl bg-[var(--accent)]/10 p-4 border border-[var(--accent)]/20">
                <item.icon className="size-8 text-[var(--accent)]" />
              </div>
              <div>
                <h2 className="font-display text-xl font-semibold mb-2 text-white">{item.title}</h2>
                <p className="text-[var(--text-muted)] leading-relaxed">{item.desc}</p>
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
          <p className="text-[var(--text-muted)] mb-4">深入了解技术实现</p>
          <Link
            to="/technology"
            className="inline-flex items-center gap-2 text-[var(--accent)] hover:underline font-medium"
          >
            技术架构
          </Link>
        </motion.div>
      </div>
    </div>
  )
}
