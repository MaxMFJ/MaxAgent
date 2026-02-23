import SwiftUI
import AppKit

struct InlineMarkdownText: View {
    let text: String
    
    var body: some View {
        if containsSpecialElements(text) {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(parseLines(text).enumerated()), id: \.offset) { _, line in
                    renderLine(line)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            Text(parseBasicMarkdown(text))
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
    
    private func containsSpecialElements(_ text: String) -> Bool {
        let patterns = [
            "\\[([^\\]]+)\\]\\(([^)]+)\\)",
            "https?://[^\\s]+",
        ]
        
        for pattern in patterns {
            if text.range(of: pattern, options: .regularExpression) != nil {
                return true
            }
        }
        return false
    }
    
    private func parseLines(_ text: String) -> [String] {
        return [text]
    }
    
    @ViewBuilder
    private func renderLine(_ line: String) -> some View {
        let parts = parseInlineParts(line)
        
        if parts.allSatisfy({ if case .text(_) = $0 { return true } else { return false } }) {
            Text(parseBasicMarkdown(line))
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        } else {
            WrappingHStack(alignment: .top, spacing: 0) {
                ForEach(Array(parts.enumerated()), id: \.offset) { _, part in
                    renderPart(part)
                }
            }
        }
    }
    
    @ViewBuilder
    private func renderPart(_ part: InlinePart) -> some View {
        switch part {
        case .text(let str):
            Text(parseBasicMarkdown(str))
                .textSelection(.enabled)
        case .code(let code):
            Text(code)
                .font(.system(.body, design: .monospaced))
                .foregroundColor(.orange)
                .padding(.horizontal, 4)
                .padding(.vertical, 1)
                .background(Color(NSColor.separatorColor).opacity(0.3))
                .cornerRadius(3)
        case .link(let title, let url):
            ClickableLink(text: title, url: url)
        case .url(let url):
            ClickableLink(text: url, url: url)
        }
    }
    
    enum InlinePart {
        case text(String)
        case code(String)
        case link(title: String, url: String)
        case url(String)
    }
    
    private func parseInlineParts(_ text: String) -> [InlinePart] {
        var parts: [InlinePart] = []
        var remaining = text
        
        let codePattern = try? NSRegularExpression(pattern: "`([^`]+)`")
        let linkPattern = try? NSRegularExpression(pattern: "\\[([^\\]]+)\\]\\(([^)]+)\\)")
        let urlPattern = try? NSRegularExpression(pattern: "https?://[^\\s]+")
        
        while !remaining.isEmpty {
            var earliestMatch: (range: Range<String.Index>, type: String, groups: [String])? = nil
            
            if let codePattern = codePattern,
               let match = codePattern.firstMatch(in: remaining, range: NSRange(remaining.startIndex..., in: remaining)),
               let range = Range(match.range, in: remaining),
               let codeRange = Range(match.range(at: 1), in: remaining) {
                if earliestMatch == nil || range.lowerBound < earliestMatch!.range.lowerBound {
                    earliestMatch = (range, "code", [String(remaining[codeRange])])
                }
            }
            
            if let linkPattern = linkPattern,
               let match = linkPattern.firstMatch(in: remaining, range: NSRange(remaining.startIndex..., in: remaining)),
               let range = Range(match.range, in: remaining),
               let titleRange = Range(match.range(at: 1), in: remaining),
               let urlRange = Range(match.range(at: 2), in: remaining) {
                if earliestMatch == nil || range.lowerBound < earliestMatch!.range.lowerBound {
                    earliestMatch = (range, "link", [String(remaining[titleRange]), String(remaining[urlRange])])
                }
            }
            
            if let urlPattern = urlPattern,
               let match = urlPattern.firstMatch(in: remaining, range: NSRange(remaining.startIndex..., in: remaining)),
               let range = Range(match.range, in: remaining) {
                if earliestMatch == nil || range.lowerBound < earliestMatch!.range.lowerBound {
                    let urlStr = String(remaining[range])
                    if !remaining.contains("](\(urlStr))") {
                        earliestMatch = (range, "url", [urlStr])
                    }
                }
            }
            
            if let match = earliestMatch {
                if match.range.lowerBound > remaining.startIndex {
                    let beforeText = String(remaining[remaining.startIndex..<match.range.lowerBound])
                    if !beforeText.isEmpty {
                        parts.append(.text(beforeText))
                    }
                }
                
                switch match.type {
                case "code":
                    parts.append(.code(match.groups[0]))
                case "link":
                    parts.append(.link(title: match.groups[0], url: match.groups[1]))
                case "url":
                    parts.append(.url(match.groups[0]))
                default:
                    break
                }
                
                remaining = String(remaining[match.range.upperBound...])
            } else {
                if !remaining.isEmpty {
                    parts.append(.text(remaining))
                }
                break
            }
        }
        
        return parts
    }
    
    private func parseBasicMarkdown(_ text: String) -> AttributedString {
        do {
            return try AttributedString(markdown: text, options: AttributedString.MarkdownParsingOptions(
                interpretedSyntax: .inlineOnlyPreservingWhitespace
            ))
        } catch {
            return AttributedString(text)
        }
    }
}

struct WrappingHStack: Layout {
    var alignment: VerticalAlignment = .center
    var spacing: CGFloat = 4
    
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = arrangeSubviews(proposal: proposal, subviews: subviews)
        return result.size
    }
    
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrangeSubviews(proposal: proposal, subviews: subviews)
        
        for (index, frame) in result.frames.enumerated() {
            subviews[index].place(
                at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                proposal: ProposedViewSize(frame.size)
            )
        }
    }
    
    private func arrangeSubviews(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, frames: [CGRect]) {
        let maxWidth = min(proposal.width ?? 500, 500)
        var frames: [CGRect] = []
        var currentX: CGFloat = 0
        var currentY: CGFloat = 0
        var lineHeight: CGFloat = 0
        var totalWidth: CGFloat = 0
        
        for subview in subviews {
            let size = subview.sizeThatFits(ProposedViewSize(width: maxWidth, height: nil))
            
            if currentX + size.width > maxWidth && currentX > 0 {
                currentX = 0
                currentY += lineHeight + spacing
                lineHeight = 0
            }
            
            frames.append(CGRect(x: currentX, y: currentY, width: size.width, height: size.height))
            
            lineHeight = max(lineHeight, size.height)
            currentX += size.width + spacing
            totalWidth = max(totalWidth, currentX - spacing)
        }
        
        let totalHeight = currentY + lineHeight
        
        return (CGSize(width: min(totalWidth, maxWidth), height: totalHeight), frames)
    }
}
