import SwiftUI
import AppKit

struct Base64ImageView: View {
    let base64String: String
    let mimeType: String
    @State private var image: NSImage?
    @State private var loadError = false
    
    var body: some View {
        Group {
            if let image = image {
                ImageDisplayView(image: image, source: "base64")
            } else if loadError {
                HStack {
                    Image(systemName: "photo")
                        .foregroundColor(.secondary)
                    Text("图片解码失败")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                }
                .padding()
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)
            } else {
                ProgressView()
                    .onAppear {
                        loadBase64Image()
                    }
            }
        }
    }
    
    private func loadBase64Image() {
        var cleanBase64 = base64String
        
        if base64String.contains(",") {
            cleanBase64 = String(base64String.split(separator: ",").last ?? "")
        }
        
        guard let data = Data(base64Encoded: cleanBase64, options: .ignoreUnknownCharacters),
              let nsImage = NSImage(data: data) else {
            loadError = true
            return
        }
        
        self.image = nsImage
    }
}
