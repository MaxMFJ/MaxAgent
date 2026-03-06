import { useMemo } from 'react'
import { motion } from 'framer-motion'

const COUNT = 12

export default function FloatingParticles() {
  const particles = useMemo(
    () =>
      Array.from({ length: COUNT }, (_, i) => ({
        id: i,
        x: Math.random() * 100,
        y: Math.random() * 100,
        size: 2 + Math.random() * 2,
        duration: 8 + Math.random() * 8,
        delay: Math.random() * 5,
      })),
    []
  )

  return (
    <div className="fixed inset-0 pointer-events-none z-[1] overflow-hidden">
      {particles.map((p) => (
        <motion.div
          key={p.id}
          className="absolute rounded-full bg-[var(--accent)]"
          style={{
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: p.size,
            height: p.size,
            boxShadow: `0 0 ${p.size * 4}px var(--accent)`,
          }}
          animate={{
            y: [0, -30, 0],
            x: [0, 10, 0],
            opacity: [0.3, 0.8, 0.3],
          }}
          transition={{
            duration: p.duration,
            delay: p.delay,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        />
      ))}
    </div>
  )
}
