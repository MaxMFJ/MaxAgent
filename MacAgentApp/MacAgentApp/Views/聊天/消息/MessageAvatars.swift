import SwiftUI

struct UserAvatar: View {
    var body: some View {
        Circle()
            .fill(Color.blue)
            .frame(width: 36, height: 36)
            .overlay(
                Image(systemName: "person.fill")
                    .foregroundColor(.white)
            )
    }
}

struct AssistantAvatar: View {
    var body: some View {
        Circle()
            .fill(LinearGradient(
                colors: [.purple, .blue],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ))
            .frame(width: 36, height: 36)
            .overlay(
                Image(systemName: "sparkles")
                    .foregroundColor(.white)
            )
    }
}
