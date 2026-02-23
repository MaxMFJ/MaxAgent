import SwiftUI

struct HeadingView: View {
    let text: String
    let level: Int
    
    var body: some View {
        Text(text)
            .font(fontForLevel)
            .fontWeight(.bold)
            .padding(.vertical, paddingForLevel)
    }
    
    private var fontForLevel: Font {
        switch level {
        case 1: return .title
        case 2: return .title2
        case 3: return .title3
        case 4: return .headline
        default: return .subheadline
        }
    }
    
    private var paddingForLevel: CGFloat {
        switch level {
        case 1: return 8
        case 2: return 6
        case 3: return 4
        default: return 2
        }
    }
}

struct ListItemView: View {
    let text: String
    let ordered: Bool
    let index: Int
    
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text(ordered ? "\(index)." : "•")
                .foregroundColor(.secondary)
                .frame(width: 20, alignment: .trailing)
            
            InlineMarkdownText(text: text)
        }
    }
}

struct BlockquoteView: View {
    let text: String
    
    var body: some View {
        HStack(spacing: 12) {
            Rectangle()
                .fill(Color.accentColor.opacity(0.5))
                .frame(width: 4)
            
            InlineMarkdownText(text: text)
                .foregroundColor(.secondary)
        }
        .padding(.vertical, 4)
    }
}
