import SwiftUI
import AppKit
import UniformTypeIdentifiers

/// 文件下载视图：在聊天消息中显示可下载的文件路径
/// 支持本地打开(Finder)和远程下载(通过后端 /files/download API)
struct FileDownloadView: View {
    let filePath: String
    
    @State private var fileInfo: FileInfoData?
    @State private var isLoading = true
    @State private var isHovering = false
    @State private var isDownloading = false
    @State private var downloadProgress: String?
    @State private var downloadError: String?
    @State private var downloadSuccess = false
    
    private var baseURL: String {
        "http://127.0.0.1:\(PortConfiguration.shared.backendPort)"
    }
    
    var body: some View {
        HStack(spacing: 12) {
            // 文件图标
            fileIcon
            
            // 文件信息
            VStack(alignment: .leading, spacing: 2) {
                Text(fileInfo?.name ?? fileName)
                    .font(CyberFont.mono(size: 14))
                    .fontWeight(.medium)
                    .foregroundColor(CyberColor.textPrimary)
                    .lineLimit(1)
                
                HStack(spacing: 8) {
                    if let info = fileInfo {
                        Text(info.sizeFormatted)
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(CyberColor.textSecond)
                        
                        Text("·")
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(CyberColor.textSecond)
                        
                        Text(info.extension.isEmpty ? "文件" : info.extension.uppercased())
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(CyberColor.cyan.opacity(0.8))
                    } else if isLoading {
                        Text("加载中...")
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(CyberColor.textSecond)
                    }
                    
                    Text(filePath)
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(CyberColor.textSecond.opacity(0.6))
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }
            
            Spacer()
            
            // 操作按钮
            actionButtons
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(CyberColor.bg1)
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(
                            isHovering ? CyberColor.cyan.opacity(0.4) : CyberColor.cyan.opacity(0.15),
                            lineWidth: 1
                        )
                )
        )
        .shadow(color: isHovering ? CyberColor.cyan.opacity(0.15) : .clear, radius: 8)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.15)) {
                isHovering = hovering
            }
        }
        .onAppear {
            loadFileInfo()
        }
        .contextMenu {
            Button {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(filePath, forType: .string)
            } label: {
                Label("复制路径", systemImage: "doc.on.doc")
            }
            
            Button {
                openInFinder()
            } label: {
                Label("在 Finder 中显示", systemImage: "folder")
            }
            
            Divider()
            
            Button {
                saveToDownloads()
            } label: {
                Label("保存到下载文件夹", systemImage: "square.and.arrow.down")
            }
        }
    }
    
    // MARK: - 子视图
    
    private var fileIcon: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 8)
                .fill(iconBackground)
                .frame(width: 40, height: 40)
            
            Image(systemName: iconName)
                .font(CyberFont.display(size: 18))
                .foregroundColor(iconColor)
        }
    }
    
    @ViewBuilder
    private var actionButtons: some View {
        if let error = downloadError {
            HStack(spacing: 4) {
                Image(systemName: "exclamationmark.triangle")
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(CyberColor.red)
                Text(error)
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(CyberColor.red)
            }
        } else if downloadSuccess {
            HStack(spacing: 4) {
                Image(systemName: "checkmark.circle.fill")
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(CyberColor.green)
                Text("已保存")
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(CyberColor.green)
            }
        } else {
            HStack(spacing: 8) {
                // 在 Finder 中打开
                Button(action: openInFinder) {
                    Image(systemName: "folder")
                        .font(CyberFont.body(size: 14))
                        .foregroundColor(CyberColor.textSecond)
                        .frame(width: 28, height: 28)
                        .background(CyberColor.bg2)
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)
                .help("在 Finder 中显示")
                
                // 下载/保存
                Button(action: saveToDownloads) {
                    if isDownloading {
                        ProgressView()
                            .scaleEffect(0.6)
                            .frame(width: 28, height: 28)
                    } else {
                        Image(systemName: "square.and.arrow.down")
                            .font(CyberFont.body(size: 14))
                            .foregroundColor(CyberColor.cyan)
                            .frame(width: 28, height: 28)
                            .background(CyberColor.cyan.opacity(0.15))
                            .cornerRadius(6)
                    }
                }
                .buttonStyle(.plain)
                .help("保存到下载文件夹")
                .disabled(isDownloading)
            }
        }
    }
    
    // MARK: - 文件信息
    
    private var fileName: String {
        (filePath as NSString).lastPathComponent
    }
    
    private var fileExtension: String {
        (filePath as NSString).pathExtension.lowercased()
    }
    
    private var iconName: String {
        fileInfo?.icon ?? defaultIconName
    }
    
    private var defaultIconName: String {
        switch fileExtension {
        case "pdf": return "doc.fill"
        case "doc", "docx": return "doc.fill"
        case "txt", "md", "log": return "doc.text"
        case "xls", "xlsx", "csv": return "tablecells"
        case "ppt", "pptx", "key": return "play.rectangle"
        case "zip", "tar", "gz", "rar", "7z": return "doc.zipper"
        case "py", "js", "ts", "swift", "java", "c", "cpp", "h",
             "html", "css", "json", "xml", "yaml", "yml":
            return "chevron.left.forwardslash.chevron.right"
        case "sh": return "terminal"
        case "mp3", "wav", "aac", "m4a": return "music.note"
        case "mp4", "mov", "avi", "mkv": return "film"
        case "dmg": return "externaldrive"
        case "app": return "app"
        default: return "doc"
        }
    }
    
    private var iconColor: Color {
        switch fileExtension {
        case "pdf": return .red
        case "doc", "docx": return .blue
        case "xls", "xlsx", "csv": return .green
        case "ppt", "pptx", "key": return .orange
        case "zip", "tar", "gz", "rar", "7z": return .yellow
        case "py": return Color(red: 0.2, green: 0.6, blue: 1.0)
        case "js", "ts": return .yellow
        case "swift": return .orange
        case "mp3", "wav", "aac", "m4a": return .pink
        case "mp4", "mov", "avi", "mkv": return .purple
        default: return CyberColor.cyan
        }
    }
    
    private var iconBackground: Color {
        iconColor.opacity(0.15)
    }
    
    // MARK: - 操作
    
    private func loadFileInfo() {
        guard let encoded = filePath.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "\(baseURL)/files/info?path=\(encoded)") else {
            isLoading = false
            return
        }
        
        Task {
            do {
                let (data, _) = try await URLSession.shared.data(from: url)
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    await MainActor.run {
                        fileInfo = FileInfoData(
                            name: json["name"] as? String ?? fileName,
                            sizeFormatted: json["size_formatted"] as? String ?? "-",
                            extension: json["extension"] as? String ?? fileExtension,
                            mimeType: json["mime_type"] as? String ?? "application/octet-stream",
                            icon: json["icon"] as? String ?? defaultIconName,
                            isDirectory: json["is_directory"] as? Bool ?? false
                        )
                        isLoading = false
                    }
                }
            } catch {
                await MainActor.run {
                    isLoading = false
                }
            }
        }
    }

    private func openInFinder() {
        let url = URL(fileURLWithPath: filePath)
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }
    
    private func saveToDownloads() {
        isDownloading = true
        downloadError = nil
        downloadSuccess = false
        
        // Mac 端：直接复制到下载目录
        let downloadsDir = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first!
        let destURL = downloadsDir.appendingPathComponent(fileName)
        
        Task {
            do {
                let sourceURL = URL(fileURLWithPath: filePath)
                
                // 如果本地文件存在，直接复制
                if FileManager.default.fileExists(atPath: filePath) {
                    // 如果目标已存在，添加时间戳避免冲突
                    var finalDest = destURL
                    if FileManager.default.fileExists(atPath: finalDest.path) {
                        let stem = (fileName as NSString).deletingPathExtension
                        let ext = (fileName as NSString).pathExtension
                        let timestamp = Int(Date().timeIntervalSince1970)
                        let newName = ext.isEmpty ? "\(stem)_\(timestamp)" : "\(stem)_\(timestamp).\(ext)"
                        finalDest = downloadsDir.appendingPathComponent(newName)
                    }
                    
                    try FileManager.default.copyItem(at: sourceURL, to: finalDest)
                    
                    await MainActor.run {
                        isDownloading = false
                        downloadSuccess = true
                        // 3秒后重置状态
                        DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                            downloadSuccess = false
                        }
                    }
                } else {
                    // 本地不存在，通过 API 下载（远程场景）
                    try await downloadFromAPI(to: downloadsDir)
                }
            } catch {
                await MainActor.run {
                    isDownloading = false
                    downloadError = "保存失败"
                    DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                        downloadError = nil
                    }
                }
            }
        }
    }
    
    private func downloadFromAPI(to directory: URL) async throws {
        guard let encoded = filePath.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "\(baseURL)/files/download?path=\(encoded)") else {
            throw URLError(.badURL)
        }
        
        let (data, response) = try await URLSession.shared.data(from: url)
        
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        
        var finalDest = directory.appendingPathComponent(fileName)
        if FileManager.default.fileExists(atPath: finalDest.path) {
            let stem = (fileName as NSString).deletingPathExtension
            let ext = (fileName as NSString).pathExtension
            let timestamp = Int(Date().timeIntervalSince1970)
            let newName = ext.isEmpty ? "\(stem)_\(timestamp)" : "\(stem)_\(timestamp).\(ext)"
            finalDest = directory.appendingPathComponent(newName)
        }
        
        try data.write(to: finalDest)
        
        await MainActor.run {
            isDownloading = false
            downloadSuccess = true
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                downloadSuccess = false
            }
        }
    }
}

// MARK: - 数据模型

private struct FileInfoData {
    let name: String
    let sizeFormatted: String
    let `extension`: String
    let mimeType: String
    let icon: String
    let isDirectory: Bool
}

// MARK: - 预览

#Preview {
    VStack(spacing: 16) {
        FileDownloadView(filePath: "/Users/test/Documents/report.pdf")
        FileDownloadView(filePath: "/Users/test/Desktop/data.csv")
        FileDownloadView(filePath: "/tmp/output.log")
    }
    .padding()
    .background(CyberColor.bg0)
}
