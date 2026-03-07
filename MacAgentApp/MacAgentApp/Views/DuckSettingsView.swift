import SwiftUI

/// Chow Duck 分身管理设置页
struct DuckSettingsContent: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @ObservedObject private var eggMgr = EggModeManager.shared
    @State private var selectedTemplate: String = "general"
    @State private var eggName: String = ""
    @State private var isChowing: Bool = false
    @State private var chowPhase: ChowPhase = .idle
    @State private var chowMode: ChowMode = .egg  // egg 或 localDuck
    @State private var lastCreatedEgg: [String: Any]?
    @State private var lastCreatedLocalDuck: Bool = false
    // Egg import state
    @State private var showImportFilePicker: Bool = false
    @State private var isImporting: Bool = false
    @State private var showClearConfirm: Bool = false
    // Tab
    @State private var selectedTab: DuckTab = .chow
    // LLM 配置 sheet（用 item 确保弹窗打开时数据已就绪）
    @State private var llmConfigDuck: LLMConfigDuckItem? = nil

    private enum ChowPhase {
        case idle, eating, digesting, done
    }

    private enum ChowMode {
        case egg, localDuck
    }

    private enum DuckTab: String, CaseIterable {
        case ducks = "分身列表"
        case chow = "Chow Duck"
        case eggs = "Egg 列表"
    }

    private let duckIcons: [String: String] = [
        "crawler": "🕷️", "coder": "💻", "image": "🎨",
        "video": "🎬", "tester": "🧪", "designer": "🎯", "general": "🦆",
    ]

    /// 吃鸭子动画最少展示时长（秒），用于给后端创建配置争取时间
    private let minChowDuration: TimeInterval = 3.0

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {

            // ═══════ 导入 Egg (此设备以子 Duck 运行) ═══════
            importEggSection

            // Header + Toggle (主 Agent 功能，Duck 模式下折叠)
            if !eggMgr.isDuckMode {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Chow Duck 分身模式")
                            .font(CyberFont.body(size: 14, weight: .semibold))
                        Text("开启后可创建 Duck 分身来并行执行任务，支持本地和远程部署。")
                            .font(CyberFont.body(size: 11))
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    Toggle("", isOn: $viewModel.chowDuckEnabled)
                        .labelsHidden()
                        .toggleStyle(.switch)
                }

                if viewModel.chowDuckEnabled {
                    // Stats row
                    if !viewModel.duckStats.isEmpty {
                        let online = viewModel.duckStats["online"] as? Int ?? 0
                        let busy = viewModel.duckStats["busy"] as? Int ?? 0
                        let total = viewModel.duckStats["total"] as? Int ?? 0
                        HStack(spacing: 12) {
                            StatBadge(label: "总计", value: "\(total)", color: CyberColor.cyan)
                            StatBadge(label: "在线", value: "\(online)", color: .green)
                            StatBadge(label: "忙碌", value: "\(busy)", color: .orange)
                        }
                    }
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)

            if viewModel.chowDuckEnabled {
                // Error banner
                if let error = viewModel.duckError {
                    HStack {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.red)
                        Text(error)
                            .font(CyberFont.body(size: 11))
                            .foregroundColor(.red)
                        Spacer()
                        Button("关闭") { viewModel.duckError = nil }
                            .font(CyberFont.body(size: 11))
                    }
                    .padding(10)
                    .background(Color.red.opacity(0.1))
                    .cornerRadius(6)
                }

                // ═══════ Tab 导航 ═══════
                Picker("", selection: $selectedTab) {
                    ForEach(DuckTab.allCases, id: \.self) { tab in
                        Text(tab.rawValue).tag(tab)
                    }
                }
                .pickerStyle(.segmented)

                // ═══════ Tab 内容 ═══════
                switch selectedTab {
                case .ducks:
                    duckListTab
                case .chow:
                    chowDuckTab
                case .eggs:
                    eggListTab
                }
            }
            } // end if !isDuckMode
        }
        .fileImporter(
            isPresented: $showImportFilePicker,
            allowedContentTypes: [.json, .zip],
            allowsMultipleSelection: false
        ) { result in
            switch result {
            case .success(let urls):
                guard let url = urls.first else { return }
                isImporting = true
                Task {
                    await viewModel.eggModeManager.importConfig(from: url)
                    isImporting = false
                }
            case .failure:
                break
            }
        }
        .onAppear {
            if viewModel.chowDuckEnabled {
                Task { await viewModel.loadDuckData() }
            }
        }
        .onChange(of: viewModel.chowDuckEnabled) { _, enabled in
            if enabled {
                Task { await viewModel.loadDuckData() }
            }
        }
        .sheet(item: $llmConfigDuck) { item in
            DuckLLMConfigSheet(
                duckId: item.duckId,
                duckName: item.duckName,
                apiKey: item.apiKey,
                baseUrl: item.baseUrl,
                model: item.model,
                onSave: { apiKey, baseUrl, model in
                    Task {
                        await viewModel.updateDuckLLMConfig(duckId: item.duckId, apiKey: apiKey, baseUrl: baseUrl, model: model)
                        llmConfigDuck = nil
                    }
                },
                onDismiss: { llmConfigDuck = nil }
            )
        }
    }

    // MARK: - Import Egg Section

    @ViewBuilder
    private var importEggSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: eggMgr.isDuckMode ? "bird.fill" : "bird")
                    .foregroundColor(eggMgr.isDuckMode ? CyberColor.cyan : .secondary)
                Text(eggMgr.isDuckMode ? "子 Duck 模式（此设备作为 Duck 运行）" : "导入 Egg — 以子 Duck 身份加入工作流")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                    .foregroundColor(eggMgr.isDuckMode ? CyberColor.cyan : CyberColor.textPrimary)
                Spacer()
            }

            if eggMgr.isDuckMode, let cfg = eggMgr.config {
                // Show current duck config
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 8) {
                        Circle().fill(Color.green).frame(width: 8, height: 8)
                        Text("Duck ID: \(cfg.duckId)")
                            .font(CyberFont.body(size: 12, weight: .medium))
                        Text(cfg.duckType)
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(CyberColor.cyan)
                            .padding(.horizontal, 6).padding(.vertical, 1)
                            .background(CyberColor.cyan.opacity(0.1))
                            .cornerRadius(4)
                    }
                    Text("主工作流: \(cfg.mainAgentUrl)")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Text("端口: \(eggMgr.assignedPort)  权限: \(cfg.permissions.joined(separator: ", "))")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
                .padding(10)
                .background(CyberColor.cyan.opacity(0.06))
                .cornerRadius(6)

                HStack(spacing: 10) {
                    Button {
                        showClearConfirm = true
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "xmark.circle")
                            Text("退出 Duck 模式")
                        }
                    }
                    .buttonStyle(.bordered)
                    .foregroundColor(.red)
                    .confirmationDialog("退出 Duck 模式", isPresented: $showClearConfirm, titleVisibility: .visible) {
                        Button("确认退出", role: .destructive) {
                            eggMgr.clearConfig()
                        }
                        Button("取消", role: .cancel) {}
                    } message: {
                        Text("退出后本设备将恢复主 Agent 模式，需重启 App 生效。")
                    }
                }
            } else {
                // Not in duck mode — show import button
                Text("导入 Egg 配置文件（duck_config.json 或 Egg ZIP），本设备将以子 Duck 身份接入主工作流。")
                    .font(CyberFont.body(size: 11))
                    .foregroundColor(.secondary)

                // Success/Error banners
                if eggMgr.importSuccess {
                    HStack(spacing: 6) {
                        Image(systemName: "checkmark.circle.fill").foregroundColor(.green)
                        Text("导入成功！重启 App 后生效。")
                            .font(CyberFont.body(size: 11))
                            .foregroundColor(.green)
                    }
                    .padding(8).background(Color.green.opacity(0.1)).cornerRadius(6)
                }
                if let err = eggMgr.importError {
                    HStack(spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill").foregroundColor(.red)
                        Text(err).font(CyberFont.body(size: 11)).foregroundColor(.red)
                    }
                    .padding(8).background(Color.red.opacity(0.1)).cornerRadius(6)
                }

                HStack(spacing: 10) {
                    Button {
                        eggMgr.importError = nil
                        eggMgr.importSuccess = false
                        showImportFilePicker = true
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: isImporting ? "arrow.triangle.2.circlepath" : "tray.and.arrow.down")
                            Text(isImporting ? "导入中…" : "导入 Egg 配置")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isImporting)
                }
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(eggMgr.isDuckMode ? CyberColor.cyan.opacity(0.4) : Color.clear, lineWidth: 1)
        )
    }

    // MARK: - Tab Content

    @ViewBuilder
    private var duckListTab: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("分身列表")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                Spacer()
                Button {
                    Task { await viewModel.loadDuckData() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .disabled(viewModel.isLoadingDucks)
            }

            if viewModel.isLoadingDucks {
                ProgressView("加载中…").frame(maxWidth: .infinity).padding()
            } else if viewModel.duckList.isEmpty {
                Text("暂无 Duck 分身")
                    .font(CyberFont.body(size: 12))
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding()
            } else {
                ForEach(viewModel.duckList, id: \.self.hashableKey) { duck in
                    DuckRowView(duck: duck, onDelete: { duckId, isLocal in
                        Task {
                            if isLocal {
                                await viewModel.destroyLocalDuck(duckId: duckId)
                            } else {
                                await viewModel.removeDuck(duckId: duckId)
                            }
                        }
                    }, onStart: { duckId in
                        Task { await viewModel.startLocalDuck(duckId: duckId) }
                    }, onLLMConfig: { duckId in
                        if let duck = viewModel.duckList.first(where: { ($0["duck_id"] as? String) == duckId }) {
                            llmConfigDuck = LLMConfigDuckItem(
                                duckId: duckId,
                                duckName: duck["name"] as? String ?? duckId,
                                apiKey: duck["llm_api_key"] as? String ?? "",
                                baseUrl: duck["llm_base_url"] as? String ?? "",
                                model: duck["llm_model"] as? String ?? ""
                            )
                        }
                    })
                }
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
    }

    @ViewBuilder
    private var chowDuckTab: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("🦆 Chow Duck")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                Spacer()
            }

            // Chow animation area（强制至少 3s 展示）
            chowAnimationView

            // Template grid
            Text("选择鸭子类型")
                .font(CyberFont.body(size: 12, weight: .medium))
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                ForEach(viewModel.duckTemplates, id: \.self.hashableKey) { template in
                    let dtype = template["duck_type"] as? String ?? ""
                    let name = template["name"] as? String ?? dtype
                    let desc = template["description"] as? String ?? ""
                    let icon = template["icon"] as? String ?? duckIcons[dtype] ?? "🦆"
                    Button {
                        selectedTemplate = dtype
                    } label: {
                        HStack(alignment: .top, spacing: 8) {
                            Text(icon).font(.title2)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(name)
                                    .font(CyberFont.body(size: 12, weight: .medium))
                                    .foregroundColor(CyberColor.textPrimary)
                                Text(desc)
                                    .font(CyberFont.body(size: 10))
                                    .foregroundColor(.secondary)
                                    .lineLimit(2)
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(selectedTemplate == dtype ? CyberColor.cyan.opacity(0.1) : Color(NSColor.controlBackgroundColor).opacity(0.6))
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(selectedTemplate == dtype ? CyberColor.cyan : Color.clear, lineWidth: 1)
                        )
                        .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                }
            }

            // Egg name input（仅生成 Egg 时显示）
            HStack(spacing: 8) {
                TextField("Egg 名称（可选）", text: $eggName)
                    .textFieldStyle(.roundedBorder)
            }

            // Action buttons
            HStack(spacing: 12) {
                Button {
                    startChowEgg()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "plus.circle.fill")
                        Text("Chow Duck → 生成 Egg")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(isChowing)

                Button {
                    startChowLocalDuck()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "macwindow.badge.plus")
                        Text("创建本地 Duck")
                    }
                }
                .buttonStyle(.bordered)
                .disabled(isChowing)
            }

            // Last created egg result
            if let egg = lastCreatedEgg {
                let eggId = egg["egg_id"] as? String ?? ""
                let eggType = egg["duck_type"] as? String ?? ""
                HStack {
                    Text("🥚")
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Egg 已生成！")
                            .font(CyberFont.body(size: 12, weight: .medium))
                        Text("ID: \(eggId) · 类型: \(eggType)")
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    if let url = viewModel.eggDownloadURL(eggId: eggId) {
                        Link("下载", destination: url)
                            .font(CyberFont.body(size: 11, weight: .medium))
                    }
                }
                .padding(10)
                .background(Color.green.opacity(0.1))
                .cornerRadius(6)
            }

            // Last created local duck result
            if lastCreatedLocalDuck {
                HStack {
                    Text("🦆")
                    VStack(alignment: .leading, spacing: 2) {
                        Text("本地 Duck 已创建！")
                            .font(CyberFont.body(size: 12, weight: .medium))
                        Text("已加入分身列表，可前往「分身列表」查看")
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                }
                .padding(10)
                .background(Color.green.opacity(0.1))
                .cornerRadius(6)
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
    }

    @ViewBuilder
    private var eggListTab: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("🥚 Egg 列表")
                    .font(CyberFont.body(size: 14, weight: .semibold))
                Spacer()
                Button {
                    Task { await viewModel.loadDuckData() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
            }

            if viewModel.duckEggs.isEmpty {
                Text("暂无 Egg")
                    .font(CyberFont.body(size: 12))
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding()
            } else {
                ForEach(viewModel.duckEggs, id: \.self.hashableKey) { egg in
                    EggRowView(egg: egg, downloadURL: viewModel.eggDownloadURL(eggId: egg["egg_id"] as? String ?? "")) {
                        Task { await viewModel.deleteEgg(eggId: egg["egg_id"] as? String ?? "") }
                    }
                }
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
    }

    // MARK: - Chow Animation

    @ViewBuilder
    private var chowAnimationView: some View {
        let icon = duckIcons[selectedTemplate] ?? "🦆"
        HStack(spacing: 0) {
            Spacer()
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(CyberColor.bg1.opacity(0.5))
                    .frame(height: 80)

                HStack(spacing: 16) {
                    // Duck
                    Text(icon)
                        .font(.system(size: 36))
                        .offset(x: chowPhase == .eating ? -40 : 0)
                        .opacity(chowPhase == .digesting || chowPhase == .done ? 0 : 1)
                        .animation(.easeInOut(duration: 1.5), value: chowPhase)

                    // Mouth
                    if chowPhase == .eating {
                        Text("👄")
                            .font(.system(size: 28))
                            .transition(.scale)
                    }

                    // Gear (digesting)
                    if chowPhase == .digesting {
                        Image(systemName: "gearshape.2.fill")
                            .font(.system(size: 28))
                            .foregroundColor(CyberColor.cyan)
                            .rotationEffect(.degrees(chowPhase == .digesting ? 360 : 0))
                            .animation(.linear(duration: 1).repeatForever(autoreverses: false), value: chowPhase)
                            .transition(.scale)
                    }

                    // Result (egg or local duck)
                    if chowPhase == .done {
                        Text(chowMode == .egg ? "🥚" : "🦆")
                            .font(.system(size: 36))
                            .transition(.scale.combined(with: .opacity))
                    }
                }
            }
            Spacer()
        }
        .animation(.spring(response: 0.5), value: chowPhase)
    }

    // MARK: - Actions

    /// 生成 Egg：强制至少 3s 吃鸭子动画，给后端创建配置文件争取时间
    private func startChowEgg() {
        isChowing = true
        lastCreatedEgg = nil
        lastCreatedLocalDuck = false
        chowMode = .egg
        chowPhase = .eating

        // eating 2s → digesting 1s（共 3s  minimum）→ 调用 API → done
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            chowPhase = .digesting
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                Task {
                    let result = await viewModel.createEgg(duckType: selectedTemplate, name: eggName.isEmpty ? nil : eggName)
                    lastCreatedEgg = result
                    chowPhase = .done
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                        chowPhase = .idle
                        isChowing = false
                    }
                }
            }
        }
    }

    /// 创建本地 Duck：强制至少 3s 吃鸭子动画，给后端创建配置文件争取时间
    private func startChowLocalDuck() {
        isChowing = true
        lastCreatedEgg = nil
        lastCreatedLocalDuck = false
        chowMode = .localDuck
        chowPhase = .eating

        // eating 2s → digesting 1s（共 3s minimum）→ 调用 API → done
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            chowPhase = .digesting
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                Task {
                    await createLocalDuckFromTemplate()
                    lastCreatedLocalDuck = true
                    chowPhase = .done
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                        chowPhase = .idle
                        isChowing = false
                        Task { await viewModel.loadDuckData() }
                    }
                }
            }
        }
    }

    private func createLocalDuckFromTemplate() async {
        guard let template = viewModel.duckTemplates.first(where: { ($0["duck_type"] as? String) == selectedTemplate }) else { return }
        let name = template["name"] as? String ?? selectedTemplate
        let skills = template["skills"] as? [String] ?? []
        await viewModel.createLocalDuck(name: name, duckType: selectedTemplate, skills: skills)
    }
}

// MARK: - Subviews

private struct StatBadge: View {
    let label: String
    let value: String
    let color: Color

    var body: some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 6, height: 6)
            Text("\(label) \(value)")
                .font(CyberFont.body(size: 11))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(color.opacity(0.1))
        .cornerRadius(4)
    }
}

/// 分身 LLM 配置弹窗的数据项（Identifiable 供 sheet(item:) 使用）
private struct LLMConfigDuckItem: Identifiable {
    let id: String
    let duckId: String
    let duckName: String
    let apiKey: String
    let baseUrl: String
    let model: String

    init(duckId: String, duckName: String, apiKey: String, baseUrl: String, model: String) {
        self.id = duckId
        self.duckId = duckId
        self.duckName = duckName
        self.apiKey = apiKey
        self.baseUrl = baseUrl
        self.model = model
    }
}

private struct DuckRowView: View {
    let duck: [String: Any]
    let onDelete: (String, Bool) -> Void
    var onStart: ((String) -> Void)? = nil
    var onLLMConfig: ((String) -> Void)? = nil

    var body: some View {
        let duckId = duck["duck_id"] as? String ?? ""
        let name = duck["name"] as? String ?? "Unknown"
        let duckType = duck["duck_type"] as? String ?? ""
        let status = duck["status"] as? String ?? "offline"
        let isLocal = duck["is_local"] as? Bool ?? false
        let completed = duck["completed_tasks"] as? Int ?? 0
        let failed = duck["failed_tasks"] as? Int ?? 0
        let hostname = duck["hostname"] as? String ?? ""
        let showStartButton = isLocal && status == "offline"

        HStack(spacing: 10) {
            Circle()
                .fill(status == "online" ? Color.green : status == "busy" ? Color.orange : Color.gray)
                .frame(width: 8, height: 8)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(name)
                        .font(CyberFont.body(size: 12, weight: .medium))
                    Text(duckType)
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(CyberColor.cyan)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 1)
                        .background(CyberColor.cyan.opacity(0.1))
                        .cornerRadius(4)
                    if isLocal {
                        Text("本地")
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(.blue)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 1)
                            .background(Color.blue.opacity(0.1))
                            .cornerRadius(4)
                    }
                }
                Text("\(hostname) · 完成 \(completed) · 失败 \(failed)")
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(.secondary)
            }
            Spacer()
            if isLocal, let onLLM = onLLMConfig {
                Button {
                    onLLM(duckId)
                } label: {
                    Image(systemName: "cpu")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .help("LLM 配置")
            }
            if showStartButton, let start = onStart {
                Button {
                    start(duckId)
                } label: {
                    Text("启动")
                        .font(CyberFont.body(size: 11, weight: .medium))
                        .foregroundColor(CyberColor.cyan)
                }
                .buttonStyle(.plain)
            }
            Button {
                onDelete(duckId, isLocal)
            } label: {
                Image(systemName: "trash")
                    .font(.system(size: 12))
                    .foregroundColor(.red.opacity(0.7))
            }
            .buttonStyle(.plain)
        }
        .padding(10)
        .background(Color(NSColor.controlBackgroundColor).opacity(0.6))
        .cornerRadius(6)
    }
}

/// 分身 LLM 配置弹窗（用户手动填写 api_key、base_url、model）
private struct DuckLLMConfigSheet: View {
    let duckId: String
    let duckName: String
    let apiKey: String
    let baseUrl: String
    let model: String
    let onSave: (String, String, String) -> Void
    let onDismiss: () -> Void

    @State private var editApiKey: String = ""
    @State private var editBaseUrl: String = ""
    @State private var editModel: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("分身 LLM 配置")
                    .font(CyberFont.body(size: 16, weight: .semibold))
                Spacer()
                Button("关闭") { onDismiss() }
                    .buttonStyle(.plain)
            }
            Text("为 \(duckName) 配置独立 LLM，使分身更有效运用大模型完成专项任务。")
                .font(CyberFont.body(size: 12))
                .foregroundColor(.secondary)

            VStack(alignment: .leading, spacing: 8) {
                Text("API Key")
                    .font(CyberFont.body(size: 11, weight: .medium))
                TextField("sk-xxx", text: $editApiKey)
                    .textFieldStyle(.roundedBorder)
            }
            VStack(alignment: .leading, spacing: 8) {
                Text("Base URL")
                    .font(CyberFont.body(size: 11, weight: .medium))
                TextField("https://api.example.com/v1", text: $editBaseUrl)
                    .textFieldStyle(.roundedBorder)
            }
            VStack(alignment: .leading, spacing: 8) {
                Text("模型名称")
                    .font(CyberFont.body(size: 11, weight: .medium))
                TextField("gpt-4o / deepseek-chat", text: $editModel)
                    .textFieldStyle(.roundedBorder)
            }

            HStack {
                Spacer()
                Button("保存") {
                    onSave(editApiKey, editBaseUrl, editModel)
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(24)
        .frame(minWidth: 360)
        .onAppear {
            editApiKey = apiKey
            editBaseUrl = baseUrl
            editModel = model
        }
    }
}

private struct EggRowView: View {
    let egg: [String: Any]
    let downloadURL: URL?
    let onDelete: () -> Void

    var body: some View {
        let eggId = egg["egg_id"] as? String ?? ""
        let name = egg["name"] as? String ?? eggId
        let duckType = egg["duck_type"] as? String ?? ""
        let connected = egg["connected"] as? Bool ?? false
        let downloaded = egg["downloaded"] as? Bool ?? false
        let createdAt = egg["created_at"] as? Double ?? 0

        HStack(spacing: 10) {
            Text("🥚").font(.title3)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(name)
                        .font(CyberFont.body(size: 12, weight: .medium))
                    Text(duckType)
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(CyberColor.cyan)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 1)
                        .background(CyberColor.cyan.opacity(0.1))
                        .cornerRadius(4)
                    if connected {
                        Text("已连接")
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(.green)
                    } else if downloaded {
                        Text("已下载")
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(.blue)
                    }
                }
                Text("\(eggId) · \(Date(timeIntervalSince1970: createdAt).formatted(date: .abbreviated, time: .shortened))")
                    .font(CyberFont.body(size: 10))
                    .foregroundColor(.secondary)
            }
            Spacer()
            if let url = downloadURL {
                Link(destination: url) {
                    Image(systemName: "arrow.down.circle")
                        .font(.system(size: 14))
                }
                .buttonStyle(.plain)
            }
            Button {
                onDelete()
            } label: {
                Image(systemName: "trash")
                    .font(.system(size: 12))
                    .foregroundColor(.red.opacity(0.7))
            }
            .buttonStyle(.plain)
        }
        .padding(10)
        .background(Color(NSColor.controlBackgroundColor).opacity(0.6))
        .cornerRadius(6)
    }
}

// MARK: - Dictionary Hashable Helper

private extension Dictionary where Key == String, Value == Any {
    var hashableKey: String {
        (self["duck_id"] as? String) ?? (self["egg_id"] as? String) ?? (self["duck_type"] as? String) ?? UUID().uuidString
    }
}
