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

/// 统一富文本 + 图片：文本部分用 NSTextView（可选、可复制、链接可点），图片单独渲染。
struct UnifiedMarkdownView: View {
    let content: String
    @State private var elements: [MarkdownElement] = []
    @State private var contentWidth: CGFloat = 400
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            RichMessageTextView(
                attributedContent: RichMessageTextView.buildAttributedString(from: textElements),
                width: max(200, contentWidth)
            )
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(GeometryReader { g in Color.clear.preference(key: WidthPreferenceKey.self, value: g.size.width) })
            
            ForEach(Array(imageElements.enumerated()), id: \.offset) { _, element in
                renderImageElement(element)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onPreferenceChange(WidthPreferenceKey.self) { contentWidth = $0 }
        .onAppear { elements = MarkdownParser.parse(content) }
        .onChange(of: content) { _, newContent in elements = MarkdownParser.parse(newContent) }
    }
    
    private var textElements: [MarkdownElement] {
        elements.filter {
            switch $0 { case .image, .base64Image, .localImage: return false; default: return true }
        }
    }
    
    private var imageElements: [MarkdownElement] {
        elements.filter {
            switch $0 { case .image, .base64Image, .localImage: return true; default: return false }
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
