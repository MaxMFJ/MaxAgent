import { useEffect, useRef } from 'react'

export default function AnimatedGrid() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animationId: number
    let offset = 0
    const gridSize = 48
    const lineColor = 'rgba(0, 245, 255, 0.08)'
    const accentLineColor = 'rgba(0, 245, 255, 0.18)'

    const resize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }

    const draw = () => {
      if (!ctx || !canvas) return
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      offset += 0.3
      if (offset >= gridSize) offset = 0

      for (let x = -offset; x < canvas.width + gridSize; x += gridSize) {
        ctx.beginPath()
        ctx.moveTo(x, 0)
        ctx.lineTo(x, canvas.height)
        ctx.strokeStyle = x % (gridSize * 2) === 0 ? accentLineColor : lineColor
        ctx.lineWidth = 1
        ctx.stroke()
      }

      for (let y = -offset; y < canvas.height + gridSize; y += gridSize) {
        ctx.beginPath()
        ctx.moveTo(0, y)
        ctx.lineTo(canvas.width, y)
        ctx.strokeStyle = y % (gridSize * 2) === 0 ? accentLineColor : lineColor
        ctx.lineWidth = 1
        ctx.stroke()
      }

      animationId = requestAnimationFrame(draw)
    }

    resize()
    window.addEventListener('resize', resize)
    draw()

    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none"
      style={{ opacity: 0.6, zIndex: 0 }}
    />
  )
}
