import SwiftUI

struct AttachmentView: View {
    let attachment: MessageAttachment
    
    var body: some View {
        switch attachment.type {
        case .base64Image:
            Base64ImageView(
                base64String: attachment.data,
                mimeType: attachment.mimeType ?? "image/png"
            )
        case .localFile:
            LocalFileImageView(filePath: attachment.data)
        case .url:
            AsyncImageView(url: attachment.data, altText: attachment.fileName ?? "")
        }
    }
}
