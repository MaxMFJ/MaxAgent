import SwiftUI
import AppKit

struct CodeBlockView: View {
    let code: String
    let language: String?
    @State private var isCopied = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(language ?? "code")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                Spacer()
                
                Button(action: copyCode) {
                    HStack(spacing: 4) {
                        Image(systemName: isCopied ? "checkmark" : "doc.on.doc")
                        Text(isCopied ? "已复制" : "复制")
                    }
                    .font(.caption)
                    .foregroundColor(isCopied ? .green : .secondary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Color(NSColor.separatorColor).opacity(0.3))
            
            ScrollView(.horizontal, showsIndicators: false) {
                Text(code)
                    .font(.system(.body, design: .monospaced))
                    .foregroundColor(codeTextColor)
                    .textSelection(.enabled)
                    .padding(12)
            }
        }
        .background(codeBackgroundColor)
        .cornerRadius(8)
    }
    
    private var codeBackgroundColor: Color {
        Color(NSColor.textBackgroundColor).opacity(0.5)
    }
    
    private var codeTextColor: Color {
        Color(NSColor.textColor)
    }
    
    private func copyCode() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(code, forType: .string)
        
        withAnimation {
            isCopied = true
        }
        
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            withAnimation {
                isCopied = false
            }
        }
    }
}

struct InlineCodeView: View {
    let code: String
    
    var body: some View {
        Text(code)
            .font(.system(.body, design: .monospaced))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Color(NSColor.separatorColor).opacity(0.3))
            .cornerRadius(4)
    }
}

struct ClickableLink: View {
    let text: String
    let url: String
    @State private var isHovering = false
    
    var body: some View {
        Button(action: openLink) {
            Text(text)
                .foregroundColor(.accentColor)
                .underline(isHovering)
                .lineLimit(nil)
                .fixedSize(horizontal: false, vertical: true)
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            isHovering = hovering
            if hovering {
                NSCursor.pointingHand.push()
            } else {
                NSCursor.pop()
            }
        }
        .help(url)
    }
    
    private func openLink() {
        if let linkUrl = URL(string: url) {
            NSWorkspace.shared.open(linkUrl)
        }
    }
}
