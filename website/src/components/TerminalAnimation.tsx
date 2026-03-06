import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const LINES = [
  { prefix: '$', cmd: 'cd MacAgent/backend', type: 'cmd' as const },
  { prefix: '$', cmd: 'pip install -r requirements.txt', type: 'cmd' as const },
  { prefix: '>', output: 'Successfully installed fastapi uvicorn...', type: 'out' as const },
  { prefix: '$', cmd: 'python main.py', type: 'cmd' as const },
  { prefix: '>', output: 'Agent backend running on http://127.0.0.1:8765', type: 'out' as const },
  { prefix: '>', output: 'WebSocket ready · Chow Duck initialized', type: 'out' as const },
]

const LINE_DELAY = 700
const LOOP_DELAY = 4000

export default function TerminalAnimation() {
  const [visibleLines, setVisibleLines] = useState(0)
  const [cursorBlink, setCursorBlink] = useState(true)
  const [loopKey, setLoopKey] = useState(0)

  useEffect(() => {
    if (visibleLines >= LINES.length) {
      const t = setTimeout(() => {
        setVisibleLines(0)
        setLoopKey((k) => k + 1)
      }, LOOP_DELAY)
      return () => clearTimeout(t)
    }
    const t = setTimeout(() => setVisibleLines((n) => n + 1), LINE_DELAY)
    return () => clearTimeout(t)
  }, [visibleLines])

  useEffect(() => {
    const blink = setInterval(() => setCursorBlink((b) => !b), 530)
    return () => clearInterval(blink)
  }, [])

  return (
    <div className="rounded-xl border border-[var(--accent)]/30 bg-[var(--bg)]/95 p-4 font-mono text-sm overflow-hidden shadow-[0_0_30px_rgba(0,245,255,0.15)] backdrop-blur-sm">
      <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
        <span className="size-2.5 rounded-full bg-red-500/80" />
        <span className="size-2.5 rounded-full bg-amber-500/80" />
        <span className="size-2.5 rounded-full bg-emerald-500/80" />
        <span className="ml-2 text-xs text-[var(--text-muted)]">chowduck — zsh</span>
      </div>
      <div className="space-y-1 min-h-[140px]">
        <AnimatePresence mode="popLayout">
          {LINES.slice(0, visibleLines).map((line, i) => (
            <motion.div
              key={`${loopKey}-${i}`}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.25 }}
              className="flex gap-2 items-start"
            >
              <span className="text-[var(--accent)] shrink-0">{line.prefix}</span>
              {line.type === 'cmd' && (
                <span className="text-[var(--text)]">{line.cmd}</span>
              )}
              {line.type === 'out' && (
                <span className="text-emerald-400/90">{line.output}</span>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
        <span className="inline-flex items-center">
          <span className="text-[var(--accent)]">$</span>
          <span
            className={`ml-1 w-2 h-4 bg-[var(--accent)] inline-block ${
              cursorBlink ? 'opacity-100' : 'opacity-0'
            }`}
            style={{ transition: 'opacity 0.05s' }}
          />
        </span>
      </div>
    </div>
  )
}
