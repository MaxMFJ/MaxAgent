import { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Menu, X } from 'lucide-react'
import { useState } from 'react'

const navItems = [
  { path: '/', label: '首页' },
  { path: '/features', label: '功能' },
  { path: '/technology', label: '技术' },
  { path: '/tools', label: '工具' },
  { path: '/skills', label: '技能' },
  { path: '/docs', label: '文档' },
  { path: '/help', label: '帮助' },
  { path: '/roadmap', label: '待扩展' },
  { path: '/test', label: '联机测试' },
]

export default function Layout({ children }: { children: ReactNode }) {
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="min-h-screen relative z-10">
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-[var(--border)] bg-[var(--bg)]/90 backdrop-blur-xl shadow-[0_0_30px_rgba(0,245,255,0.08)]">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link to="/" className="font-display text-xl font-bold tracking-wider text-[var(--accent)] neon-text">
            CHOW DUCK
          </Link>
          <nav className="hidden md:flex items-center gap-8">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`text-sm font-medium transition-all duration-300 ${
                  location.pathname === item.path
                    ? 'text-[var(--accent)] drop-shadow-[0_0_8px_rgba(0,245,255,0.5)]'
                    : 'text-[var(--text-muted)] hover:text-[var(--accent)]'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <button
            className="md:hidden p-2"
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        {mobileOpen && (
          <motion.nav
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden border-t border-[var(--border)] bg-[var(--bg-elevated)]"
          >
            <div className="flex flex-col py-4 px-6 gap-4">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setMobileOpen(false)}
                  className={location.pathname === item.path ? 'text-[var(--accent)]' : ''}
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </motion.nav>
        )}
      </header>
      <main className="pt-16">{children}</main>
      <footer className="border-t border-[var(--border)] bg-[var(--bg-elevated)]/95 py-12 relative">
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-[var(--accent)]/50 to-transparent" />
        <div className="mx-auto max-w-6xl px-6">
          <div className="flex flex-col md:flex-row justify-between items-center gap-6">
            <span className="font-display text-sm text-[var(--text-muted)] tracking-wider">
              CHOW DUCK · macOS AI AGENT
            </span>
            <div className="flex gap-8 text-sm text-[var(--text-muted)]">
              <Link to="/docs" className="hover:text-[var(--text)]">文档</Link>
              <Link to="/help" className="hover:text-[var(--text)]">帮助</Link>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
