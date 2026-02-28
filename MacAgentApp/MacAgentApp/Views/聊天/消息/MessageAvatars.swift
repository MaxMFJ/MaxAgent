import SwiftUI

struct UserAvatar: View {
    var body: some View {
        Circle()
            .fill(
                LinearGradient(
                    colors: [CyberColor.purple, CyberColor.purple.opacity(0.7)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .frame(width: 36, height: 36)
            .overlay(
                Image(systemName: "person.fill")
                    .foregroundColor(CyberColor.textPrimary)
            )
            .shadow(color: CyberColor.purple.opacity(0.3), radius: 6)
    }
}

struct AssistantAvatar: View {
    var body: some View {
        Circle()
            .fill(
                LinearGradient(
                    colors: [CyberColor.cyan, CyberColor.green.opacity(0.7)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .frame(width: 36, height: 36)
            .overlay(
                Image(systemName: "sparkles")
                    .foregroundColor(.white)
            )
            .shadow(color: CyberColor.cyan.opacity(0.3), radius: 6)
    }
}
