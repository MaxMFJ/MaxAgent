import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct ImageDisplayView: View {
    let image: NSImage
    let source: String
    @State private var isHovering = false
    @State private var showFullScreen = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Image(nsImage: image)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(maxWidth: 400, maxHeight: 300)
                .cornerRadius(8)
                .shadow(color: .black.opacity(0.1), radius: 4, x: 0, y: 2)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.gray.opacity(0.2), lineWidth: 1)
                )
                .onHover { hovering in
                    isHovering = hovering
                }
                .overlay(alignment: .topTrailing) {
                    if isHovering {
                        HStack(spacing: 4) {
                            Button(action: copyImage) {
                                Image(systemName: "doc.on.doc")
                                    .font(.caption)
                            }
                            .buttonStyle(.plain)
                            .help("复制图片")
                            
                            Button(action: saveImage) {
                                Image(systemName: "square.and.arrow.down")
                                    .font(.caption)
                            }
                            .buttonStyle(.plain)
                            .help("保存图片")
                            
                            Button(action: { showFullScreen = true }) {
                                Image(systemName: "arrow.up.left.and.arrow.down.right")
                                    .font(.caption)
                            }
                            .buttonStyle(.plain)
                            .help("全屏查看")
                        }
                        .padding(6)
                        .background(.ultraThinMaterial)
                        .cornerRadius(6)
                        .padding(6)
                    }
                }
                .onTapGesture(count: 2) {
                    showFullScreen = true
                }
            
            HStack {
                Image(systemName: "photo")
                    .font(.caption2)
                Text("\(Int(image.size.width)) × \(Int(image.size.height))")
                    .font(.caption2)
            }
            .foregroundColor(.secondary)
        }
        .sheet(isPresented: $showFullScreen) {
            FullScreenImageView(image: image)
        }
    }
    
    private func copyImage() {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.writeObjects([image])
    }
    
    private func saveImage() {
        let savePanel = NSSavePanel()
        savePanel.allowedContentTypes = [.png, .jpeg]
        savePanel.nameFieldStringValue = "screenshot.png"
        
        if savePanel.runModal() == .OK, let url = savePanel.url {
            if let tiffData = image.tiffRepresentation,
               let bitmapRep = NSBitmapImageRep(data: tiffData),
               let pngData = bitmapRep.representation(using: .png, properties: [:]) {
                try? pngData.write(to: url)
            }
        }
    }
}

struct FullScreenImageView: View {
    let image: NSImage
    @Environment(\.dismiss) var dismiss
    @State private var scale: CGFloat = 1.0
    
    var body: some View {
        ZStack {
            Color.black.opacity(0.9)
                .ignoresSafeArea()
            
            Image(nsImage: image)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .scaleEffect(scale)
                .gesture(
                    MagnificationGesture()
                        .onChanged { value in
                            scale = value
                        }
                )
                .onTapGesture(count: 2) {
                    withAnimation {
                        scale = scale > 1 ? 1 : 2
                    }
                }
            
            VStack {
                HStack {
                    Spacer()
                    Button(action: { dismiss() }) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.title)
                            .foregroundColor(.white)
                    }
                    .buttonStyle(.plain)
                    .padding()
                }
                Spacer()
            }
        }
        .frame(minWidth: 600, minHeight: 400)
    }
}
