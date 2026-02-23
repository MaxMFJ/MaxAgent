import SwiftUI

struct MarkdownText: View {
    let content: String
    
    var body: some View {
        RichMarkdownView(content: content)
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
