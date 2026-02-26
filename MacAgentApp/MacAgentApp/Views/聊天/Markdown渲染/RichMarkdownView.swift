import SwiftUI

/// 优先使用「单 NSTextView」富文本：整条消息可跨段/跨代码块选择复制，链接可点击。
struct MarkdownText: View {
    let content: String
    
    var body: some View {
        UnifiedMarkdownView(content: content)
    }
}

private struct WidthPreferenceKey: PreferenceKey {
    static var defaultValue: CGFloat = 400
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

/// 段落类型：一段连续文本（用 NSTextView 渲染）或一个代码块（用可折叠 CodeBlockView 渲染）
private enum UnifiedSegment {
    case text([MarkdownElement])
    case code(code: String, language: String?)
}

/// 统一富文本 + 图片：文本段用 NSTextView（可选、可复制、链接可点），代码块用可折叠 CodeBlockView，图片单独渲染。
struct UnifiedMarkdownView: View {
    let content: String
    @State private var contentWidth: CGFloat = 400
    @State private var segmentHeights: [Int: CGFloat] = [:]
    
    /// 直接由 content 推导
    private var elements: [MarkdownElement] {
        MarkdownParser.parse(content)
    }
    
    /// 将元素切成「文本段」与「代码块」交替的列表，不含图片
    private var segments: [UnifiedSegment] {
        let nonImage = elements.filter {
            switch $0 { case .image, .base64Image, .localImage: return false; default: return true }
        }
        var out: [UnifiedSegment] = []
        var textAccum: [MarkdownElement] = []
        for el in nonImage {
            if case .codeBlock(let code, let lang) = el {
                if !textAccum.isEmpty {
                    out.append(.text(textAccum))
                    textAccum = []
                }
                out.append(.code(code: code, language: lang))
            } else {
                textAccum.append(el)
            }
        }
        if !textAccum.isEmpty { out.append(.text(textAccum)) }
        return out
    }
    
    private var imageElements: [MarkdownElement] {
        elements.filter {
            switch $0 { case .image, .base64Image, .localImage: return true; default: return false }
        }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(segments.enumerated()), id: \.offset) { index, segment in
                segmentView(index: index, segment: segment)
            }
            ForEach(Array(imageElements.enumerated()), id: \.offset) { _, element in
                renderImageElement(element)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(GeometryReader { g in Color.clear.preference(key: WidthPreferenceKey.self, value: g.size.width) })
        .onPreferenceChange(WidthPreferenceKey.self) { contentWidth = $0 }
    }
    
    @ViewBuilder
    private func segmentView(index: Int, segment: UnifiedSegment) -> some View {
        switch segment {
        case .text(let els):
            let binding = Binding<CGFloat>(
                get: { segmentHeights[index] ?? 40 },
                set: { segmentHeights[index] = $0 }
            )
            RichMessageTextView(
                attributedContent: RichMessageTextView.buildAttributedString(from: els),
                width: max(200, contentWidth),
                reportedHeight: binding
            )
            .frame(maxWidth: .infinity, alignment: .leading)
            .frame(height: max(40, binding.wrappedValue))
        case .code(let code, let lang):
            CodeBlockView(code: code, language: lang)
        }
    }
    
    @ViewBuilder
    private func renderImageElement(_ element: MarkdownElement) -> some View {
        switch element {
        case .image(let url, let alt):
            AsyncImageView(url: url, altText: alt)
        case .base64Image(let data, let mimeType):
            Base64ImageView(base64String: data, mimeType: mimeType)
        case .localImage(let path):
            LocalFileImageView(filePath: path)
        default:
            EmptyView()
        }
    }
}

struct RichMarkdownView: View {
    let content: String
    @State private var elements: [MarkdownElement] = []
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(elements.enumerated()), id: \.offset) { index, element in
                renderElement(element)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .fixedSize(horizontal: false, vertical: true)
        .onAppear {
            elements = MarkdownParser.parse(content)
        }
        .onChange(of: content) { _, newContent in
            elements = MarkdownParser.parse(newContent)
        }
    }
    
    @ViewBuilder
    private func renderElement(_ element: MarkdownElement) -> some View {
        switch element {
        case .text(let text):
            InlineMarkdownText(text: text)
            
        case .codeBlock(let code, let language):
            CodeBlockView(code: code, language: language)
            
        case .inlineCode(let code):
            InlineCodeView(code: code)
            
        case .image(let url, let alt):
            AsyncImageView(url: url, altText: alt)
            
        case .base64Image(let data, let mimeType):
            Base64ImageView(base64String: data, mimeType: mimeType)
            
        case .localImage(let path):
            LocalFileImageView(filePath: path)
            
        case .link(let text, let url):
            ClickableLink(text: text, url: url)
            
        case .heading(let text, let level):
            HeadingView(text: text, level: level)
            
        case .listItem(let text, let ordered, let index):
            ListItemView(text: text, ordered: ordered, index: index)
            
        case .blockquote(let text):
            BlockquoteView(text: text)
            
        case .horizontalRule:
            Divider()
                .padding(.vertical, 8)
        }
    }
}
