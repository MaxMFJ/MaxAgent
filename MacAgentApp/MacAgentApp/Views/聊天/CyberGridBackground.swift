import SwiftUI
import AppKit

// MARK: - SwiftUI wrapper (zero SwiftUI layout overhead)

/// 赛博朋克动态网格背景 — 使用原生 NSView + CVDisplayLink 渲染
///
/// 完全绕过 SwiftUI 的 TimelineView / layout 系统，
/// 避免每帧触发整个视图树重新布局。CPU 开销接近零。
struct CyberGridBackground: NSViewRepresentable {

    func makeNSView(context: Context) -> CyberGridNSView {
        CyberGridNSView()
    }

    func updateNSView(_ nsView: CyberGridNSView, context: Context) {}
}

// MARK: - 原生 NSView：低频 Timer 驱动 + colorEffect 静态壳

/// 用一个简单的 SwiftUI 子场景，通过窗口内嵌 NSHostingView 来驱动 Shader，
/// 这样只有这个小 HostingView 的 body 会更新，不会触发外部 ChatView re-layout。
final class CyberGridNSView: NSView {

    private static let timeWrap: Double = 7_200          // 2h loop
    private static let fps: Double = 10                   // 10fps 足够平滑扫描波
    private var hostingView: NSHostingView<AnyView>?
    private var timer: Timer?

    /// 可被 Timer 更新的时间值；由 HostingView 的 rootView 观察。
    private let timeHolder = TimeHolder()

    override init(frame: NSRect) {
        super.init(frame: frame)
        setupHostingView()
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        setupHostingView()
    }

    // MARK: setup

    private func setupHostingView() {
        let rootView = CyberGridShaderView(holder: timeHolder)
        let host = NSHostingView(rootView: AnyView(rootView))
        host.translatesAutoresizingMaskIntoConstraints = false
        addSubview(host)
        NSLayoutConstraint.activate([
            host.leadingAnchor.constraint(equalTo: leadingAnchor),
            host.trailingAnchor.constraint(equalTo: trailingAnchor),
            host.topAnchor.constraint(equalTo: topAnchor),
            host.bottomAnchor.constraint(equalTo: bottomAnchor),
        ])
        hostingView = host

        // Timer 驱动时间更新，仅刷新内嵌 HostingView
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / Self.fps, repeats: true) { [weak self] _ in
            guard let self else { return }
            let raw = Date.timeIntervalSinceReferenceDate
            self.timeHolder.time = Float(fmod(raw, Self.timeWrap))
        }
        RunLoop.current.add(timer!, forMode: .common)
    }

    override func removeFromSuperview() {
        timer?.invalidate()
        timer = nil
        super.removeFromSuperview()
    }

    deinit {
        timer?.invalidate()
    }
}

// MARK: - Observable time holder

final class TimeHolder: ObservableObject {
    @Published var time: Float = 0
}

// MARK: - 内部 Shader 视图（仅此 body 会随 time 变化刷新）

private struct CyberGridShaderView: View {
    @ObservedObject var holder: TimeHolder

    var body: some View {
        GeometryReader { geo in
            let w = Float(geo.size.width)
            let h = Float(geo.size.height)
            if w > 0 && h > 0 {
                Rectangle()
                    .fill(CyberColor.bg0)
                    .colorEffect(
                        ShaderLibrary.cyberGrid(
                            .float2(w, h),
                            .float(holder.time)
                        )
                    )
                    .drawingGroup()
            }
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }
}

#Preview {
    CyberGridBackground()
        .frame(width: 800, height: 500)
}
