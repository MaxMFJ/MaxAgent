import SwiftUI
import AppKit

struct ChatView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @FocusState private var isInputFocused: Bool
    @State private var isUserScrolling = false
    @State private var lastScrollPosition: CGFloat = 0
    @State private var scrollViewHeight: CGFloat = 0
    
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
                    Group {
                        if let conversation = viewModel.currentConversation {
                            // 使用 VStack 而非 LazyVStack，避免悬停时布局变化导致滚动跳动（SwiftUI 已知问题）
                            VStack(alignment: .leading, spacing: 16) {
                                ForEach(conversation.messages) { message in
                                    MessageBubble(message: message)
                                        .id(message.id)
                                }
                                Color.clear
                                    .frame(height: 1)
                                    .id("bottom_anchor")
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        } else {
                            WelcomeView()
                        }
                    }
                    .padding()
                }
                .scrollDismissesKeyboard(.immediately)
                .background(GeometryReader { geo in
                    Color.clear.preference(key: ScrollHeightKey.self, value: geo.size.height)
                })
                .onPreferenceChange(ScrollHeightKey.self) { height in
                    scrollViewHeight = height
                }
                .task(id: viewModel.currentConversation?.id) {
                    // 对话切换时滚动到底部（延迟以等待布局完成）
                    try? await Task.sleep(nanoseconds: 150_000_000)
                    scrollToBottom(proxy: proxy, animated: false)
                }
                .onChange(of: viewModel.shouldScrollToBottom) { _, shouldScroll in
                    if shouldScroll {
                        scrollToBottom(proxy: proxy, animated: true)
                        viewModel.shouldScrollToBottom = false
                    }
                }
                .onChange(of: viewModel.currentConversation?.messages.last?.isStreaming) { wasStreaming, isStreaming in
                    // 仅在流式结束时滚动到底部（如果用户未手动滚动）
                    if wasStreaming == true && isStreaming == false && !isUserScrolling {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                            scrollToBottom(proxy: proxy, animated: true)
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
    
    /// 滚动到底部，仅在未被用户手动滚动时生效
    private func scrollToBottom(proxy: ScrollViewProxy, animated: Bool) {
        guard !isUserScrolling else { return }
        if animated {
            withAnimation(.easeOut(duration: 0.2)) {
                proxy.scrollTo("bottom_anchor", anchor: .bottom)
            }
        } else {
            proxy.scrollTo("bottom_anchor", anchor: .bottom)
        }
        // 滚动后短暂重置用户滚动标记（延迟以避免立即触发）
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            isUserScrolling = false
        }
    }
}

private struct ScrollHeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

#Preview {
    ChatView()
        .environmentObject(AgentViewModel())
}
