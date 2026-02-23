import Foundation

enum MarkdownElement {
    case text(String)
    case codeBlock(code: String, language: String?)
    case inlineCode(String)
    case image(url: String, alt: String)
    case base64Image(data: String, mimeType: String)
    case localImage(path: String)
    case link(text: String, url: String)
    case heading(text: String, level: Int)
    case listItem(text: String, ordered: Bool, index: Int)
    case blockquote(String)
    case horizontalRule
}

struct MarkdownParser {
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
            
            // Local file path image
            if line.hasPrefix("/") && line.range(of: "\\.(png|jpg|jpeg|gif|webp)$", options: [.regularExpression, .caseInsensitive]) != nil {
                elements.append(.localImage(path: line.trimmingCharacters(in: .whitespaces)))
                i += 1
                listIndex = 0
                continue
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
            
            // Regular text
            if !line.isEmpty {
                elements.append(.text(line))
                listIndex = 0
            }
            
            i += 1
        }
        
        return elements
    }
}
