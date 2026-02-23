import SwiftUI
import AppKit

struct ChatView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @FocusState private var isInputFocused: Bool
    @State private var shouldAutoScroll = true
    
    var body: some View {
        VStack(spacing: 0) {
            // 错误提示横幅
            if let errorMessage = viewModel.errorMessage {
                ErrorBannerView(message: errorMessage) {
                    viewModel.errorMessage = nil
                }
            }
            
            // 消息列表区域
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(spacing: 16) {
                        if let conversation = viewModel.currentConversation {
                            ForEach(conversation.messages) { message in
                                MessageBubble(message: message)
                                    .id(message.id)
                            }
                            
                            // 底部锚点
                            Color.clear
                                .frame(height: 1)
                                .id("bottom_anchor")
                        } else {
                            WelcomeView()
                        }
                    }
                    .padding()
                }
                .onAppear {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                        proxy.scrollTo("bottom_anchor", anchor: .bottom)
                    }
                }
                .onChange(of: viewModel.currentConversation?.messages.count) { _, _ in
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                        withAnimation(.easeOut(duration: 0.15)) {
                            proxy.scrollTo("bottom_anchor", anchor: .bottom)
                        }
                    }
                }
                .onChange(of: viewModel.currentConversation?.messages.last?.isStreaming) { oldValue, newValue in
                    if oldValue == true && newValue == false {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                            withAnimation(.easeOut(duration: 0.2)) {
                                proxy.scrollTo("bottom_anchor", anchor: .bottom)
                            }
                        }
                    }
                }
            }
            
            Divider()
            
            // 输入区域
            InputBar()
        }
        .background(Color(NSColor.textBackgroundColor))
    }
}

#Preview {
    ChatView()
        .environmentObject(AgentViewModel())
}
