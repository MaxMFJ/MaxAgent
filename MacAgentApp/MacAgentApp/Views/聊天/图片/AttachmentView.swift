import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct AttachmentView: View {
    let attachment: MessageAttachment
    @State private var isDownloading = false
    @State private var downloadDone = false
    @State private var downloadError: String?
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            switch attachment.type {
            case .base64Image:
                Base64ImageView(
                    base64String: attachment.data,
                    mimeType: attachment.mimeType ?? "image/png"
                )
            case .localFile:
                LocalFileImageView(filePath: attachment.data)
            case .url:
                VStack(alignment: .leading, spacing: 8) {
                    AsyncImageView(url: attachment.data, altText: attachment.fileName ?? "")
                    fileDownloadBar
                }
            }
        }
    }
    
    @ViewBuilder
    private var fileDownloadBar: some View {
        HStack(spacing: 8) {
            if let err = downloadError {
                Text(err)
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(.red)
            } else if downloadDone {
                HStack(spacing: 4) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                    Text("已保存")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                }
            } else {
                Button(action: downloadFile) {
                    HStack(spacing: 4) {
                        if isDownloading {
                            ProgressView()
                                .scaleEffect(0.6)
                        } else {
                            Image(systemName: "arrow.down.circle")
                        }
                        Text(isDownloading ? "下载中…" : "下载文件")
                            .font(CyberFont.body(size: 11))
                    }
                    .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .disabled(isDownloading)
            }
            Spacer()
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
    }
    
    private func downloadFile() {
        guard attachment.type == .url, let url = URL(string: attachment.data) else { return }
        isDownloading = true
        downloadError = nil
        let suggestedName = attachment.fileName ?? (url.lastPathComponent.isEmpty ? "download" : url.lastPathComponent)
        URLSession.shared.dataTask(with: url) { data, response, error in
            DispatchQueue.main.async {
                isDownloading = false
                if let error = error {
                    downloadError = error.localizedDescription
                    return
                }
                guard let data = data else {
                    downloadError = "无数据"
                    return
                }
                let panel = NSSavePanel()
                panel.nameFieldStringValue = suggestedName
                panel.allowedContentTypes = [UTType.data]
                panel.canCreateDirectories = true
                if panel.runModal() == .OK, let dest = panel.url {
                    do {
                        try data.write(to: dest)
                        downloadDone = true
                    } catch {
                        downloadError = error.localizedDescription
                    }
                }
            }
        }.resume()
    }
}
