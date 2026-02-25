import SwiftUI
import AppKit

/// 基于 NSTextView 的富文本消息视图：整条消息一个文本视图，支持跨段/跨代码块选择、复制，链接系统级可点击。
struct RichMessageTextView: NSViewRepresentable {
    /// 原始 markdown 字符串（当未提供 attributedContent 时用于构建）
    var content: String = ""
    /// 仅用于「仅文本元素」的预构建内容（与 content 二选一，优先使用）
    var attributedContent: NSAttributedString? = nil
    var width: CGFloat = 500
    
    private var effectiveAttributedString: NSAttributedString {
        if let attr = attributedContent { return attr }
        return RichMessageTextView.buildAttributedString(from: content)
    }
    
    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSTextView.scrollableTextView()
        scrollView.hasVerticalScroller = false
        scrollView.hasHorizontalScroller = false
        scrollView.drawsBackground = false
        scrollView.borderType = .noBorder
        scrollView.autohidesScrollers = true
        
        guard let textView = scrollView.documentView as? NSTextView else { return scrollView }
        textView.isEditable = false
        textView.isSelectable = true
        textView.drawsBackground = false
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.containerSize = NSSize(width: width, height: .greatestFiniteMagnitude)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.textContainerInset = NSSize(width: 0, height: 4)
        textView.linkTextAttributes = [
            .foregroundColor: NSColor.linkColor,
            .underlineStyle: NSUnderlineStyle.single.rawValue,
        ]
        
        textView.textStorage?.setAttributedString(effectiveAttributedString)
        
        return scrollView
    }
    
    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? NSTextView else { return }
        let attr = effectiveAttributedString
        if textView.attributedString().string != attr.string {
            textView.textStorage?.setAttributedString(attr)
        }
        textView.textContainer?.containerSize = NSSize(width: width, height: .greatestFiniteMagnitude)
    }
    
    // MARK: - Build NSAttributedString from markdown content
    
    private static let textFont = NSFont.systemFont(ofSize: NSFont.systemFontSize)
    private static let codeFont = NSFont.monospacedSystemFont(ofSize: NSFont.smallSystemFontSize, weight: .regular)
    private static let headingFonts: [NSFont] = [
        NSFont.systemFont(ofSize: 22, weight: .bold),
        NSFont.systemFont(ofSize: 18, weight: .bold),
        NSFont.systemFont(ofSize: 16, weight: .bold),
    ]
    
    /// 从完整 markdown 字符串构建（内部会 parse）
    static func buildAttributedString(from content: String) -> NSAttributedString {
        buildAttributedString(from: MarkdownParser.parse(content))
    }
    
    /// 从已解析的 Markdown 元素构建（可只传入文本类元素，图片会显示为 [图片]）
    static func buildAttributedString(from elements: [MarkdownElement]) -> NSAttributedString {
        let result = NSMutableAttributedString()
        let textColor = NSColor.labelColor
        let linkColor = NSColor.linkColor
        let codeBg = NSColor.tertiaryLabelColor.withAlphaComponent(0.2)
        let codeBlockBg = NSColor.tertiaryLabelColor.withAlphaComponent(0.15)
        
        for (index, element) in elements.enumerated() {
            if index > 0 { result.append(NSAttributedString(string: "\n")) }
            
            switch element {
            case .text(let line):
                result.append(buildInlineAttributedString(line, textColor: textColor, linkColor: linkColor, codeBg: codeBg))
            case .codeBlock(let code, _):
                let block = NSMutableAttributedString(string: code)
                block.addAttributes([
                    .font: codeFont,
                    .foregroundColor: textColor,
                    .backgroundColor: codeBlockBg,
                ], range: NSRange(location: 0, length: block.length))
                result.append(block)
            case .inlineCode(let code):
                let seg = NSMutableAttributedString(string: code)
                seg.addAttributes([
                    .font: codeFont,
                    .foregroundColor: textColor,
                    .backgroundColor: codeBg,
                ], range: NSRange(location: 0, length: seg.length))
                result.append(seg)
            case .link(let title, let url):
                let seg = NSMutableAttributedString(string: title)
                seg.addAttributes([
                    .font: textFont,
                    .foregroundColor: linkColor,
                    .link: url,
                    .underlineStyle: NSUnderlineStyle.single.rawValue,
                ], range: NSRange(location: 0, length: seg.length))
                result.append(seg)
            case .heading(let text, let level):
                let font = level <= 3 ? headingFonts[min(level - 1, 2)] : textFont
                let seg = NSMutableAttributedString(string: text)
                seg.addAttributes([.font: font, .foregroundColor: textColor], range: NSRange(location: 0, length: seg.length))
                result.append(seg)
            case .listItem(let text, let ordered, let idx):
                let prefix = ordered ? "\(idx). " : "• "
                result.append(NSAttributedString(string: prefix, attributes: [.font: textFont, .foregroundColor: textColor]))
                result.append(buildInlineAttributedString(text, textColor: textColor, linkColor: linkColor, codeBg: codeBg))
            case .blockquote(let text):
                result.append(NSAttributedString(string: "  ", attributes: [.font: textFont]))
                let seg = buildInlineAttributedString(text, textColor: NSColor.secondaryLabelColor, linkColor: linkColor, codeBg: codeBg)
                result.append(seg)
            case .horizontalRule:
                result.append(NSAttributedString(string: "――――――\n", attributes: [.font: textFont, .foregroundColor: NSColor.separatorColor]))
            case .image, .base64Image, .localImage:
                result.append(NSAttributedString(string: "[图片]", attributes: [.font: textFont, .foregroundColor: NSColor.secondaryLabelColor]))
            }
        }
        
        let fullRange = NSRange(location: 0, length: result.length)
        let para = NSMutableParagraphStyle()
        para.lineSpacing = 4
        result.addAttribute(.paragraphStyle, value: para, range: fullRange)
        result.addAttribute(.font, value: textFont, range: fullRange)
        result.fixAttributes(in: fullRange)
        return result
    }
    
    private static func buildInlineAttributedString(_ line: String, textColor: NSColor, linkColor: NSColor, codeBg: NSColor) -> NSMutableAttributedString {
        let parts = parseInlineParts(line)
        let result = NSMutableAttributedString()
        for part in parts {
            switch part {
            case .text(let str):
                result.append(NSAttributedString(string: str, attributes: [.font: textFont, .foregroundColor: textColor]))
            case .code(let code):
                let seg = NSMutableAttributedString(string: code)
                seg.addAttributes([
                    .font: codeFont,
                    .foregroundColor: textColor,
                    .backgroundColor: codeBg,
                ], range: NSRange(location: 0, length: seg.length))
                result.append(seg)
            case .link(let title, let url):
                let seg = NSMutableAttributedString(string: title)
                seg.addAttributes([
                    .font: textFont,
                    .foregroundColor: linkColor,
                    .link: url,
                    .underlineStyle: NSUnderlineStyle.single.rawValue,
                ], range: NSRange(location: 0, length: seg.length))
                result.append(seg)
            case .url(let url):
                let seg = NSMutableAttributedString(string: url)
                seg.addAttributes([
                    .font: textFont,
                    .foregroundColor: linkColor,
                    .link: url.hasPrefix("http") ? url : "https://\(url)",
                    .underlineStyle: NSUnderlineStyle.single.rawValue,
                ], range: NSRange(location: 0, length: seg.length))
                result.append(seg)
            }
        }
        return result
    }
    
    private static func parseInlineParts(_ text: String) -> [InlinePart] {
        var parts: [InlinePart] = []
        var remaining = text
        let codePattern = try? NSRegularExpression(pattern: "`([^`]+)`")
        let linkPattern = try? NSRegularExpression(pattern: "\\[([^\\]]+)\\]\\(([^)]+)\\)")
        let urlPattern = try? NSRegularExpression(pattern: "(https?://[^\\s]+)|(www\\.[a-zA-Z0-9][\\w.-]*\\.[a-zA-Z0-9\\w.-]*)")
        let urlTrailing = CharacterSet(charactersIn: "。，、．.,;:!?！？」』)】 \t\n\r")
        
        while !remaining.isEmpty {
            var earliest: (range: Range<String.Index>, type: String, groups: [String], end: String.Index)?
            
            if let re = codePattern, let m = re.firstMatch(in: remaining, range: NSRange(remaining.startIndex..., in: remaining)),
               let r = Range(m.range, in: remaining), let r1 = Range(m.range(at: 1), in: remaining) {
                earliest = (r, "code", [String(remaining[r1])], r.upperBound)
            }
            if let re = linkPattern, let m = re.firstMatch(in: remaining, range: NSRange(remaining.startIndex..., in: remaining)),
               let r = Range(m.range, in: remaining),
               let r1 = Range(m.range(at: 1), in: remaining), let r2 = Range(m.range(at: 2), in: remaining) {
                if earliest == nil || r.lowerBound < earliest!.range.lowerBound {
                    earliest = (r, "link", [String(remaining[r1]), String(remaining[r2])], r.upperBound)
                }
            }
            if let re = urlPattern, let m = re.firstMatch(in: remaining, range: NSRange(remaining.startIndex..., in: remaining)),
               let r = Range(m.range, in: remaining) {
                let urlStr = String(remaining[r])
                let trimmed = urlStr.trimmingCharacters(in: urlTrailing)
                if !trimmed.isEmpty && !remaining.contains("](\(trimmed))") {
                    let n = min(trimmed.count, remaining.distance(from: r.lowerBound, to: r.upperBound))
                    let end = remaining.index(r.lowerBound, offsetBy: n)
                    if earliest == nil || r.lowerBound < earliest!.range.lowerBound {
                        earliest = (r, "url", [trimmed], end)
                    }
                }
            }
            
            if let e = earliest {
                if e.range.lowerBound > remaining.startIndex {
                    let before = String(remaining[remaining.startIndex..<e.range.lowerBound])
                    if !before.isEmpty {
                        parts.append(.text(before))
                    }
                }
                switch e.type {
                case "code": parts.append(.code(e.groups[0]))
                case "link": parts.append(.link(title: e.groups[0], url: e.groups[1]))
                case "url": parts.append(.url(e.groups[0]))
                default: break
                }
                remaining = String(remaining[e.end...])
            } else {
                if !remaining.isEmpty { parts.append(.text(remaining)) }
                break
            }
        }
        return parts
    }
    
    private enum InlinePart {
        case text(String)
        case code(String)
        case link(title: String, url: String)
        case url(String)
    }
}
