import SwiftUI
import AppKit

struct AsyncImageView: View {
    let url: String
    let altText: String
    @State private var image: NSImage?
    @State private var isLoading = true
    @State private var loadError = false
    
    var body: some View {
        Group {
            if let image = image {
                ImageDisplayView(image: image, source: url)
            } else if isLoading {
                HStack {
                    ProgressView()
                        .scaleEffect(0.8)
                    Text("加载图片...")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                }
                .padding()
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)
            } else if loadError {
                HStack {
                    Image(systemName: "photo")
                        .foregroundColor(.secondary)
                    Text(altText.isEmpty ? "图片加载失败" : altText)
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                }
                .padding()
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)
            }
        }
        .onAppear {
            loadImage()
        }
    }
    
    private func loadImage() {
        guard let imageUrl = URL(string: url) else {
            loadError = true
            isLoading = false
            return
        }
        
        URLSession.shared.dataTask(with: imageUrl) { data, response, error in
            DispatchQueue.main.async {
                isLoading = false
                
                if let data = data, let nsImage = NSImage(data: data) {
                    self.image = nsImage
                } else {
                    loadError = true
                }
            }
        }.resume()
    }
}
