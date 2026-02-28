import SwiftUI
import AppKit

struct WelcomeView: View {
    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            
            Image(systemName: "sparkles")
                .font(.system(size: 60))
                .foregroundStyle(.linearGradient(
                    colors: [CyberColor.cyan, CyberColor.green],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ))
                .shadow(color: CyberColor.cyan.opacity(0.4), radius: 12)
            
            Text("MacAgent")
                .font(.system(size: 34, weight: .bold, design: .monospaced))
                .foregroundColor(CyberColor.textPrimary)
            
            Text("你的 macOS 智能助手")
                .font(.title3)
                .foregroundColor(CyberColor.textSecond)
            
            VStack(alignment: .leading, spacing: 12) {
                FeatureRow(icon: "folder", title: "文件管理", description: "创建、移动、删除文件和文件夹")
                FeatureRow(icon: "terminal", title: "终端命令", description: "执行 shell 命令和脚本")
                FeatureRow(icon: "app.badge", title: "应用控制", description: "打开、关闭、切换应用程序")
                FeatureRow(icon: "cpu", title: "系统信息", description: "查看 CPU、内存、磁盘状态")
                FeatureRow(icon: "doc.on.clipboard", title: "剪贴板", description: "读取和写入剪贴板内容")
            }
            .padding()
            .background(CyberColor.bg2)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(CyberColor.cyan.opacity(0.15), lineWidth: 0.5)
            )
            .cornerRadius(12)
            
            Spacer()
        }
        .padding()
    }
}

struct FeatureRow: View {
    let icon: String
    let title: String
    let description: String
    
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundColor(CyberColor.cyan)
                .frame(width: 32)
            
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .fontWeight(.medium)
                    .foregroundColor(CyberColor.textPrimary)
                Text(description)
                    .font(.caption)
                    .foregroundColor(CyberColor.textSecond)
            }
        }
    }
}
