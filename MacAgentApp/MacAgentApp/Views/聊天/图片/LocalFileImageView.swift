import SwiftUI
import AppKit

struct LocalFileImageView: View {
    let filePath: String
    @State private var image: NSImage?
    @State private var loadError = false
    
    var body: some View {
        Group {
            if let image = image {
                ImageDisplayView(image: image, source: filePath)
            } else if loadError {
                HStack(spacing: 8) {
                    Image(systemName: "photo")
                        .foregroundColor(.secondary)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("图片加载失败")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Text(filePath)
                            .font(.caption2)
                            .foregroundColor(.secondary.opacity(0.7))
                            .lineLimit(1)
                    }
                }
                .padding()
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)
            } else {
                ProgressView()
                    .onAppear {
                        loadLocalImage()
                    }
            }
        }
    }
    
    private func loadLocalImage() {
        guard FileManager.default.fileExists(atPath: filePath),
              let nsImage = NSImage(contentsOfFile: filePath) else {
            loadError = true
            return
        }
        
        self.image = nsImage
    }
}
