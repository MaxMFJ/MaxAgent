import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @Environment(\.dismiss) var dismiss
    @State private var selectedTab = 0

    private struct NavItem {
        let title: String
        let icon: String
        let index: Int
    }

    private let navItems: [NavItem] = [
        NavItem(title: "服务",   icon: "server.rack",                        index: 0),
        NavItem(title: "远程",   icon: "antenna.radiowaves.left.and.right",  index: 1),
        NavItem(title: "模型",   icon: "cpu",                                index: 2),
        NavItem(title: "通用",   icon: "gear",                               index: 3),
        NavItem(title: "邮件",   icon: "envelope",                           index: 4),
        NavItem(title: "工具",   icon: "wrench.and.screwdriver",             index: 5),
        NavItem(title: "权限",   icon: "lock.shield",                        index: 6),
        NavItem(title: "关于",   icon: "info.circle",                        index: 7),
        NavItem(title: "MCP",    icon: "network",                            index: 8),
        NavItem(title: "功能开关", icon: "slider.horizontal.3",              index: 9),
        NavItem(title: "审计",   icon: "doc.text.magnifyingglass",           index: 10),
        NavItem(title: "Context", icon: "chart.bar.xaxis",                  index: 11),
        NavItem(title: "Chow Duck", icon: "bird",                           index: 12),
    ]

    var body: some View {
        VStack(spacing: 0) {
            // 顶部标题栏
            HStack {
                Image(systemName: "gearshape.2.fill")
                    .font(.system(size: 16))
                    .foregroundColor(CyberColor.cyan)
                Text("设置")
                    .font(CyberFont.body(size: 15, weight: .semibold))
                    .foregroundColor(CyberColor.cyan)
                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(CyberColor.bg1)

            Rectangle().fill(CyberColor.cyan.opacity(0.2)).frame(height: 1)

            HStack(spacing: 0) {
                // 左侧垂直导航栏
                VStack(spacing: 0) {
                    ScrollView {
                        VStack(spacing: 2) {
                            ForEach(navItems, id: \.index) { item in
                                SettingsSidebarRow(
                                    title: item.title,
                                    icon: item.icon,
                                    isSelected: selectedTab == item.index
                                ) {
                                    selectedTab = item.index
                                }
                            }
                        }
                        .padding(.vertical, 8)
                    }
                    Spacer(minLength: 0)
                }
                .frame(width: 150)
                .background(CyberColor.bg1)

                Rectangle().fill(CyberColor.cyan.opacity(0.2)).frame(width: 1)

                // 内容区域
                Group {
                    switch selectedTab {
                    case 0:
                        ServiceManagerView()
                    case 1:
                        TunnelView()
                    case 2:
                        ScrollView {
                            ModelSettingsContent(onSave: closeSettings)
                                .padding(20)
                                .frame(minWidth: 580)
                        }
                    case 3:
                        ScrollView {
                            GeneralSettingsContent()
                                .padding(20)
                        }
                    case 4:
                        ScrollView {
                            MailSettingsContent()
                                .padding(20)
                                .frame(minWidth: 580)
                        }
                    case 5:
                        ScrollView {
                            ToolSettingsContent()
                                .padding(20)
                        }
                    case 6:
                        ScrollView {
                            PermissionSettingsContent()
                        }
                    case 7:
                        ScrollView {
                            AboutContent()
                                .padding(20)
                        }
                    case 8:
                        ScrollView {
                            MCPSettingsContent()
                                .padding(20)
                                .frame(minWidth: 580)
                        }
                    case 9:
                        ScrollView {
                            FeatureFlagsSettingsContent()
                                .padding(20)
                        }
                    case 10:
                        AuditLogView()
                    case 11:
                        ContextVisualizationView()
                    case 12:
                        ScrollView {
                            DuckSettingsContent()
                                .padding(20)
                        }
                    default:
                        ServiceManagerView()
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            Rectangle().fill(CyberColor.cyan.opacity(0.2)).frame(height: 1)

            // 固定底部按钮栏
            HStack {
                Spacer()
                Button("关闭") {
                    closeSettings()
                }
                .controlSize(.large)
            }
            .padding(16)
            .frame(maxWidth: .infinity)
            .background(CyberColor.bg1)
        }
        .frame(width: 820, height: 700)
        .background(CyberColor.bg0)
    }
    
    private func closeSettings() {
        viewModel.showSettings = false
        dismiss()
    }
}

struct SettingsSidebarRow: View {
    let title: String
    let icon: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.system(size: 15))
                    .frame(width: 20)
                Text(title)
                    .font(CyberFont.body(size: 13))
                Spacer()
            }
            .foregroundColor(isSelected ? CyberColor.cyan : CyberColor.textSecond)
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isSelected ? CyberColor.cyan.opacity(0.15) : Color.clear)
            )
            .padding(.horizontal, 8)
        }
        .buttonStyle(.plain)
    }
}

struct SettingsTabButton: View {
    let title: String
    let icon: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 6) {
                Image(systemName: icon)
                    .font(CyberFont.display(size: 20))
                Text(title)
                    .font(CyberFont.body(size: 12))
            }
            .foregroundColor(isSelected ? CyberColor.cyan : CyberColor.textSecond)
            .frame(width: 70, height: 50)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isSelected ? CyberColor.cyan.opacity(0.15) : Color.clear)
            )
        }
        .buttonStyle(.plain)
    }
}

struct GeneralSettingsContent: View {
    @EnvironmentObject var viewModel: AgentViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // 使用 LangChain 进行对话
            VStack(alignment: .leading, spacing: 8) {
                Text("对话引擎")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                // LangChain 说明：是什么、能提升什么能力
                VStack(alignment: .leading, spacing: 6) {
                    Text("LangChain 是什么？")
                        .font(CyberFont.body(size: 13))
                        .fontWeight(.medium)
                    Text("LangChain 是业界常用的 AI 应用编排框架，提供统一的 Runnable 接口、LCEL 链式组合和标准 Agent 循环。开启后，对话将使用 LangChain 的 Agent 执行，与 Chow Duck 原生引擎并存、可随时切换。")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("能提升什么能力？")
                        .font(CyberFont.body(size: 13))
                        .fontWeight(.medium)
                        .padding(.top, 4)
                    Text("• 可观测性：便于接入 LangSmith / OpenTelemetry 做端到端追踪与调试\n• 工具链：工具以 Runnable 形式参与链式调用，支持统一重试与中间件\n• 标准 Agent 循环：与社区生态一致，便于扩展人工审核、多步推理等节点\n• 与现有能力兼容：仍使用同一套 LLM、工具与上下文，仅执行路径不同")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(NSColor.controlBackgroundColor).opacity(0.6))
                .cornerRadius(6)

                Toggle(isOn: $viewModel.langchainCompat) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("使用 LangChain 进行对话")
                        if viewModel.langchainInstalled {
                            Text("已安装可选依赖，可开启或关闭。")
                                .font(CyberFont.body(size: 11))
                                .foregroundColor(.secondary)
                        } else {
                            Text("未安装 LangChain，请先点击「安装」；安装成功后将默认勾选。")
                                .font(CyberFont.body(size: 11))
                                .foregroundColor(.secondary)
                        }
                    }
                }
                .disabled(!viewModel.langchainInstalled)
                .onChange(of: viewModel.langchainCompat) { _, newValue in
                    Task {
                        await viewModel.setLangChainCompat(newValue)
                    }
                }
                if !viewModel.langchainInstalled {
                    HStack(spacing: 8) {
                        Button {
                            Task { await viewModel.installLangChainAndEnable() }
                        } label: {
                            if viewModel.isInstallingLangChain {
                                ProgressView()
                                    .scaleEffect(0.8)
                                Text("安装中…")
                            } else {
                                Text("安装")
                            }
                        }
                        .disabled(viewModel.isInstallingLangChain)
                        .buttonStyle(.borderedProminent)
                    }
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
            .alert("LangChain 依赖安装失败", isPresented: Binding(
                get: { viewModel.langchainInstallError != nil },
                set: { if !$0 { viewModel.langchainInstallError = nil } }
            )) {
                Button("确定", role: .cancel) {
                    viewModel.langchainInstallError = nil
                }
            } message: {
                if let msg = viewModel.langchainInstallError {
                    Text(msg)
                }
            }

            Divider()

            // 语音 TTS / STT
            VStack(alignment: .leading, spacing: 12) {
                Text("语音")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                Toggle(isOn: $viewModel.ttsEnabled) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("朗读助手回复 (TTS)")
                        Text("开启后，助手回复会流式朗读（按句播放）")
                            .font(CyberFont.body(size: 11))
                            .foregroundColor(.secondary)
                    }
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("语音输入 (STT)")
                        .font(CyberFont.body(size: 13))
                        .fontWeight(.medium)
                    HStack(alignment: .firstTextBaseline, spacing: 16) {
                        HStack(spacing: 4) {
                            Text("静音")
                            TextField("", value: $viewModel.sttSilenceSeconds, format: .number)
                                .textFieldStyle(.roundedBorder)
                                .frame(width: 44)
                            Text("秒后自动发送")
                                .font(CyberFont.body(size: 11))
                                .foregroundColor(.secondary)
                        }
                        HStack(spacing: 4) {
                            Text("超时")
                            TextField("", value: $viewModel.sttNoSpeechTimeoutSeconds, format: .number)
                                .textFieldStyle(.roundedBorder)
                                .frame(width: 44)
                            Text("秒未说话强制发送")
                                .font(CyberFont.body(size: 11))
                                .foregroundColor(.secondary)
                        }
                    }
                    Text("点击输入框旁麦克风开始语音输入；静音达到设定秒数自动发送，或一直未说话则超时发送。空内容不会发送。")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(NSColor.controlBackgroundColor).opacity(0.6))
                .cornerRadius(6)
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)

            Divider()

            // GitHub Token（开放技能源）
            VStack(alignment: .leading, spacing: 8) {
                Text("GitHub Token")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        SecureField("可选，用于拉取开放技能源并提高 API 限额", text: $viewModel.githubToken)
                            .textFieldStyle(.roundedBorder)
                        if viewModel.githubConfigured {
                            Text("已配置")
                                .font(CyberFont.body(size: 11))
                                .foregroundColor(.secondary)
                        }
                    }
                    Text("未配置时从 GitHub 拉取技能会受频率限制；设置后限额更高。")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                    Button("保存") {
                        Task { await viewModel.syncGitHubConfig() }
                    }
                    .buttonStyle(.borderedProminent)
                }
                .padding()
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)
            }
            
            Divider()
            
            // 连接状态
            VStack(alignment: .leading, spacing: 8) {
                Text("连接状态")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                
                HStack {
                    Circle()
                        .fill(viewModel.isConnected ? Color.green : Color.red)
                        .frame(width: 12, height: 12)
                    
                    Text(viewModel.isConnected ? "已连接到后端服务" : "未连接到后端服务")
                    
                    Spacer()
                    
                    if !viewModel.isConnected {
                        Button("重新连接") {
                            viewModel.connect()
                        }
                        .buttonStyle(.borderedProminent)
                    }
                }
                .padding()
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)
            }
            
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear {
            Task {
                await viewModel.loadBackendConfig()
                await viewModel.loadGitHubConfig()
            }
        }
    }
}

/// 远程回退/云端提供商显示名（与后端 CLOUD_PROVIDERS 一致）
private func remoteFallbackDisplayName(_ provider: String) -> String {
    switch provider.lowercased() {
    case "newapi": return "New API"
    case "deepseek": return "DeepSeek"
    case "openai": return "ChatGPT"
    case "gemini": return "Gemini"
    case "anthropic": return "Claude API"
    default: return provider
    }
}

struct ModelSettingsContent: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @State private var showApiKey = false
    var onSave: () -> Void
    
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // AI 提供商（合并到模型页，选择即对应当前使用的模型配置）
            VStack(alignment: .leading, spacing: 8) {
                Text("AI 提供商")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                Picker("", selection: $viewModel.provider) {
                    Text("DeepSeek").tag("deepseek")
                    Text("New API").tag("newapi")
                    Text("ChatGPT").tag("openai")
                    Text("Gemini").tag("gemini")
                    Text("Claude").tag("anthropic")
                    Text("Ollama").tag("ollama")
                    Text("LM Studio").tag("lmstudio")
                }
                .pickerStyle(.menu)
                .onChange(of: viewModel.provider) { _, newValue in
                    Task {
                        if newValue == "ollama" || newValue == "lmstudio" {
                            await viewModel.fetchLocalModels()
                        }
                        await viewModel.syncConfig()
                    }
                }
            }

            switch viewModel.provider {
            case "deepseek":
                deepSeekConfig
            case "newapi":
                newApiConfig
            case "openai":
                chatGPTConfig
            case "gemini":
                geminiConfig
            case "anthropic":
                claudeApiConfig
            case "ollama":
                ollamaConfig
            case "lmstudio":
                lmStudioConfig
            default:
                deepSeekConfig
            }

            // 远程回退策略：固定列出所有远程 LLM，用户显式选择“当使用远程模型时”调用哪个
            VStack(alignment: .leading, spacing: 8) {
                Text("远程回退策略")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                Text("自主任务在本地不可用时将使用远程模型，此处选择使用哪个云端提供商。")
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(.secondary)
                Picker("当使用远程模型时调用：", selection: $viewModel.remoteFallbackProvider) {
                    Text("默认 (DeepSeek)").tag("")
                    Text("New API").tag("newapi")
                    Text("DeepSeek").tag("deepseek")
                    Text("ChatGPT").tag("openai")
                    Text("Gemini").tag("gemini")
                    Text("Claude API").tag("anthropic")
                }
                .pickerStyle(.menu)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
            
            // 保存按钮
            HStack {
                Spacer()
                Button("保存并应用") {
                    Task {
                        await viewModel.syncConfig()
                        onSave()
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            }
            
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear {
            Task {
                await viewModel.loadBackendConfig()
                if viewModel.provider == "ollama" || viewModel.provider == "lmstudio" {
                    await viewModel.fetchLocalModels()
                }
            }
        }
    }
    
    // MARK: - DeepSeek 配置
    private var deepSeekConfig: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("DeepSeek 配置")
                .font(CyberFont.body(size: 14, weight: .semibold))
            
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("API Key:")
                        .frame(width: 80, alignment: .leading)
                    Group {
                        if showApiKey {
                            TextField("输入 API Key", text: $viewModel.apiKey)
                        } else {
                            SecureField("输入 API Key", text: $viewModel.apiKey)
                        }
                    }
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 280)
                    .id(showApiKey)
                    Button(action: { showApiKey.toggle() }) {
                        Image(systemName: showApiKey ? "eye.slash" : "eye")
                    }
                    .buttonStyle(.plain)
                }
                
                HStack {
                    Text("API 地址:")
                        .frame(width: 80, alignment: .leading)
                    TextField("https://api.deepseek.com", text: $viewModel.baseUrl)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 280)
                }
                
                HStack {
                    Text("模型:")
                        .frame(width: 80, alignment: .leading)
                    TextField("deepseek-chat", text: $viewModel.model)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 280)
                }
                
                Link("获取 API Key →", destination: URL(string: "https://platform.deepseek.com/")!)
                    .font(CyberFont.body(size: 11))
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
    }
    
    // MARK: - New API 配置（统一转发网关，OpenAI 兼容，按语雀文档配置）
    private var newApiConfig: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("New API 配置")
                .font(CyberFont.body(size: 14, weight: .semibold))
            Text("统一 AI 模型网关，支持 OpenAI / Claude / Gemini 等格式转发。默认使用 cc1 地址，请按文档配置 API Key 与模型。")
                .font(CyberFont.body(size: 11))
                .foregroundColor(.secondary)
            
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("API Key / Token:")
                        .frame(width: 100, alignment: .leading)
                    Group {
                        if showApiKey {
                            TextField("输入 Token", text: $viewModel.newApiKey)
                        } else {
                            SecureField("输入 Token", text: $viewModel.newApiKey)
                        }
                    }
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 280)
                    .id(showApiKey)
                    Button(action: { showApiKey.toggle() }) {
                        Image(systemName: showApiKey ? "eye.slash" : "eye")
                    }
                    .buttonStyle(.plain)
                }
                
                HStack {
                    Text("API 地址:")
                        .frame(width: 100, alignment: .leading)
                    TextField("https://cc1.newapi.ai/v1", text: $viewModel.newApiBaseUrl)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 280)
                }
                
                HStack {
                    Text("模型:")
                        .frame(width: 100, alignment: .leading)
                    TextField("如 gpt-4o、deepseek-chat 等", text: $viewModel.newApiModel)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 280)
                }
                
                Link("New API 配置说明文档（转发站通用）示例 →", destination: URL(string: "https://www.yuque.com/nicaisadasd/fwextu/ekk2q8nrf3ow4k9q")!)
                    .font(CyberFont.body(size: 11))
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
    }
    
    // MARK: - ChatGPT (OpenAI) 配置
    private var chatGPTConfig: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("ChatGPT (OpenAI) 配置")
                .font(CyberFont.body(size: 14, weight: .semibold))
            Text("使用 OpenAI 官方 API，模型如 gpt-5.2、gpt-coder 等。")
                .font(CyberFont.body(size: 11))
                .foregroundColor(.secondary)
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("API Key:")
                        .frame(width: 80, alignment: .leading)
                    Group {
                        if showApiKey {
                            TextField("输入 API Key", text: $viewModel.openaiApiKey)
                        } else {
                            SecureField("输入 API Key", text: $viewModel.openaiApiKey)
                        }
                    }
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 280)
                    .id(showApiKey)
                    Button(action: { showApiKey.toggle() }) {
                        Image(systemName: showApiKey ? "eye.slash" : "eye")
                    }
                    .buttonStyle(.plain)
                }
                HStack {
                    Text("API 地址:")
                        .frame(width: 80, alignment: .leading)
                    TextField("https://api.openai.com/v1", text: $viewModel.openaiBaseUrl)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 280)
                }
                HStack {
                    Text("模型:")
                        .frame(width: 80, alignment: .leading)
                    TextField("gpt-4o", text: $viewModel.openaiModel)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 280)
                }
                Link("OpenAI API 文档 →", destination: URL(string: "https://platform.openai.com/docs")!)
                    .font(CyberFont.body(size: 11))
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
    }
    
    // MARK: - Gemini 配置
    private var geminiConfig: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Gemini 配置")
                .font(CyberFont.body(size: 14, weight: .semibold))
            Text("Google Gemini API。若使用 OpenAI 兼容网关，请填写对应 base_url 与模型名。")
                .font(CyberFont.body(size: 11))
                .foregroundColor(.secondary)
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("API Key:")
                        .frame(width: 80, alignment: .leading)
                    Group {
                        if showApiKey {
                            TextField("输入 API Key", text: $viewModel.geminiApiKey)
                        } else {
                            SecureField("输入 API Key", text: $viewModel.geminiApiKey)
                        }
                    }
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 280)
                    .id(showApiKey)
                    Button(action: { showApiKey.toggle() }) {
                        Image(systemName: showApiKey ? "eye.slash" : "eye")
                    }
                    .buttonStyle(.plain)
                }
                HStack {
                    Text("API 地址:")
                        .frame(width: 80, alignment: .leading)
                    TextField("如 OpenAI 兼容网关或 Google 端点", text: $viewModel.geminiBaseUrl)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 280)
                }
                HStack {
                    Text("模型:")
                        .frame(width: 80, alignment: .leading)
                    TextField("如 gemini-1.5-pro、gemini-1.5-flash", text: $viewModel.geminiModel)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 280)
                }
                Link("Google AI Studio →", destination: URL(string: "https://aistudio.google.com/")!)
                    .font(CyberFont.body(size: 11))
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
    }
    
    // MARK: - Claude API 配置
    private var claudeApiConfig: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Claude API 配置")
                .font(CyberFont.body(size: 14, weight: .semibold))
            Text("Anthropic Claude API。若使用 OpenAI 兼容网关，请填写对应 base_url 与模型名。")
                .font(CyberFont.body(size: 11))
                .foregroundColor(.secondary)
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("API Key:")
                        .frame(width: 80, alignment: .leading)
                    Group {
                        if showApiKey {
                            TextField("输入 API Key", text: $viewModel.anthropicApiKey)
                        } else {
                            SecureField("输入 API Key", text: $viewModel.anthropicApiKey)
                        }
                    }
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 280)
                    .id(showApiKey)
                    Button(action: { showApiKey.toggle() }) {
                        Image(systemName: showApiKey ? "eye.slash" : "eye")
                    }
                    .buttonStyle(.plain)
                }
                HStack {
                    Text("API 地址:")
                        .frame(width: 80, alignment: .leading)
                    TextField("如 OpenAI 兼容网关或 Anthropic 端点", text: $viewModel.anthropicBaseUrl)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 280)
                }
                HStack {
                    Text("模型:")
                        .frame(width: 80, alignment: .leading)
                    TextField("如 claude-3-5-sonnet、claude-3-opus", text: $viewModel.anthropicModel)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 280)
                }
                Link("Anthropic 文档 →", destination: URL(string: "https://docs.anthropic.com/")!)
                    .font(CyberFont.body(size: 11))
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
    }
    
    // MARK: - Ollama 配置
    private var ollamaConfig: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Ollama 配置")
                .font(CyberFont.body(size: 14, weight: .semibold))
            
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("地址:")
                        .frame(width: 80, alignment: .leading)
                    TextField("http://localhost:11434/v1", text: $viewModel.ollamaUrl)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 280)
                }
                
                HStack {
                    Text("模型:")
                        .frame(width: 80, alignment: .leading)
                    
                    if viewModel.availableLocalModels.isEmpty {
                        TextField("deepseek-r1:8b", text: $viewModel.ollamaModel)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 200)
                    } else {
                        Picker("", selection: $viewModel.ollamaModel) {
                            ForEach(viewModel.availableLocalModels, id: \.self) { model in
                                Text(model).tag(model)
                            }
                        }
                        .labelsHidden()
                    }
                    
                    Button(action: {
                        Task { await viewModel.fetchLocalModels() }
                    }) {
                        if viewModel.isLoadingModels {
                            ProgressView()
                                .scaleEffect(0.6)
                        } else {
                            Image(systemName: "arrow.clockwise")
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(viewModel.isLoadingModels)
                    .help("刷新模型列表")
                }
                
                if !viewModel.availableLocalModels.isEmpty {
                    Text("已发现 \(viewModel.availableLocalModels.count) 个模型")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                }
                
                Link("Ollama 官网 →", destination: URL(string: "https://ollama.ai/")!)
                    .font(CyberFont.body(size: 11))
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
    }
    
    // MARK: - LM Studio 配置
    private var lmStudioConfig: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("LM Studio 配置")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                Spacer()
                Text("本地多模型管理")
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(.secondary)
            }
            
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("端口:")
                        .frame(width: 80, alignment: .leading)
                    TextField("1234", text: viewModel.lmStudioPortBinding)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 100)
                    Text("默认 1234，多实例时可填 1235、1236…")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                }
                HStack {
                    Text("地址:")
                        .frame(width: 80, alignment: .leading)
                    TextField("http://localhost:1234/v1", text: $viewModel.lmStudioUrl)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 280)
                }
                
                HStack {
                    Text("模型:")
                        .frame(width: 80, alignment: .leading)
                    
                    if viewModel.availableLocalModels.isEmpty {
                        TextField("选择或输入模型名称", text: $viewModel.lmStudioModel)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 200)
                    } else {
                        Picker("", selection: $viewModel.lmStudioModel) {
                            Text("选择模型...").tag("")
                            ForEach(viewModel.availableLocalModels, id: \.self) { model in
                                Text(model).tag(model)
                            }
                        }
                        .labelsHidden()
                    }
                    
                    Button(action: {
                        Task { await viewModel.fetchLocalModels() }
                    }) {
                        if viewModel.isLoadingModels {
                            ProgressView()
                                .scaleEffect(0.6)
                        } else {
                            Image(systemName: "arrow.clockwise")
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(viewModel.isLoadingModels)
                    .help("刷新模型列表")
                }
                
                if !viewModel.availableLocalModels.isEmpty {
                    Text("已发现 \(viewModel.availableLocalModels.count) 个模型")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                }
                
                Divider()
                
                VStack(alignment: .leading, spacing: 4) {
                    Text("使用说明:")
                        .font(CyberFont.body(size: 11))
                        .fontWeight(.medium)
                    Text("1. 下载并安装 LM Studio")
                    Text("2. 下载你需要的模型（如 Llama、Qwen、DeepSeek 等）")
                    Text("3. 在 LM Studio 中启动本地服务器")
                    Text("4. 点击刷新按钮获取可用模型")
                }
                .font(CyberFont.body(size: 11))
                .foregroundColor(.secondary)
                
                Link("下载 LM Studio →", destination: URL(string: "https://lmstudio.ai/")!)
                    .font(CyberFont.body(size: 11))
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
    }
}

struct ToolSettingsContent: View {
    @EnvironmentObject var viewModel: AgentViewModel
    
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("工具审批")
                .font(CyberFont.body(size: 14, weight: .semibold))
            
            Text("以下动态工具未通过签名校验，审批后将加入白名单并立即加载。")
                .font(CyberFont.body(size: 11))
                .foregroundColor(.secondary)
            
            if viewModel.pendingTools.isEmpty {
                HStack {
                    Image(systemName: "checkmark.circle")
                        .foregroundColor(.secondary)
                    Text("暂无待审批工具")
                        .foregroundColor(.secondary)
                }
                .padding()
                .frame(maxWidth: .infinity)
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(viewModel.pendingTools) { tool in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(tool.toolName)
                                    .font(CyberFont.body(size: 13))
                                    .fontWeight(.medium)
                                Text(tool.filename)
                                    .font(CyberFont.body(size: 11))
                                    .foregroundColor(.secondary)
                            }
                            Spacer()
                            HStack(spacing: 6) {
                                if viewModel.approvingToolName == tool.toolName {
                                    ProgressView()
                                        .scaleEffect(0.7)
                                }
                                Button("审批") {
                                    Task { await viewModel.approveTool(name: tool.toolName) }
                                }
                                .buttonStyle(.borderedProminent)
                                .disabled(viewModel.approvingToolName == tool.toolName)
                            }
                        }
                        .padding(12)
                        .background(Color(NSColor.controlBackgroundColor))
                        .cornerRadius(8)
                    }
                }
            }
            
            if let err = viewModel.errorMessage, !err.isEmpty {
                Text(err)
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(.red)
            }
            
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear {
            Task { await viewModel.loadPendingTools() }
        }
    }
}

struct MailSettingsContent: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @State private var showPassword = false
    @State private var saveMessage: String?
    
    private let textFieldWidth: CGFloat = 280
    
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("邮件发信配置")
                .font(CyberFont.body(size: 14, weight: .semibold))
            
            Text("通过 SMTP 系统级发送邮件，不依赖 Mail 程序。需在邮箱中开启 SMTP 并获取授权码。")
                .font(CyberFont.body(size: 11))
                .foregroundColor(.secondary)
            
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("SMTP 服务器:")
                        .frame(width: 100, alignment: .leading)
                    TextField("smtp.qq.com", text: $viewModel.smtpServer)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: textFieldWidth)
                }
                
                HStack {
                    Text("端口:")
                        .frame(width: 100, alignment: .leading)
                    TextField("465", text: $viewModel.smtpPort)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 80)
                    Text("465=SSL, 587=STARTTLS")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                }
                
                HStack {
                    Text("邮箱:")
                        .frame(width: 100, alignment: .leading)
                    TextField("your_email@qq.com", text: $viewModel.smtpUser)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: textFieldWidth)
                }
                
                HStack {
                    Text("授权码:")
                        .frame(width: 100, alignment: .leading)
                    Group {
                        if showPassword {
                            TextField("输入授权码", text: $viewModel.smtpPassword)
                        } else {
                            SecureField("输入授权码（QQ/163 等需在邮箱设置中获取）", text: $viewModel.smtpPassword)
                        }
                    }
                    .textFieldStyle(.roundedBorder)
                    .frame(width: textFieldWidth)
                    .id(showPassword)
                    Button(action: { showPassword.toggle() }) {
                        Image(systemName: showPassword ? "eye.slash" : "eye")
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
            
            if let msg = saveMessage {
                Text(msg)
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(msg.contains("失败") ? .red : .green)
            }
            
            HStack {
                Spacer()
                Button("保存并同步到后端") {
                    Task {
                        saveMessage = nil
                        await viewModel.syncSmtpConfig()
                        saveMessage = viewModel.errorMessage ?? "已保存，Agent 发信功能可直接使用"
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            }
            
            Divider()
            
            VStack(alignment: .leading, spacing: 6) {
                Text("常见邮箱:")
                    .font(CyberFont.body(size: 11))
                    .fontWeight(.medium)
                Text("QQ: smtp.qq.com:465 | 163: smtp.163.com:465 | Gmail: smtp.gmail.com:587")
                Text("需在邮箱设置中开启 SMTP 并获取授权码，非登录密码")
            }
            .font(CyberFont.body(size: 11))
            .foregroundColor(.secondary)
            
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear {
            Task { await viewModel.loadSmtpConfig() }
        }
    }
}

struct AboutContent: View {
    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            
            Image(systemName: "sparkles")
                .font(CyberFont.display(size: 50))
                .foregroundStyle(.linearGradient(
                    colors: [CyberColor.cyan, CyberColor.green],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ))
                .shadow(color: CyberColor.cyan.opacity(0.4), radius: 10)
            
            Text("Chow Duck")
                .font(CyberFont.mono(size: 32, weight: .bold))
                .foregroundColor(CyberColor.textPrimary)
            
            Text("版本 1.0.0")
                .foregroundColor(CyberColor.textSecond)
            
            Text("一个强大的 macOS AI 助手\n可以帮助你完成各种电脑操作任务")
                .multilineTextAlignment(.center)
                .foregroundColor(CyberColor.textSecond)
            
            Divider()
                .frame(width: 200)
            
            HStack(spacing: 24) {
                AboutFeature(icon: "folder", text: "文件")
                AboutFeature(icon: "terminal", text: "终端")
                AboutFeature(icon: "app.badge", text: "应用")
                AboutFeature(icon: "cpu", text: "系统")
                AboutFeature(icon: "doc.on.clipboard", text: "剪贴板")
            }
            
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }
}

struct AboutFeature: View {
    let icon: String
    let text: String
    
    var body: some View {
        VStack(spacing: 6) {
            Image(systemName: icon)
                .font(CyberFont.body(size: 18, weight: .semibold))
                .foregroundColor(CyberColor.cyan)
            Text(text)
                .font(CyberFont.body(size: 11))
                .foregroundColor(CyberColor.textSecond)
        }
    }
}

#Preview {
    SettingsView()
        .environmentObject(AgentViewModel())
}
