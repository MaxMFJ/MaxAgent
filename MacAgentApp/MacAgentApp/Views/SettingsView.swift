import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @Environment(\.dismiss) var dismiss
    @State private var selectedTab = 0
    
    var body: some View {
        VStack(spacing: 0) {
            // 固定顶部 Tab 栏
            HStack(spacing: 16) {
                SettingsTabButton(title: "服务", icon: "server.rack", isSelected: selectedTab == 0) {
                    selectedTab = 0
                }
                SettingsTabButton(title: "远程", icon: "antenna.radiowaves.left.and.right", isSelected: selectedTab == 1) {
                    selectedTab = 1
                }
                SettingsTabButton(title: "模型", icon: "cpu", isSelected: selectedTab == 2) {
                    selectedTab = 2
                }
                SettingsTabButton(title: "通用", icon: "gear", isSelected: selectedTab == 3) {
                    selectedTab = 3
                }
                SettingsTabButton(title: "关于", icon: "info.circle", isSelected: selectedTab == 4) {
                    selectedTab = 4
                }
            }
            .padding(.vertical, 16)
            .frame(maxWidth: .infinity)
            .background(Color(NSColor.windowBackgroundColor))
            
            Divider()
            
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
                    }
                case 3:
                    ScrollView {
                        GeneralSettingsContent()
                            .padding(20)
                    }
                case 4:
                    ScrollView {
                        AboutContent()
                            .padding(20)
                    }
                default:
                    ServiceManagerView()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            
            Divider()
            
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
            .background(Color(NSColor.windowBackgroundColor))
        }
        .frame(width: 650, height: 550)
        .background(Color(NSColor.controlBackgroundColor))
    }
    
    private func closeSettings() {
        viewModel.showSettings = false
        dismiss()
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
                    .font(.system(size: 20))
                Text(title)
                    .font(.system(size: 12))
            }
            .foregroundColor(isSelected ? .accentColor : .secondary)
            .frame(width: 70, height: 50)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isSelected ? Color.accentColor.opacity(0.15) : Color.clear)
            )
        }
        .buttonStyle(.plain)
    }
}

struct GeneralSettingsContent: View {
    @EnvironmentObject var viewModel: AgentViewModel
    
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // AI 提供商选择
            VStack(alignment: .leading, spacing: 8) {
                Text("AI 提供商")
                    .font(.headline)
                
                Picker("", selection: $viewModel.provider) {
                    Text("DeepSeek").tag("deepseek")
                    Text("Ollama").tag("ollama")
                    Text("LM Studio").tag("lmstudio")
                }
                .pickerStyle(.segmented)
                .onChange(of: viewModel.provider) { _, newValue in
                    Task {
                        if newValue == "ollama" || newValue == "lmstudio" {
                            await viewModel.fetchLocalModels()
                        }
                        await viewModel.syncConfig()
                    }
                }
            }
            
            Divider()
            
            // 连接状态
            VStack(alignment: .leading, spacing: 8) {
                Text("连接状态")
                    .font(.headline)
                
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
            
            Divider()
            
            // Model Selection Settings
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("智能模型选择")
                        .font(.headline)
                    
                    Spacer()
                    
                    Text("自动选择最优模型")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                VStack(alignment: .leading, spacing: 12) {
                    Toggle("启用智能模型选择", isOn: $viewModel.enableModelSelection)
                        .toggleStyle(.switch)
                    
                    Text("根据任务特征自动选择本地或远程模型，节省 Token 成本")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    Divider()
                    
                    Toggle("优先使用本地模型", isOn: $viewModel.preferLocalModel)
                        .toggleStyle(.switch)
                        .disabled(!viewModel.enableModelSelection)
                    
                    Text("当本地模型可用时，优先使用本地模型处理任务")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    Divider()
                    
                    VStack(alignment: .leading, spacing: 6) {
                        Text("模型选择规则:")
                            .font(.caption)
                            .fontWeight(.medium)
                        
                        Group {
                            HStack {
                                Image(systemName: "house.fill")
                                    .foregroundColor(.green)
                                    .frame(width: 16)
                                Text("本地模型: 敏感数据、简单操作、代码生成")
                            }
                            HStack {
                                Image(systemName: "cloud.fill")
                                    .foregroundColor(.blue)
                                    .frame(width: 16)
                                Text("远程模型: 复杂推理、知识查询、多步规划")
                            }
                        }
                        .font(.caption)
                        .foregroundColor(.secondary)
                    }
                }
                .padding()
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)
            }
            
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct ModelSettingsContent: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @State private var showApiKey = false
    var onSave: () -> Void
    
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            switch viewModel.provider {
            case "deepseek":
                deepSeekConfig
            case "ollama":
                ollamaConfig
            case "lmstudio":
                lmStudioConfig
            default:
                deepSeekConfig
            }
            
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
            if viewModel.provider == "ollama" || viewModel.provider == "lmstudio" {
                Task {
                    await viewModel.fetchLocalModels()
                }
            }
        }
    }
    
    // MARK: - DeepSeek 配置
    private var deepSeekConfig: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("DeepSeek 配置")
                .font(.headline)
            
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("API Key:")
                        .frame(width: 80, alignment: .leading)
                    
                    if showApiKey {
                        TextField("输入 API Key", text: $viewModel.apiKey)
                            .textFieldStyle(.roundedBorder)
                    } else {
                        SecureField("输入 API Key", text: $viewModel.apiKey)
                            .textFieldStyle(.roundedBorder)
                    }
                    
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
                }
                
                HStack {
                    Text("模型:")
                        .frame(width: 80, alignment: .leading)
                    TextField("deepseek-chat", text: $viewModel.model)
                        .textFieldStyle(.roundedBorder)
                }
                
                Link("获取 API Key →", destination: URL(string: "https://platform.deepseek.com/")!)
                    .font(.caption)
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
                .font(.headline)
            
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("地址:")
                        .frame(width: 80, alignment: .leading)
                    TextField("http://localhost:11434/v1", text: $viewModel.ollamaUrl)
                        .textFieldStyle(.roundedBorder)
                }
                
                HStack {
                    Text("模型:")
                        .frame(width: 80, alignment: .leading)
                    
                    if viewModel.availableLocalModels.isEmpty {
                        TextField("deepseek-r1:8b", text: $viewModel.ollamaModel)
                            .textFieldStyle(.roundedBorder)
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
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                Link("Ollama 官网 →", destination: URL(string: "https://ollama.ai/")!)
                    .font(.caption)
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
                    .font(.headline)
                Spacer()
                Text("本地多模型管理")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("地址:")
                        .frame(width: 80, alignment: .leading)
                    TextField("http://localhost:1234/v1", text: $viewModel.lmStudioUrl)
                        .textFieldStyle(.roundedBorder)
                }
                
                HStack {
                    Text("模型:")
                        .frame(width: 80, alignment: .leading)
                    
                    if viewModel.availableLocalModels.isEmpty {
                        TextField("选择或输入模型名称", text: $viewModel.lmStudioModel)
                            .textFieldStyle(.roundedBorder)
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
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                Divider()
                
                VStack(alignment: .leading, spacing: 4) {
                    Text("使用说明:")
                        .font(.caption)
                        .fontWeight(.medium)
                    Text("1. 下载并安装 LM Studio")
                    Text("2. 下载你需要的模型（如 Llama、Qwen、DeepSeek 等）")
                    Text("3. 在 LM Studio 中启动本地服务器")
                    Text("4. 点击刷新按钮获取可用模型")
                }
                .font(.caption)
                .foregroundColor(.secondary)
                
                Link("下载 LM Studio →", destination: URL(string: "https://lmstudio.ai/")!)
                    .font(.caption)
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
        }
    }
}

struct AboutContent: View {
    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            
            Image(systemName: "sparkles")
                .font(.system(size: 50))
                .foregroundStyle(.linearGradient(
                    colors: [.blue, .purple],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ))
            
            Text("MacAgent")
                .font(.largeTitle)
                .fontWeight(.bold)
            
            Text("版本 1.0.0")
                .foregroundColor(.secondary)
            
            Text("一个强大的 macOS AI 助手\n可以帮助你完成各种电脑操作任务")
                .multilineTextAlignment(.center)
                .foregroundColor(.secondary)
            
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
                .font(.title2)
                .foregroundColor(.accentColor)
            Text(text)
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}

#Preview {
    SettingsView()
        .environmentObject(AgentViewModel())
}
