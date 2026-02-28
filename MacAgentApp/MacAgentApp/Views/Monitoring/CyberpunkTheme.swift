import SwiftUI

// MARK: - Cyberpunk Color Palette

enum CyberColor {
    static let bg0          = Color(red: 0.04, green: 0.04, blue: 0.08)   // 极深背景
    static let bg1          = Color(red: 0.07, green: 0.07, blue: 0.12)   // 卡片背景
    static let bg2          = Color(red: 0.10, green: 0.10, blue: 0.16)   // 次级面板
    static let bgHighlight  = Color(red: 0.12, green: 0.12, blue: 0.20)   // 悬停/选中

    static let cyan         = Color(red: 0.00, green: 0.90, blue: 1.00)   // 主色 - 青
    static let cyanDim      = Color(red: 0.00, green: 0.55, blue: 0.65)
    static let green        = Color(red: 0.00, green: 1.00, blue: 0.55)   // 成功/在线
    static let greenDim     = Color(red: 0.00, green: 0.60, blue: 0.35)
    static let purple       = Color(red: 0.75, green: 0.10, blue: 1.00)   // 强调
    static let purpleDim    = Color(red: 0.45, green: 0.05, blue: 0.60)
    static let orange       = Color(red: 1.00, green: 0.55, blue: 0.00)   // 警告/运行中
    static let orangeDim    = Color(red: 0.60, green: 0.30, blue: 0.00)
    static let red          = Color(red: 1.00, green: 0.15, blue: 0.25)   // 错误
    static let redDim       = Color(red: 0.55, green: 0.05, blue: 0.10)
    static let yellow       = Color(red: 1.00, green: 0.90, blue: 0.00)   // 强调/pending

    static let textPrimary  = Color(red: 0.88, green: 0.92, blue: 1.00)
    static let textSecond   = Color(red: 0.45, green: 0.52, blue: 0.65)
    static let border       = Color(red: 0.20, green: 0.22, blue: 0.32)
    static let borderGlow   = Color(red: 0.00, green: 0.90, blue: 1.00).opacity(0.25)
}

// MARK: - Cyber Card

struct CyberCard<Content: View>: View {
    var glowColor: Color = CyberColor.cyan
    var padding: CGFloat = 14
    @ViewBuilder let content: () -> Content

    var body: some View {
        content()
            .padding(padding)
            .background(CyberColor.bg1)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(glowColor.opacity(0.35), lineWidth: 1)
            )
            .cornerRadius(8)
            .shadow(color: glowColor.opacity(0.10), radius: 8, x: 0, y: 0)
    }
}

// MARK: - Neon Label

struct CyberLabel: View {
    let text: String
    var color: Color = CyberColor.cyan
    var size: CGFloat = 10

    var body: some View {
        Text(text.uppercased())
            .font(.system(size: size, weight: .semibold, design: .monospaced))
            .foregroundColor(color)
            .tracking(1.5)
    }
}

// MARK: - Scan Line Background

struct ScanLineBackground: View {
    var body: some View {
        ZStack {
            CyberColor.bg0
            // subtle scanlines
            GeometryReader { geo in
                VStack(spacing: 0) {
                    ForEach(0..<Int(geo.size.height / 4), id: \.self) { _ in
                        Color.white.opacity(0.012)
                            .frame(height: 2)
                        Color.clear.frame(height: 2)
                    }
                }
            }
        }
        .ignoresSafeArea()
    }
}

// MARK: - Neon Dot

struct NeonDot: View {
    let color: Color
    var size: CGFloat = 8
    @State private var glow: Bool = false

    var body: some View {
        ZStack {
            Circle()
                .fill(color.opacity(0.25))
                .frame(width: size * 2.2, height: size * 2.2)
                .blur(radius: glow ? 4 : 2)
                .animation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true), value: glow)
            Circle()
                .fill(color)
                .frame(width: size, height: size)
        }
        .onAppear { glow = true }
    }
}

// MARK: - Cyber Stat Box

struct CyberStatBox: View {
    let label: String
    let value: String
    var color: Color = CyberColor.cyan
    var subLabel: String? = nil

    var body: some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.system(size: 26, weight: .bold, design: .monospaced))
                .foregroundColor(color)
                .shadow(color: color.opacity(0.6), radius: 4, x: 0, y: 0)
            CyberLabel(text: label, color: CyberColor.textSecond, size: 9)
            if let sub = subLabel {
                Text(sub)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(CyberColor.textSecond.opacity(0.7))
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(CyberColor.bg1)
        .overlay(RoundedRectangle(cornerRadius: 6).stroke(color.opacity(0.3), lineWidth: 1))
        .cornerRadius(6)
        .shadow(color: color.opacity(0.08), radius: 6)
    }
}

// MARK: - Cyber Progress Bar

struct CyberBar: View {
    let ratio: Double          // 0...1
    var color: Color = CyberColor.cyan
    var height: CGFloat = 6
    var animated: Bool = true

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: height / 2)
                    .fill(color.opacity(0.12))
                RoundedRectangle(cornerRadius: height / 2)
                    .fill(
                        LinearGradient(
                            colors: [color.opacity(0.6), color],
                            startPoint: .leading, endPoint: .trailing
                        )
                    )
                    .frame(width: geo.size.width * max(0, min(ratio, 1)))
                    .animation(animated ? .easeInOut(duration: 0.5) : .none, value: ratio)
                    .shadow(color: color.opacity(0.5), radius: 2)
            }
        }
        .frame(height: height)
    }
}

// MARK: - Corner Accent Decoration

struct CornerAccent: View {
    var color: Color = CyberColor.cyan
    var size: CGFloat = 10
    var lineWidth: CGFloat = 1.5

    var body: some View {
        ZStack {
            // top-left
            Path { p in
                p.move(to: CGPoint(x: 0, y: size))
                p.addLine(to: CGPoint(x: 0, y: 0))
                p.addLine(to: CGPoint(x: size, y: 0))
            }
            .stroke(color, lineWidth: lineWidth)

            GeometryReader { geo in
                // top-right
                Path { p in
                    p.move(to: CGPoint(x: geo.size.width - size, y: 0))
                    p.addLine(to: CGPoint(x: geo.size.width, y: 0))
                    p.addLine(to: CGPoint(x: geo.size.width, y: size))
                }
                .stroke(color, lineWidth: lineWidth)

                // bottom-left
                Path { p in
                    p.move(to: CGPoint(x: 0, y: geo.size.height - size))
                    p.addLine(to: CGPoint(x: 0, y: geo.size.height))
                    p.addLine(to: CGPoint(x: size, y: geo.size.height))
                }
                .stroke(color, lineWidth: lineWidth)

                // bottom-right
                Path { p in
                    p.move(to: CGPoint(x: geo.size.width - size, y: geo.size.height))
                    p.addLine(to: CGPoint(x: geo.size.width, y: geo.size.height))
                    p.addLine(to: CGPoint(x: geo.size.width, y: geo.size.height - size))
                }
                .stroke(color, lineWidth: lineWidth)
            }
        }
    }
}

// MARK: - AI 思考中动画（神经网络节点闪烁）

struct AIThinkingBrain: View {
    var isActive: Bool = true
    var nodeCount: Int = 12

    var body: some View {
        TimelineView(.animation(minimumInterval: 0.05)) { ctx in
            AIThinkingBrainContent(isActive: isActive, nodeCount: nodeCount, time: ctx.date.timeIntervalSinceReferenceDate)
        }
    }
}

private struct AIThinkingBrainContent: View {
    let isActive: Bool
    let nodeCount: Int
    let time: TimeInterval

    private var phase: CGFloat {
        CGFloat(time.truncatingRemainder(dividingBy: 4) / 4 * 2 * Double.pi)
    }

    var body: some View {
        GeometryReader { geo in
            let center = CGPoint(x: geo.size.width / 2, y: geo.size.height / 2)
            let radius = min(geo.size.width, geo.size.height) * 0.35
            ZStack {
                ForEach(0..<nodeCount, id: \.self) { i in
                    BrainNode(isActive: isActive, index: i, total: nodeCount, phase: phase, center: center, radius: radius)
                }
            }
        }
    }
}

private struct BrainNode: View {
    let isActive: Bool
    let index: Int
    let total: Int
    let phase: CGFloat
    let center: CGPoint
    let radius: CGFloat

    private var angle: CGFloat {
        CGFloat(index) / CGFloat(total) * 2 * .pi - .pi / 2 + phase * 0.3
    }

    private var x: CGFloat { center.x + radius * CGFloat(cos(Double(angle))) }
    private var y: CGFloat { center.y + radius * CGFloat(sin(Double(angle))) }

    var body: some View {
        Circle()
            .fill(isActive ? CyberColor.cyan : CyberColor.cyan.opacity(0.3))
            .frame(width: 6, height: 6)
            .scaleEffect(isActive ? (0.8 + 0.4 * CGFloat(sin(Double(phase + CGFloat(index))))) : 1)
            .position(x: x, y: y)
            .opacity(isActive ? (0.6 + 0.4 * CGFloat(sin(Double(phase * 2 + CGFloat(index) * 0.5)))) : 0.4)
    }
}

// MARK: - 打字光标（闪烁）

struct TypingCursor: View {
    @State private var visible = true
    var color: Color = CyberColor.cyan

    var body: some View {
        Rectangle()
            .fill(color)
            .frame(width: 2, height: 14)
            .opacity(visible ? 1 : 0)
            .onAppear {
                withAnimation(.easeInOut(duration: 0.5).repeatForever(autoreverses: true)) { visible = false }
            }
    }
}

// MARK: - 迷你折线图（带动画）

struct MiniSparkLineChart: View {
    let values: [Double]  // 0...1 normalized
    var color: Color = CyberColor.cyan
    var height: CGFloat = 36
    @State private var drawProgress: CGFloat = 0

    var body: some View {
        SparkLineChartBody(values: values, color: color, height: height, drawProgress: $drawProgress)
            .frame(height: height)
            .onAppear {
                withAnimation(.easeOut(duration: 1.2)) { drawProgress = 1 }
            }
            .onChange(of: values.count) { _ in
                drawProgress = 0
                withAnimation(.easeOut(duration: 0.8)) { drawProgress = 1 }
            }
    }
}

private struct SparkLineChartBody: View {
    let values: [Double]
    let color: Color
    let height: CGFloat
    @Binding var drawProgress: CGFloat

    var body: some View {
        GeometryReader { geo in
            let pts = sparkPoints(in: geo.size)
            ZStack(alignment: .bottom) {
                RoundedRectangle(cornerRadius: 4)
                    .fill(color.opacity(0.08))
                    .frame(height: height)
                SparkLinePath(points: pts, progress: drawProgress, color: color, height: height)
            }
        }
    }

    private func sparkPoints(in size: CGSize) -> [CGPoint] {
        guard !values.isEmpty else { return [] }
        let w = size.width
        let h = height
        let n = max(1, values.count - 1)
        return values.enumerated().map { i, v in
            CGPoint(x: w * CGFloat(i) / CGFloat(n), y: h - h * CGFloat(v))
        }
    }
}

private struct SparkLinePath: View {
    let points: [CGPoint]
    let progress: CGFloat
    let color: Color
    let height: CGFloat

    var body: some View {
        Path { path in
            guard points.count > 1 else { return }
            path.move(to: points[0])
            let endIdx = min(points.count - 1, max(0, Int(CGFloat(points.count - 1) * progress)))
            guard endIdx >= 1 else { return }  // 避免 1...0 崩溃
            for i in 1...endIdx {
                path.addLine(to: points[i])
            }
        }
        .trim(from: 0, to: progress)
        .stroke(color, style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
        .frame(height: height)
    }
}

// MARK: - 浮动粒子背景（空状态用）

struct FloatingParticlesView: View {
    var particleCount: Int = 20

    var body: some View {
        TimelineView(.animation(minimumInterval: 0.08)) { ctx in
            FloatingParticlesContent(particleCount: particleCount, time: ctx.date.timeIntervalSinceReferenceDate)
        }
    }
}

private struct FloatingParticlesContent: View {
    let particleCount: Int
    let time: TimeInterval

    private var phase: CGFloat {
        CGFloat(time.truncatingRemainder(dividingBy: 6) / 6 * 2 * Double.pi)
    }

    var body: some View {
        GeometryReader { geo in
            ZStack {
                ForEach(0..<particleCount, id: \.self) { i in
                    FloatingParticle(phase: phase, index: i, size: geo.size, total: particleCount)
                }
            }
        }
    }
}

private struct FloatingParticle: View {
    let phase: CGFloat
    let index: Int
    let size: CGSize
    let total: Int

    var body: some View {
        Circle()
            .fill(CyberColor.cyan.opacity(0.15))
            .frame(width: 4, height: 4)
            .offset(x: CGFloat(sin(Double(phase + CGFloat(index) * 0.7))) * 40,
                    y: CGFloat(cos(Double(phase + CGFloat(index) * 0.5))) * 30 - CGFloat(index % 3) * 20)
            .position(x: size.width * (0.2 + 0.6 * (CGFloat(index) / CGFloat(total))),
                      y: size.height * (0.3 + 0.4 * CGFloat(sin(Double(index) * 0.3))))
    }
}

// MARK: - 成功庆祝徽章（任务完成时）

struct SuccessCelebrationBadge: View {
    @State private var scale: CGFloat = 0.5
    @State private var opacity: Double = 0

    var body: some View {
        ZStack {
            ForEach(0..<6, id: \.self) { i in
                Image(systemName: "sparkle")
                    .font(.system(size: 12))
                    .foregroundColor(CyberColor.green)
                    .offset(x: CGFloat(cos(Double(i) * .pi / 3)) * 24, y: CGFloat(sin(Double(i) * .pi / 3)) * 24)
                    .opacity(opacity)
            }
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 32))
                .foregroundColor(CyberColor.green)
                .scaleEffect(scale)
        }
        .onAppear {
            withAnimation(.spring(response: 0.4, dampingFraction: 0.6)) {
                scale = 1.2
                opacity = 1
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                withAnimation(.easeOut(duration: 0.3)) { scale = 1 }
            }
        }
    }
}

// MARK: - Hex Grid Pattern

struct HexGridPattern: View {
    var color: Color = CyberColor.cyan.opacity(0.04)

    var body: some View {
        Canvas { ctx, size in
            let w: CGFloat = 28
            let h = w * 0.866
            var row = 0
            var y: CGFloat = 0
            while y < size.height + h {
                let offset: CGFloat = row.isMultiple(of: 2) ? 0 : w * 0.75
                var x = offset
                while x < size.width + w {
                    let center = CGPoint(x: x, y: y)
                    var path = Path()
                    for i in 0..<6 {
                        let angle = CGFloat(i) * .pi / 3 - .pi / 6
                        let pt = CGPoint(x: center.x + w * 0.5 * CGFloat(cos(Double(angle))),
                                         y: center.y + h * 0.5 * CGFloat(sin(Double(angle))))
                        i == 0 ? path.move(to: pt) : path.addLine(to: pt)
                    }
                    path.closeSubpath()
                    ctx.stroke(path, with: .color(color), lineWidth: 0.5)
                    x += w * 1.5
                }
                y += h
                row += 1
            }
        }
    }
}
