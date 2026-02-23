import SwiftUI

struct UserMessageContent: View {
    let content: String
    
    var body: some View {
        Text(content)
            .textSelection(.enabled)
            .padding(12)
            .background(Color.accentColor)
            .foregroundColor(.white)
            .cornerRadius(16)
            .cornerRadius(4, corners: .topRight)
    }
}
