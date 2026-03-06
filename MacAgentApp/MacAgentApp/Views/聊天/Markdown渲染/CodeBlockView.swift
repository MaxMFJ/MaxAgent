import SwiftUI
import AppKit

/// 可折叠代码块：超过一定行数时默认折叠，可展开/收起。
struct CodeBlockView: View {
    let code: String
    let language: String?
    /// 折叠时显示的最大行数
    var maxLinesWhenCollapsed: Int = 10
    @State private var isCopied = false
    @State private var isCollapsed: Bool = true
    
    private var lines: [String] {
        code.components(separatedBy: "\n")
    }
    
    private var lineCount: Int {
        lines.count
    }
    
    private var shouldShowCollapseToggle: Bool {
        lineCount > maxLinesWhenCollapsed
    }
    
    private var displayedCode: String {
        if !shouldShowCollapseToggle { return code }
        if isCollapsed {
            return lines.prefix(maxLinesWhenCollapsed).joined(separator: "\n")
        }
        return code
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(language ?? "code")
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(.secondary)
                
                Spacer()
                
                HStack(spacing: 12) {
                    if shouldShowCollapseToggle {
                        Button(action: { withAnimation(.easeInOut(duration: 0.2)) { isCollapsed.toggle() } }) {
                            HStack(spacing: 4) {
                                Image(systemName: isCollapsed ? "chevron.down" : "chevron.up")
                                Text(isCollapsed ? "展开" : "收起")
                            }
                            .font(CyberFont.body(size: 11))
                            .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                    
                    Button(action: copyCode) {
                        HStack(spacing: 4) {
                            Image(systemName: isCopied ? "checkmark" : "doc.on.doc")
                            Text(isCopied ? "已复制" : "复制")
                        }
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(isCopied ? .green : .secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Color(NSColor.separatorColor).opacity(0.3))
            
            ScrollView(.horizontal, showsIndicators: false) {
                VStack(alignment: .leading, spacing: 0) {
                    Text(displayedCode)
                        .font(CyberFont.mono(size: 14))
                        .foregroundColor(codeTextColor)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    if shouldShowCollapseToggle && isCollapsed {
                        Text("… 共 \(lineCount) 行")
                            .font(CyberFont.body(size: 11))
                            .foregroundColor(.secondary)
                            .padding(.top, 4)
                    }
                }
                .padding(12)
            }
        }
        .background(codeBackgroundColor)
        .cornerRadius(8)
        .onAppear {
            isCollapsed = shouldShowCollapseToggle
        }
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
            .font(CyberFont.mono(size: 14))
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
                .padding(.vertical, 2)
                .padding(.horizontal, 2)
                .contentShape(Rectangle())
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
        let openable = url.hasPrefix("http://") || url.hasPrefix("https://") ? url : "https://\(url)"
        if let linkUrl = URL(string: openable) {
            NSWorkspace.shared.open(linkUrl)
        }
    }
}
