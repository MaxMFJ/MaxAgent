import SwiftUI
import UniformTypeIdentifiers

// MARK: - RPA 设置主视图

struct RPASettingsContent: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @State private var showFilePicker: Bool = false
    @State private var searchText: String = ""
    @State private var showDeleteConfirm: String? = nil   // 存待删除的 runbook id

    private var filtered: [[String: Any]] {
        guard !searchText.isEmpty else { return viewModel.runbookList }
        let q = searchText.lowercased()
        return viewModel.runbookList.filter { rb in
            let name = (rb["name"] as? String ?? "").lowercased()
            let desc = (rb["description"] as? String ?? "").lowercased()
            let cat  = (rb["category"] as? String ?? "").lowercased()
            let tags = (rb["tags"] as? [String] ?? []).joined(separator: " ").lowercased()
            return name.contains(q) || desc.contains(q) || cat.contains(q) || tags.contains(q)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {

            // ── 标题栏 ──
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("RPA 机器人流程自动化")
                        .font(CyberFont.body(size: 14, weight: .semibold))
                    Text("Robotic Process Automation — 标准化自动操作脚本，LLM 可智能调用。")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                }
                Spacer()
                Button {
                    showFilePicker = true
                } label: {
                    Label("导入 Runbook", systemImage: "square.and.arrow.down")
                        .font(CyberFont.body(size: 12))
                }
                .buttonStyle(.borderedProminent)
                .tint(CyberColor.cyan)
                .fileImporter(
                    isPresented: $showFilePicker,
                    allowedContentTypes: [.json, UTType(filenameExtension: "yaml") ?? .data,
                                          UTType(filenameExtension: "yml") ?? .data],
                    allowsMultipleSelection: false
                ) { result in
                    handleImport(result: result)
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)

            // ── 错误横幅 ──
            if let error = viewModel.runbookError {
                HStack {
                    Image(systemName: "exclamationmark.triangle.fill").foregroundColor(.red)
                    Text(error)
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.red)
                    Spacer()
                    Button("关闭") { viewModel.runbookError = nil }
                        .font(CyberFont.body(size: 11))
                }
                .padding(10)
                .background(Color.red.opacity(0.1))
                .cornerRadius(6)
            }

            // ── 统计徽章 ──
            if !viewModel.runbookList.isEmpty {
                let categories = Set(viewModel.runbookList.compactMap { $0["category"] as? String })
                HStack(spacing: 12) {
                    RPAStatBadge(label: "总计", value: "\(viewModel.runbookList.count)", color: CyberColor.cyan)
                    RPAStatBadge(label: "分类", value: "\(categories.count)", color: .purple)
                }
            }

            // ── 搜索框 ──
            HStack {
                Image(systemName: "magnifyingglass").foregroundColor(.secondary)
                TextField("搜索名称 / 描述 / 分类 / 标签", text: $searchText)
                    .textFieldStyle(.plain)
                    .font(CyberFont.body(size: 12))
                if !searchText.isEmpty {
                    Button { searchText = "" } label: {
                        Image(systemName: "xmark.circle.fill").foregroundColor(.secondary)
                    }.buttonStyle(.plain)
                }
            }
            .padding(8)
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(6)

            // ── 列表 ──
            if viewModel.isLoadingRunbooks {
                HStack {
                    Spacer()
                    ProgressView().scaleEffect(0.8)
                    Text("加载中…").font(CyberFont.body(size: 12)).foregroundColor(.secondary)
                    Spacer()
                }
                .padding()
            } else if filtered.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "list.bullet.rectangle")
                        .font(.system(size: 32))
                        .foregroundColor(.secondary.opacity(0.5))
                    Text(viewModel.runbookList.isEmpty ? "暂无 Runbook，点击「导入」添加第一个" : "未找到匹配的 Runbook")
                        .font(CyberFont.body(size: 12))
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(32)
            } else {
                VStack(spacing: 8) {
                    ForEach(filtered.indices, id: \.self) { i in
                        RunbookRow(runbook: filtered[i]) {
                            let id = filtered[i]["id"] as? String ?? ""
                            showDeleteConfirm = id
                        }
                    }
                }
            }

            Spacer(minLength: 0)
        }
        .task { await viewModel.loadRunbooks() }
        // 删除二次确认
        .alert("确认删除", isPresented: Binding(
            get: { showDeleteConfirm != nil },
            set: { if !$0 { showDeleteConfirm = nil } }
        )) {
            Button("取消", role: .cancel) { showDeleteConfirm = nil }
            Button("删除", role: .destructive) {
                if let id = showDeleteConfirm {
                    Task { await viewModel.deleteRunbook(id: id) }
                }
                showDeleteConfirm = nil
            }
        } message: {
            let name = viewModel.runbookList.first(where: { $0["id"] as? String == showDeleteConfirm })?["name"] as? String ?? showDeleteConfirm ?? ""
            Text("将永久删除 Runbook「\(name)」，此操作不可撤销。")
        }
    }

    private func handleImport(result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard let url = urls.first else { return }
            let accessing = url.startAccessingSecurityScopedResource()
            defer { if accessing { url.stopAccessingSecurityScopedResource() } }
            guard let data = try? Data(contentsOf: url) else {
                viewModel.runbookError = "无法读取文件"
                return
            }
            let filename = url.lastPathComponent
            Task { await viewModel.uploadRunbookFile(data: data, filename: filename) }
        case .failure(let err):
            viewModel.runbookError = "文件选择失败: \(err.localizedDescription)"
        }
    }
}

// MARK: - 单条 Runbook 行

private struct RunbookRow: View {
    let runbook: [String: Any]
    let onDelete: () -> Void

    private var name: String       { runbook["name"]        as? String ?? "未命名" }
    private var desc: String       { runbook["description"] as? String ?? "" }
    private var category: String   { runbook["category"]    as? String ?? "general" }
    private var tags: [String]     { runbook["tags"]        as? [String] ?? [] }
    private var stepCount: Int     {
        (runbook["steps"] as? [[String: Any]])?.count ?? 0
    }
    private var version: String    { runbook["version"]     as? String ?? "1.0" }
    private var source: String     { runbook["source"]      as? String ?? "" }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // 左侧图标
            Image(systemName: categoryIcon(category))
                .font(.system(size: 18))
                .foregroundColor(CyberColor.cyan)
                .frame(width: 28)
                .padding(.top, 2)

            VStack(alignment: .leading, spacing: 4) {
                // 名称 + 版本
                HStack(spacing: 6) {
                    Text(name)
                        .font(CyberFont.body(size: 13, weight: .semibold))
                    Text("v\(version)")
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Color.secondary.opacity(0.12))
                        .cornerRadius(3)
                }

                // 描述
                if !desc.isEmpty {
                    Text(desc)
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }

                // 标签 + 步数
                HStack(spacing: 6) {
                    // 分类
                    Text(category)
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(CyberColor.cyan)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(CyberColor.cyan.opacity(0.1))
                        .cornerRadius(4)

                    // 用户标签
                    ForEach(tags.prefix(3), id: \.self) { tag in
                        Text(tag)
                            .font(CyberFont.body(size: 10))
                            .foregroundColor(.purple)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Color.purple.opacity(0.1))
                            .cornerRadius(4)
                    }

                    Spacer()

                    // 步数
                    HStack(spacing: 3) {
                        Image(systemName: "list.number")
                            .font(.system(size: 9))
                        Text("\(stepCount) 步")
                            .font(CyberFont.body(size: 10))
                    }
                    .foregroundColor(.secondary)
                }

                // 来源（如有）
                if !source.isEmpty {
                    Text(source)
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(.secondary.opacity(0.7))
                        .lineLimit(1)
                }
            }

            Spacer()

            // 删除按钮
            Button(action: onDelete) {
                Image(systemName: "trash")
                    .font(.system(size: 13))
                    .foregroundColor(.red.opacity(0.8))
            }
            .buttonStyle(.plain)
            .padding(.top, 2)
        }
        .padding(12)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color(NSColor.separatorColor), lineWidth: 0.5)
        )
    }

    private func categoryIcon(_ cat: String) -> String {
        switch cat.lowercased() {
        case "python", "code":    return "terminal"
        case "git":               return "arrow.triangle.branch"
        case "deploy":            return "cloud.fill"
        case "test":              return "checkmark.seal"
        case "infra":             return "server.rack"
        case "data":              return "cylinder.split.1x2"
        default:                  return "list.bullet.rectangle"
        }
    }
}

// MARK: - 统计徽章

private struct RPAStatBadge: View {
    let label: String
    let value: String
    let color: Color

    var body: some View {
        HStack(spacing: 4) {
            Text(value)
                .font(CyberFont.body(size: 14, weight: .semibold))
                .foregroundColor(color)
            Text(label)
                .font(CyberFont.body(size: 11))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(color.opacity(0.08))
        .cornerRadius(6)
    }
}
