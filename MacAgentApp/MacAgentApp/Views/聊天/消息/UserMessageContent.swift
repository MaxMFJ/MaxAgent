import SwiftUI

struct UserMessageContent: View {
    let content: String
    
    var body: some View {
        Text(content)
            .textSelection(.enabled)
            .padding(12)
            .foregroundColor(CyberColor.textPrimary)
            .background(
                LinearGradient(
                    colors: [CyberColor.purple.opacity(0.6), CyberColor.purple.opacity(0.35)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .cornerRadius(16)
            .cornerRadius(4, corners: .topRight)
            .shadow(color: CyberColor.purple.opacity(0.25), radius: 8, x: 0, y: 2)
    }
}
