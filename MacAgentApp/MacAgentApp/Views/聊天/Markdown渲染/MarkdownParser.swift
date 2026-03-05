import Foundation

enum MarkdownElement {
    case text(String)
    case codeBlock(code: String, language: String?)
    case inlineCode(String)
    case image(url: String, alt: String)
    case base64Image(data: String, mimeType: String)
    case localImage(path: String)
    case filePath(path: String)         // 可下载的文件路径（非图片）
    case link(text: String, url: String)
    case heading(text: String, level: Int)
    case listItem(text: String, ordered: Bool, index: Int)
    case blockquote(String)
    case horizontalRule
}

struct MarkdownParser {
    
    // 图片扩展名集合
    private static let imageExtensions: Set<String> = ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "ico"]
    
    /// 从全文中智能提取所有文件路径（用于在 View 层显示下载卡片）
    /// 支持：独立行路径、代码块中路径、内联路径、反引号路径
    /// 只要是完整的绝对路径（/开头，有目录层级，有文件扩展名）就会被检测到
    static func extractFilePaths(from content: String) -> [String] {
        var paths: [String] = []
        let nsContent = content as NSString
        let fullRange = NSRange(location: 0, length: nsContent.length)
        
        // 策略1：匹配独立行的绝对路径（允许路径中有空格）
        // 例如代码块中的路径、纯路径行
        if let lineRegex = try? NSRegularExpression(
            pattern: #"(?:^|\n)\s*(/[^\n]*?/[^\n]*\.[a-zA-Z0-9]{1,10})\s*(?:\n|$)"#,
            options: []
        ) {
            for match in lineRegex.matches(in: content, options: [], range: fullRange) {
                guard match.range(at: 1).location != NSNotFound,
                      let pathRange = Range(match.range(at: 1), in: content) else { continue }
                var path = String(content[pathRange]).trimmingCharacters(in: .whitespaces)
                // 移除可能的尾部中文标点
                while let last = path.last, "。，；：！？".contains(last) { path = String(path.dropLast()) }
                if validateFilePath(path) && !paths.contains(path) {
                    paths.append(path)
                }
            }
        }
        
        // 策略2：匹配嵌入句子中的路径（不含空格）
        // 例如 "文件在 /usr/local/bin/test.sh 中"
        if let inlineRegex = try? NSRegularExpression(
            pattern: #"(/[^\s"'`\)），。！？；：\n]+/[^\s"'`\)），。！？；：\n]+\.[a-zA-Z0-9]{1,10})(?=$|\s|[，。！？；：'"`\)）\n])"#,
            options: [.anchorsMatchLines]
        ) {
            for match in inlineRegex.matches(in: content, options: [], range: fullRange) {
                guard match.range(at: 1).location != NSNotFound,
                      let pathRange = Range(match.range(at: 1), in: content) else { continue }
                let path = String(content[pathRange])
                if validateFilePath(path) && !paths.contains(path) {
                    paths.append(path)
                }
            }
        }
        
        // 策略3：匹配反引号内的路径（允许空格）
        // 例如 `/ Users/lzz/my file.pdf`
        if let backtickRegex = try? NSRegularExpression(
            pattern: #"`(/[^`\n]+/[^`\n]+\.[a-zA-Z0-9]{1,10})`"#,
            options: []
        ) {
            for match in backtickRegex.matches(in: content, options: [], range: fullRange) {
                guard match.range(at: 1).location != NSNotFound,
                      let pathRange = Range(match.range(at: 1), in: content) else { continue }
                let path = String(content[pathRange])
                if validateFilePath(path) && !paths.contains(path) {
                    paths.append(path)
                }
            }
        }
        
        return paths
    }
    
    /// 验证路径是否是有效的可下载文件路径
    private static func validateFilePath(_ path: String) -> Bool {
        // 必须以 / 开头
        guard path.hasPrefix("/") else { return false }
        // 至少有一个目录层级（/xxx/yyy.ext）
        let components = path.components(separatedBy: "/").filter { !$0.isEmpty }
        guard components.count >= 2 else { return false }
        // 必须有文件扩展名
        let ext = (path as NSString).pathExtension.lowercased()
        guard !ext.isEmpty, ext.count <= 10 else { return false }
        // 排除图片扩展名
        if imageExtensions.contains(ext) { return false }
        // 排除明显的非文件路径（如 URL path）
        if path.contains("://") { return false }
        // 排除 markdown 格式干扰
        if path.contains("](") || path.contains("![") { return false }
        return true
    }
    
    static func parse(_ content: String) -> [MarkdownElement] {
        var elements: [MarkdownElement] = []
        let lines = content.components(separatedBy: "\n")
        var i = 0
        var listIndex = 0
        
        while i < lines.count {
            let line = lines[i]
            
            // Code block
            if line.hasPrefix("```") {
                let language = String(line.dropFirst(3)).trimmingCharacters(in: .whitespaces)
                var codeLines: [String] = []
                i += 1
                
                while i < lines.count && !lines[i].hasPrefix("```") {
                    codeLines.append(lines[i])
                    i += 1
                }
                
                let code = codeLines.joined(separator: "\n")
                elements.append(.codeBlock(code: code, language: language.isEmpty ? nil : language))
                i += 1
                listIndex = 0
                continue
            }
            
            // Base64 image
            if line.hasPrefix("data:image/") && line.contains(";base64,") {
                let parts = line.components(separatedBy: ";base64,")
                if parts.count == 2 {
                    let mimeType = parts[0].replacingOccurrences(of: "data:", with: "")
                    let base64Data = parts[1]
                    elements.append(.base64Image(data: base64Data, mimeType: mimeType))
                    i += 1
                    listIndex = 0
                    continue
                }
            }
            
            // Local file path image (standalone line, no spaces)
            do {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.hasPrefix("/") &&
                   trimmed.range(of: "\\s", options: .regularExpression) == nil &&
                   trimmed.range(of: "\\.(png|jpg|jpeg|gif|webp|bmp|svg|ico)$", options: [.regularExpression, .caseInsensitive]) != nil &&
                   trimmed.components(separatedBy: "/").filter({ !$0.isEmpty }).count >= 2 {
                    elements.append(.localImage(path: trimmed))
                    i += 1
                    listIndex = 0
                    continue
                }
            }
            
            // Local file path (non-image, standalone line, no spaces)
            do {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.hasPrefix("/") &&
                   trimmed.range(of: "\\s", options: .regularExpression) == nil &&
                   trimmed.range(of: "\\.[a-zA-Z0-9]{1,10}$", options: .regularExpression) != nil &&
                   trimmed.range(of: "\\.(png|jpg|jpeg|gif|webp|bmp|svg|ico)$", options: [.regularExpression, .caseInsensitive]) == nil &&
                   trimmed.components(separatedBy: "/").filter({ !$0.isEmpty }).count >= 2 {
                    elements.append(.filePath(path: trimmed))
                    i += 1
                    listIndex = 0
                    continue
                }
            }
            
            // Image: ![alt](url)
            if let _ = line.range(of: "!\\[([^\\]]*)\\]\\(([^)]+)\\)", options: .regularExpression) {
                let pattern = try? NSRegularExpression(pattern: "!\\[([^\\]]*)\\]\\(([^)]+)\\)")
                if let match = pattern?.firstMatch(in: line, range: NSRange(line.startIndex..., in: line)),
                   let altRange = Range(match.range(at: 1), in: line),
                   let urlRange = Range(match.range(at: 2), in: line) {
                    let alt = String(line[altRange])
                    let url = String(line[urlRange])
                    
                    if url.hasPrefix("data:image/") && url.contains(";base64,") {
                        let parts = url.components(separatedBy: ";base64,")
                        if parts.count == 2 {
                            let mimeType = parts[0].replacingOccurrences(of: "data:", with: "")
                            elements.append(.base64Image(data: parts[1], mimeType: mimeType))
                        }
                    } else if url.hasPrefix("/") {
                        elements.append(.localImage(path: url))
                    } else {
                        elements.append(.image(url: url, alt: alt))
                    }
                    i += 1
                    listIndex = 0
                    continue
                }
            }
            
            // Heading
            if let headingMatch = line.range(of: "^#{1,6}\\s+", options: .regularExpression) {
                let level = line.prefix(while: { $0 == "#" }).count
                let text = String(line[headingMatch.upperBound...])
                elements.append(.heading(text: text, level: level))
                i += 1
                listIndex = 0
                continue
            }
            
            // Horizontal rule
            if line.trimmingCharacters(in: .whitespaces).range(of: "^[-*_]{3,}$", options: .regularExpression) != nil {
                elements.append(.horizontalRule)
                i += 1
                listIndex = 0
                continue
            }
            
            // Blockquote
            if line.hasPrefix(">") {
                let text = String(line.dropFirst()).trimmingCharacters(in: .whitespaces)
                elements.append(.blockquote(text))
                i += 1
                listIndex = 0
                continue
            }
            
            // Ordered list
            if let _ = line.range(of: "^\\d+\\.\\s+", options: .regularExpression) {
                let text = line.replacingOccurrences(of: "^\\d+\\.\\s+", with: "", options: .regularExpression)
                listIndex += 1
                elements.append(.listItem(text: text, ordered: true, index: listIndex))
                i += 1
                continue
            }
            
            // Unordered list
            if line.range(of: "^[-*+]\\s+", options: .regularExpression) != nil {
                let text = line.replacingOccurrences(of: "^[-*+]\\s+", with: "", options: .regularExpression)
                elements.append(.listItem(text: text, ordered: false, index: 0))
                i += 1
                listIndex = 0
                continue
            }
            
            // Standalone image URL
            if line.range(of: "^https?://.*\\.(png|jpg|jpeg|gif|webp|svg)(\\?.*)?$", options: [.regularExpression, .caseInsensitive]) != nil {
                elements.append(.image(url: line, alt: ""))
                i += 1
                listIndex = 0
                continue
            }
            
            // Regular text (with inline file path extraction)
            if !line.isEmpty {
                elements.append(.text(line))
                listIndex = 0
            }
            
            i += 1
        }
        
        return elements
    }
}
