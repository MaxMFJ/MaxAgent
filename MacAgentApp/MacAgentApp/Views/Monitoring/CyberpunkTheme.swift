import SwiftUI
#if canImport(CoreText)
import CoreText
#endif

// MARK: - Cyberpunk Color Palette（与官网 website 对齐）
// 官网 CSS: --bg #0a0a0f, --bg-card #12121f, --accent #00f5ff, --text #e8e8f0, --text-muted #8b8ba3

enum CyberColor {
    static let bg0          = Color(hex: 0x0a0a0f)   // --bg 极深背景
    static let bg1          = Color(hex: 0x12121f)   // --bg-card 卡片背景
    static let bg2          = Color(hex: 0x0f0f18)   // --bg-elevated 次级面板
    static let bgHighlight  = Color(hex: 0x1a1a2e)   // --bg-card-hover 悬停/选中

    static let cyan         = Color(hex: 0x00f5ff)   // --accent 主色
    static let cyanDim      = Color(hex: 0x00b8c4)   // --accent-dim
    static let green        = Color(red: 0.00, green: 1.00, blue: 0.55)   // 成功/在线
    static let greenDim     = Color(red: 0.00, green: 0.60, blue: 0.35)
    static let purple       = Color(hex: 0xbf00ff)   // --neon-purple
    static let purpleDim    = Color(red: 0.45, green: 0.05, blue: 0.60)
    static let orange       = Color(red: 1.00, green: 0.55, blue: 0.00)   // 警告/运行中
    static let orangeDim    = Color(red: 0.60, green: 0.30, blue: 0.00)
    static let red          = Color(red: 1.00, green: 0.15, blue: 0.25)   // 错误
    static let redDim       = Color(red: 0.55, green: 0.05, blue: 0.10)
    static let yellow       = Color(red: 1.00, green: 0.90, blue: 0.00)   // 强调/pending

    static let textPrimary  = Color(hex: 0xe8e8f0)   // --text
    static let textSecond   = Color(hex: 0x8b8ba3)   // --text-muted
    static let border       = Color(hex: 0x2a2a3a)   // --border
    static let borderGlow   = Color(hex: 0x00f5ff).opacity(0.25)
    /// 霓虹发光色（官网 --accent-glow: rgba(0,245,255,0.4)）
    static let accentGlow   = Color(hex: 0x00f5ff).opacity(0.4)
    static let neonCyan     = Color(hex: 0x00ffff)   // --neon-cyan
    static let neonPink     = Color(hex: 0xff00ff)   // --neon-pink
}

// MARK: - Color Hex 扩展

extension Color {
    init(hex: Int) {
        let r = Double((hex >> 16) & 0xff) / 255
        let g = Double((hex >> 8) & 0xff) / 255
        let b = Double(hex & 0xff) / 255
        self.init(red: r, green: g, blue: b)
    }
}

// MARK: - Cyber Font（全局仅用 Orbitron-Variable）
// 全应用统一 Orbitron 几何科技感，变量字体支持 400–900 字重

enum CyberFont {
    /// 标题/品牌
    static func display(size: CGFloat = 14, weight: Font.Weight = .semibold) -> Font {
        .custom("Orbitron", size: size).weight(weight)
    }
    /// 正文
    static func body(size: CGFloat = 13, weight: Font.Weight = .regular) -> Font {
        .custom("Orbitron", size: size).weight(weight)
    }
    /// 标签/数据/等宽风格
    static func mono(size: CGFloat = 11, weight: Font.Weight = .medium) -> Font {
        .custom("Orbitron", size: size).weight(weight)
    }

#if canImport(AppKit)
    /// NSFont 版本，供 NSTextView/AppKit 使用（Orbitron 变量字体实例）
    /// 若按名称查找失败则从 Bundle 直接加载，避免回退到 PingFang
    static func nsDisplay(size: CGFloat = 14) -> NSFont {
        NSFont(name: "Orbitron-SemiBold", size: size)
            ?? NSFont(name: "Orbitron", size: size)
            ?? nsFontFromBundle(size: size, weight: 600)
            ?? .systemFont(ofSize: size, weight: .semibold)
    }
    static func nsBody(size: CGFloat = 13) -> NSFont {
        NSFont(name: "Orbitron-Regular", size: size)
            ?? NSFont(name: "Orbitron", size: size)
            ?? nsFontFromBundle(size: size, weight: 400)
            ?? .systemFont(ofSize: size)
    }
    static func nsBodyBold(size: CGFloat = 13) -> NSFont {
        NSFont(name: "Orbitron-Bold", size: size)
            ?? NSFont(name: "Orbitron", size: size)
            ?? nsFontFromBundle(size: size, weight: 700)
            ?? .systemFont(ofSize: size, weight: .bold)
    }
    static func nsMono(size: CGFloat = 11) -> NSFont {
        NSFont(name: "Orbitron-Medium", size: size)
            ?? NSFont(name: "Orbitron", size: size)
            ?? nsFontFromBundle(size: size, weight: 500)
            ?? .systemFont(ofSize: size, weight: .medium)
    }

    /// 从 Bundle 直接加载 Orbitron-Variable.ttf，用于名称查找失败时的回退
    private static func nsFontFromBundle(size: CGFloat, weight: CGFloat) -> NSFont? {
#if canImport(CoreText)
        guard let url = Bundle.main.url(forResource: "Orbitron-Variable", withExtension: "ttf", subdirectory: "Fonts")
            ?? Bundle.main.url(forResource: "Orbitron-Variable", withExtension: "ttf") else { return nil }
        guard let descriptors = CTFontManagerCreateFontDescriptorsFromURL(url as CFURL) as? [CTFontDescriptor],
              let first = descriptors.first else { return nil }
        let ctFont = CTFontCreateWithFontDescriptor(first, size, nil)
        return ctFont as NSFont?
#else
        return nil
#endif
    }
#endif
}

// MARK: - 霓虹发光文字（官网 neon-text + neon-breathe）
// text-shadow: 0 0 10px/20px/40px accent-glow；呼吸动画 3s 循环

struct NeonGlowText: ViewModifier {
    var color: Color = CyberColor.accentGlow
    var breathe: Bool = false
    @State private var breathPhase: Bool = false

    func body(content: Content) -> some View {
        let r1: CGFloat = breathe ? (breathPhase ? 15 : 10) : 10
        let r2: CGFloat = breathe ? (breathPhase ? 35 : 20) : 20
        let r3: CGFloat = breathe ? (breathPhase ? 50 : 40) : 40
        let o: Double = breathe ? (breathPhase ? 0.5 : 0.35) : 0.4
        content
            .shadow(color: color.opacity(o), radius: r1)
            .shadow(color: color.opacity(o), radius: r2)
            .shadow(color: color.opacity(o * 0.8), radius: r3)
            .animation(breathe ? .easeInOut(duration: 1.5).repeatForever(autoreverses: true) : .default, value: breathPhase)
            .onAppear { if breathe { breathPhase = true } }
    }
}

extension View {
    /// 霓虹发光，可选呼吸动画
    func neonGlow(color: Color = CyberColor.accentGlow, breathe: Bool = false) -> some View {
        modifier(NeonGlowText(color: color, breathe: breathe))
    }
}

// MARK: - Cyber Card（官网 rounded-xl = 12，增强霓虹边框）

struct CyberCard<Content: View>: View {
    var glowColor: Color = CyberColor.cyan
    var padding: CGFloat = 14
    @ViewBuilder let content: () -> Content

    var body: some View {
        content()
            .padding(padding)
            .background(CyberColor.bg1)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(glowColor.opacity(0.35), lineWidth: 1)
            )
            .cornerRadius(12)
            .shadow(color: glowColor.opacity(0.15), radius: 12, x: 0, y: 0)
            .shadow(color: glowColor.opacity(0.08), radius: 24, x: 0, y: 0)
    }
}

// MARK: - Neon Label（使用 display 字体，与官网 font-display 对齐，可选发光）

struct CyberLabel: View {
    let text: String
    var color: Color = CyberColor.cyan
    var size: CGFloat = 10
    var glow: Bool = false

    var body: some View {
        Text(text.uppercased())
            .font(CyberFont.display(size: size, weight: .semibold))
            .foregroundColor(color)
            .tracking(1.5)
            .modifier(OptionalNeonGlow(glow: glow, color: color.opacity(0.4)))
    }
}

private struct OptionalNeonGlow: ViewModifier {
    let glow: Bool
    let color: Color
    func body(content: Content) -> some View {
        if glow {
            content
                .shadow(color: color, radius: 8)
                .shadow(color: color, radius: 16)
        } else {
            content
        }
    }
}

// MARK: - 丰富背景（官网层次：网格 + 顶部渐变 + 紫色/青色径向光晕）

struct CyberRichBackground: View {
    var body: some View {
        ZStack {
            CyberGridBackground()
            // 官网 Home: from accent/10 via transparent
            LinearGradient(
                colors: [CyberColor.cyan.opacity(0.1), Color.clear],
                startPoint: .top,
                endPoint: .bottom
            )
            .allowsHitTesting(false)
            // 官网: radial ellipse 80% 50% at 50% -20%, purple/20%
            RadialGradient(
                colors: [CyberColor.purple.opacity(0.15), Color.clear],
                center: UnitPoint(x: 0.5, y: 0.0),
                startRadius: 0,
                endRadius: 350
            )
            .allowsHitTesting(false)
            // 官网: radial ellipse 60% 40% at 80% 20%, accent/8%
            RadialGradient(
                colors: [CyberColor.cyan.opacity(0.08), Color.clear],
                center: UnitPoint(x: 0.85, y: 0.15),
                startRadius: 0,
                endRadius: 280
            )
            .allowsHitTesting(false)
            // 底部渐变过渡
            VStack {
                Spacer()
                LinearGradient(
                    colors: [Color.clear, CyberColor.bg0.opacity(0.6)],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .frame(height: 120)
            }
            .allowsHitTesting(false)
        }
    }
}

// MARK: - Scan Line Background

struct ScanLineBackground: View {
    var body: some View {
        ZStack {
            CyberColor.bg0
            // subtle scanlines — 用 Canvas 替代 ForEach 避免创建数百个子视图
            Canvas { ctx, size in
                let step: CGFloat = 4
                var y: CGFloat = 0
                while y < size.height {
                    let rect = CGRect(x: 0, y: y, width: size.width, height: 2)
                    ctx.fill(Path(rect), with: .color(.white.opacity(0.012)))
                    y += step
                }
            }
            .drawingGroup()
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
                .fill(color.opacity(glow ? 0.35 : 0.15))
                .frame(width: size * 2.2, height: size * 2.2)
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
                .font(CyberFont.display(size: 26, weight: .bold))
                .foregroundColor(color)
                .shadow(color: color.opacity(0.6), radius: 4, x: 0, y: 0)
            CyberLabel(text: label, color: CyberColor.textSecond, size: 9)
            if let sub = subLabel {
                Text(sub)
                    .font(CyberFont.mono(size: 9))
                    .foregroundColor(CyberColor.textSecond.opacity(0.7))
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(CyberColor.bg1)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(color.opacity(0.3), lineWidth: 1))
        .cornerRadius(8)
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

// MARK: - AI 思考中动画（轻量级脉冲圆点，无 TimelineView）

struct AIThinkingBrain: View {
    var isActive: Bool = true
    var nodeCount: Int = 12
    @State private var pulse: Bool = false

    var body: some View {
        GeometryReader { geo in
            let center = CGPoint(x: geo.size.width / 2, y: geo.size.height / 2)
            let radius = min(geo.size.width, geo.size.height) * 0.35
            ZStack {
                ForEach(0..<nodeCount, id: \.self) { i in
                    let angle = CGFloat(i) / CGFloat(nodeCount) * 2 * .pi - .pi / 2
                    let x = center.x + radius * CGFloat(cos(Double(angle)))
                    let y = center.y + radius * CGFloat(sin(Double(angle)))
                    Circle()
                        .fill(isActive ? CyberColor.cyan : CyberColor.cyan.opacity(0.3))
                        .frame(width: 6, height: 6)
                        .scaleEffect(isActive && pulse ? (i.isMultiple(of: 2) ? 1.3 : 0.7) : 1.0)
                        .opacity(isActive ? (pulse ? (i.isMultiple(of: 3) ? 0.5 : 1.0) : 0.7) : 0.4)
                        .position(x: x, y: y)
                        .animation(
                            isActive
                                ? .easeInOut(duration: 1.2 + Double(i % 3) * 0.3).repeatForever(autoreverses: true)
                                : .default,
                            value: pulse
                        )
                }
            }
        }
        .onAppear { if isActive { pulse = true } }
        .onChange(of: isActive) { _, active in pulse = active }
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
            .onChange(of: values.count) {
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

// MARK: - 浮动粒子背景（轻量级，使用隐式动画而非 TimelineView）

struct FloatingParticlesView: View {
    var particleCount: Int = 20
    @State private var drift: Bool = false

    var body: some View {
        GeometryReader { geo in
            ZStack {
                ForEach(0..<particleCount, id: \.self) { i in
                    Circle()
                        .fill(CyberColor.cyan.opacity(0.12))
                        .frame(width: 4, height: 4)
                        .offset(
                            x: drift ? CGFloat(((i * 7 + 3) % 11) - 5) * 8 : 0,
                            y: drift ? CGFloat(((i * 5 + 2) % 9) - 4) * 6 : 0
                        )
                        .position(
                            x: geo.size.width * (0.1 + 0.8 * CGFloat(i) / CGFloat(max(particleCount, 1))),
                            y: geo.size.height * (0.2 + 0.6 * CGFloat((i * 37 % particleCount)) / CGFloat(max(particleCount, 1)))
                        )
                        .animation(
                            .easeInOut(duration: 3.0 + Double(i % 4) * 0.8)
                            .repeatForever(autoreverses: true),
                            value: drift
                        )
                }
            }
        }
        .onAppear { drift = true }
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
                    .font(CyberFont.body(size: 12))
                    .foregroundColor(CyberColor.green)
                    .offset(x: CGFloat(cos(Double(i) * .pi / 3)) * 24, y: CGFloat(sin(Double(i) * .pi / 3)) * 24)
                    .opacity(opacity)
            }
            Image(systemName: "checkmark.circle.fill")
                .font(CyberFont.display(size: 32))
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

// MARK: - Hex Grid Pattern（官网 --grid-color: rgba(0,245,255,0.06)）

struct HexGridPattern: View {
    var color: Color = CyberColor.cyan.opacity(0.06)

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
        .drawingGroup()
    }
}
