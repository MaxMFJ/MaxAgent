import SwiftUI
import AppKit

/// 将 content 拆分为普通文本与 thinking 块
enum ContentPart: Equatable {
    case text(String)
    case thinking(String)
}

struct ContentSplitter {
    /// 解析 content，提取 <thinking>...</thinking> 块
    static func split(_ content: String) -> [ContentPart] {
        var parts: [ContentPart] = []
        var remaining = content
        let openTag = "<thinking>"
        let closeTag = "</thinking>"
        
        while !remaining.isEmpty {
            if let openRange = remaining.range(of: openTag, options: .caseInsensitive) {
                // 开标签之前的文本
                let before = String(remaining[..<openRange.lowerBound])
                if !before.isEmpty {
                    parts.append(.text(before))
                }
                
                let afterOpen = String(remaining[openRange.upperBound...])
                if let closeRange = afterOpen.range(of: closeTag, options: .caseInsensitive) {
                    let thinkingContent = String(afterOpen[..<closeRange.lowerBound])
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    if !thinkingContent.isEmpty {
                        parts.append(.thinking(thinkingContent))
                    }
                    remaining = String(afterOpen[closeRange.upperBound...])
                } else {
                    // 未闭合，剩余全部当作 thinking 内容（流式输出中）
                    let thinkingContent = afterOpen.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !thinkingContent.isEmpty {
                        parts.append(.thinking(thinkingContent))
                    }
                    break
                }
            } else {
                if !remaining.isEmpty {
                    parts.append(.text(remaining))
                }
                break
            }
        }
        
        return parts.isEmpty ? [.text(content)] : parts
    }
}

/// 可折叠的 Thinking 块视图，类似 Cursor 的 thinking 展示
/// - 流式输出中：默认展开，用户可见思考过程
/// - 输出完成后：默认折叠，点击可展开
struct ThinkingBlockView: View {
    let thinkingContent: String
    /// 是否正在流式输出；false 时输出完成，默认折叠
    let isStreaming: Bool
    @State private var isCollapsed: Bool
    
    init(thinkingContent: String, isStreaming: Bool) {
        self.thinkingContent = thinkingContent
        self.isStreaming = isStreaming
        // 输出完成后默认折叠
        self._isCollapsed = State(initialValue: !isStreaming)
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button(action: {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isCollapsed.toggle()
                }
            }) {
                HStack(spacing: 6) {
                    Image(systemName: "brain.head.profile")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text("思考过程")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Image(systemName: isCollapsed ? "chevron.down" : "chevron.up")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(NSColor.separatorColor).opacity(0.25))
                .cornerRadius(6)
            }
            .buttonStyle(.plain)
            
            if !isCollapsed {
                Text(thinkingContent)
                    .font(.system(.caption, design: .default))
                    .foregroundColor(.secondary)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
                    .background(Color(NSColor.textBackgroundColor).opacity(0.5))
                    .cornerRadius(4)
                    .padding(.top, 4)
            }
        }
        .onChange(of: isStreaming) { _, newValue in
            // 流式结束时，自动折叠
            if !newValue && !isCollapsed {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isCollapsed = true
                }
            }
        }
    }
}
