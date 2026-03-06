import { motion } from 'framer-motion'
import { FileText } from 'lucide-react'

const docs = [
  { name: 'README', path: 'README.md', desc: '项目概览、快速开始、系统要求、主要 API、环境变量' },
  { name: '后端结构', path: 'docs/backend-structure.md', desc: '模块说明、数据流、核心组件' },
  { name: '新环境部署指南', path: 'docs/新环境部署指南.md', desc: '新机器部署、依赖安装、环境配置' },
  { name: '自愈功能测试指南', path: 'docs/自愈功能测试指南.md', desc: '自愈诊断与修复流程测试' },
  { name: '后台功能清单', path: 'docs/后台功能清单-人工测试审核.md', desc: 'API 与功能人工测试清单' },
  { name: '主线目标与路线图', path: 'docs/主线目标与路线图.md', desc: '2026 标杆、Phase A/B/C 里程碑' },
  { name: 'Web 端功能拆分', path: 'docs/Web端功能拆分文档.md', desc: 'Web 端模块与功能拆分' },
  { name: 'v3.2 功能清单', path: 'docs/v3.2_PLAN.md', desc: 'Trace、可观测、可评估、Benchmark 自动化' },
]

export default function Docs() {
  return (
    <div className="py-16 px-6">
      <div className="mx-auto max-w-4xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-16"
        >
          <p className="font-display text-sm tracking-[0.2em] text-[var(--accent)] uppercase mb-2">Documentation</p>
          <h1 className="font-display text-4xl font-bold mb-4">文档</h1>
          <p className="text-lg text-[var(--text-muted)]">
            项目文档索引，涵盖部署、架构、测试与路线图。文档位于项目 <code className="rounded bg-[var(--bg-elevated)] px-1.5 py-0.5 text-[var(--accent)]">docs/</code> 目录，可在本地直接查阅。
          </p>
        </motion.div>

        <div className="space-y-4">
          {docs.map((doc, i) => (
            <motion.div
              key={doc.path}
              initial={{ opacity: 0, x: -20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.05 }}
              className="card-cyber flex items-start gap-4 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-4 transition-all duration-300"
            >
              <FileText className="size-5 text-[var(--accent)] flex-shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-white">{doc.name}</span>
                </div>
                <p className="text-sm text-[var(--text-muted)] mt-1">{doc.desc}</p>
                <p className="text-xs text-[var(--text-muted)]/70 mt-2 font-mono">{doc.path}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  )
}
