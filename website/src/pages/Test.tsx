import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { CheckCircle, XCircle, Loader2 } from 'lucide-react'

const BACKEND_URL = 'http://127.0.0.1:8765'

export default function Test() {
  const [health, setHealth] = useState<{ ok: boolean; status?: number; error?: string } | null>(null)

  useEffect(() => {
    let cancelled = false
    setHealth(null)
    fetch(`${BACKEND_URL}/health`)
      .then((res) => {
        if (cancelled) return
        setHealth({ ok: res.ok, status: res.status })
      })
      .catch((err) => {
        if (cancelled) return
        setHealth({ ok: false, error: err.message || '连接失败' })
      })
    return () => { cancelled = true }
  }, [])

  return (
    <div className="py-16 px-6">
      <div className="mx-auto max-w-2xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-12"
        >
          <h1 className="font-display text-4xl font-bold mb-4">服务联机测试</h1>
          <p className="text-[var(--text-muted)]">
            检测后端 Agent 服务（{BACKEND_URL}）是否可访问
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-8"
        >
          <h2 className="font-display text-lg font-semibold mb-4">后端健康检查</h2>
          <div className="flex items-center gap-4">
            {health === null && (
              <>
                <Loader2 className="size-6 text-[var(--accent)] animate-spin" />
                <span className="text-[var(--text-muted)]">正在连接...</span>
              </>
            )}
            {health?.ok && (
              <>
                <CheckCircle className="size-6 text-emerald-500" />
                <span className="text-emerald-400">连接成功</span>
                {health.status && (
                  <span className="text-sm text-[var(--text-muted)]">HTTP {health.status}</span>
                )}
              </>
            )}
            {health && !health.ok && (
              <>
                <XCircle className="size-6 text-red-500" />
                <div>
                  <span className="text-red-400">连接失败</span>
                  {health.error && (
                    <p className="text-sm text-[var(--text-muted)] mt-1">{health.error}</p>
                  )}
                  <p className="text-sm text-[var(--text-muted)] mt-2">
                    请确认后端已启动：<code className="text-[var(--accent)]">cd backend && python main.py</code>
                  </p>
                </div>
              </>
            )}
          </div>
        </motion.div>
      </div>
    </div>
  )
}
