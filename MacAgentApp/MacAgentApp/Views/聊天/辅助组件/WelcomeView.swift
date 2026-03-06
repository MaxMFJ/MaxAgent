import SwiftUI
import AppKit

struct WelcomeView: View {
    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            
            Image(systemName: "sparkles")
                .font(CyberFont.display(size: 60))
                .foregroundStyle(.linearGradient(
                    colors: [CyberColor.cyan, CyberColor.purple],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ))
                .shadow(color: CyberColor.accentGlow, radius: 12)
                .shadow(color: CyberColor.accentGlow, radius: 24)

            Text("MACOS NATIVE AI AGENT")
                .font(CyberFont.display(size: 12, weight: .medium))
                .tracking(3)
                .foregroundColor(CyberColor.cyan)
                .neonGlow(color: CyberColor.accentGlow.opacity(0.6))
            
            Text("Chow Duck")
                .font(CyberFont.display(size: 34, weight: .bold))
                .foregroundColor(.white)
                .neonGlow(color: CyberColor.accentGlow, breathe: true)
            
            Text("你的 macOS 智能助手")
                .font(CyberFont.body(size: 16))
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
                    .stroke(CyberColor.cyan.opacity(0.25), lineWidth: 0.5)
            )
            .cornerRadius(12)
            .shadow(color: CyberColor.accentGlow.opacity(0.08), radius: 16)
            
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
                .font(CyberFont.body(size: 15, weight: .semibold))
                .foregroundColor(CyberColor.cyan)
                .shadow(color: CyberColor.accentGlow.opacity(0.3), radius: 4)
                .frame(width: 32)
            
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(CyberFont.body(size: 13, weight: .medium))
                    .foregroundColor(CyberColor.textPrimary)
                Text(description)
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(CyberColor.textSecond)
            }
        }
    }
}
