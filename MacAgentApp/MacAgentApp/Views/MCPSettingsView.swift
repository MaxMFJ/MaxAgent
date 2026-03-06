import SwiftUI

// MARK: - Built-in MCP Catalog

private struct BuiltinMCP {
    let id: String
    let title: String
    let subtitle: String
    let icon: String
    let color: Color
    let transport: String
    let command: [String]
    let url: String
    let requiresInstall: Bool   // needs npm/npx
    let installHint: String

    static let catalog: [BuiltinMCP] = [
        // ── 系统无原生实现的增量能力 ──
        BuiltinMCP(
            id: "github",
            title: "GitHub MCP",
            subtitle: "仓库、PR、Issues、代码搜索",
            icon: "chevron.left.forwardslash.chevron.right",
            color: .purple,
            transport: "stdio",
            command: ["npx", "-y", "@modelcontextprotocol/server-github"],
            url: "",
            requiresInstall: true,
            installHint: "需要 GITHUB_TOKEN 环境变量"
        ),
        BuiltinMCP(
            id: "brave-search",
            title: "Brave Search MCP",
            subtitle: "隐私优先的网页搜索引擎",
            icon: "magnifyingglass",
            color: .orange,
            transport: "stdio",
            command: ["npx", "-y", "@modelcontextprotocol/server-brave-search"],
            url: "",
            requiresInstall: true,
            installHint: "需要 BRAVE_API_KEY 环境变量"
        ),
        BuiltinMCP(
            id: "sequential-thinking",
            title: "Sequential Thinking MCP",
            subtitle: "增强推理、逐步思考与问题分解",
            icon: "brain.head.profile",
            color: .cyan,
            transport: "stdio",
            command: ["npx", "-y", "@modelcontextprotocol/server-sequential-thinking"],
            url: "",
            requiresInstall: true,
            installHint: "需要 Node.js 18+"
        ),
        // ── 原生工具的增强补充 ──
        BuiltinMCP(
            id: "puppeteer",
            title: "Browser Automation MCP",
            subtitle: "Puppeteer 浏览器自动化（增强原生 browser_tool）",
            icon: "safari",
            color: .red,
            transport: "stdio",
            command: ["npx", "-y", "@modelcontextprotocol/server-puppeteer"],
            url: "",
            requiresInstall: true,
            installHint: "需要 Node.js 18+、自动安装 Chromium"
        ),
        BuiltinMCP(
            id: "filesystem",
            title: "Filesystem MCP",
            subtitle: "增强文件操作（sandbox 安全模式）",
            icon: "folder",
            color: .yellow,
            transport: "stdio",
            command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/"],
            url: "",
            requiresInstall: true,
            installHint: "需要 Node.js 18+"
        ),
        BuiltinMCP(
            id: "memory",
            title: "Memory MCP",
            subtitle: "持久化知识图谱、增强跨会话记忆",
            icon: "brain",
            color: .mint,
            transport: "stdio",
            command: ["npx", "-y", "@modelcontextprotocol/server-memory"],
            url: "",
            requiresInstall: true,
            installHint: "需要 Node.js 18+"
        ),
    ]
}

// MARK: - MCP Settings Content

struct MCPSettingsContent: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @State private var showAddSheet = false
    @State private var addName = ""
    @State private var addTransport = "stdio"
    @State private var addCommand = ""
    @State private var addUrl = ""
    @State private var showBuiltinCatalog = true
    @State private var connectingIds: Set<String> = []  // 正在连接中的 MCP ID

    // Connected server names set for quick lookup
    private var connectedNames: Set<String> {
        Set(viewModel.mcpServers.compactMap { $0["name"] as? String })
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {

            // ── 内置 MCP 目录 ─────────────────────────────────────────
            VStack(alignment: .leading, spacing: 8) {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) { showBuiltinCatalog.toggle() }
                } label: {
                    HStack {
                        Image(systemName: showBuiltinCatalog ? "chevron.down" : "chevron.right")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                        Text("内置 MCP 能力库")
                            .font(.system(size: 13, weight: .semibold))
                        Text("\(BuiltinMCP.catalog.count) 个")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color(NSColor.controlBackgroundColor))
                            .cornerRadius(4)
                        Spacer()
                    }
                }
                .buttonStyle(.plain)

                if showBuiltinCatalog {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                        ForEach(BuiltinMCP.catalog, id: \.id) { mcp in
                            BuiltinMCPCard(
                                mcp: mcp,
                                isConnected: connectedNames.contains(mcp.id),
                                isConnecting: connectingIds.contains(mcp.id)
                            ) {
                                // One-click connect
                                connectingIds.insert(mcp.id)
                                Task {
                                    await viewModel.addMCPServer(
                                        name: mcp.id,
                                        transport: mcp.transport,
                                        command: mcp.transport == "stdio" ? mcp.command : nil,
                                        url: mcp.transport == "http" ? mcp.url : nil
                                    )
                                    connectingIds.remove(mcp.id)
                                }
                            } onRemove: {
                                Task { await viewModel.deleteMCPServer(name: mcp.id) }
                            }
                        }
                    }
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor).opacity(0.5))
            .cornerRadius(10)

            // ── 已连接服务器 ───────────────────────────────────────────
            // 说明
            VStack(alignment: .leading, spacing: 6) {
                Text("MCP（Model Context Protocol）")
                    .font(.system(size: 14, weight: .semibold))
                Text("连接外部工具服务，支持 npx stdio 进程和 HTTP 两种方式。添加后，Agent 可自动调用 MCP 提供的工具。")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)

            // 工具栏
            HStack {
                Text("已连接的 MCP 服务")
                    .font(.system(size: 13, weight: .semibold))
                Spacer()
                Button {
                    Task { await viewModel.loadMCPServers() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.borderless)
                .disabled(viewModel.isLoadingMCP)

                Button {
                    addName = ""; addTransport = "stdio"; addCommand = ""; addUrl = ""
                    showAddSheet = true
                } label: {
                    Label("添加", systemImage: "plus")
                }
                .buttonStyle(.borderedProminent)
            }

            if let err = viewModel.mcpError {
                Text(err)
                    .foregroundColor(.red)
                    .font(.system(size: 11))
            }

            if viewModel.isLoadingMCP {
                ProgressView("加载中…")
                    .frame(maxWidth: .infinity)
            } else if viewModel.mcpServers.isEmpty {
                Text("尚未添加任何 MCP 服务器")
                    .foregroundColor(.secondary)
                    .font(.system(size: 12))
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding()
            } else {
                ForEach(viewModel.mcpServers.indices, id: \.self) { i in
                    let server = viewModel.mcpServers[i]
                    MCPServerRow(server: server) {
                        let name = server["name"] as? String ?? ""
                        Task { await viewModel.deleteMCPServer(name: name) }
                    }
                }
            }

            if !viewModel.mcpTools.isEmpty {
                Divider()
                VStack(alignment: .leading, spacing: 8) {
                    Text("可用 MCP 工具 (\(viewModel.mcpTools.count))")
                        .font(.system(size: 13, weight: .semibold))
                    ForEach(viewModel.mcpTools.indices, id: \.self) { i in
                        let tool = viewModel.mcpTools[i]
                        HStack {
                            Image(systemName: "wrench.and.screwdriver")
                                .foregroundColor(Color.accentColor)
                                .frame(width: 16)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(tool["full_name"] as? String ?? tool["name"] as? String ?? "")
                                    .font(.system(size: 12, weight: .medium))
                                if let desc = tool["description"] as? String, !desc.isEmpty {
                                    Text(desc)
                                        .font(.system(size: 11))
                                        .foregroundColor(.secondary)
                                        .lineLimit(2)
                                }
                            }
                            Spacer()
                        }
                        .padding(.vertical, 4)
                        Divider()
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
            Task { await viewModel.loadMCPServers() }
        }
        .sheet(isPresented: $showAddSheet) {
            AddMCPServerSheet(
                name: $addName,
                transport: $addTransport,
                command: $addCommand,
                url: $addUrl,
                onAdd: {
                    let cmdParts = addTransport == "stdio" ? addCommand.components(separatedBy: " ").filter { !$0.isEmpty } : nil
                    let urlVal = addTransport == "http" ? addUrl : nil
                    Task {
                        await viewModel.addMCPServer(name: addName, transport: addTransport, command: cmdParts, url: urlVal)
                        showAddSheet = false
                    }
                },
                onCancel: { showAddSheet = false }
            )
        }
    }
}

// MARK: - Builtin MCP Card

private struct BuiltinMCPCard: View {
    let mcp: BuiltinMCP
    let isConnected: Bool
    let isConnecting: Bool
    let onConnect: () -> Void
    let onRemove: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(mcp.color.opacity(0.15))
                    .frame(width: 36, height: 36)
                Image(systemName: mcp.icon)
                    .font(.system(size: 16))
                    .foregroundColor(mcp.color)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(mcp.title)
                    .font(.system(size: 11, weight: .semibold))
                    .lineLimit(1)
                Text(mcp.subtitle)
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
                    .lineLimit(2)
                if mcp.requiresInstall {
                    Text(mcp.installHint)
                        .font(.system(size: 8))
                        .foregroundColor(mcp.color.opacity(0.8))
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 0)
            if isConnecting {
                ProgressView()
                    .controlSize(.small)
                    .help("正在连接…")
            } else if isConnected {
                Button(action: onRemove) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                        .font(.system(size: 18))
                }
                .buttonStyle(.plain)
                .help("已连接，点击移除")
            } else {
                Button(action: onConnect) {
                    Image(systemName: "plus.circle")
                        .foregroundColor(mcp.color)
                        .font(.system(size: 18))
                }
                .buttonStyle(.plain)
                .help("点击连接")
            }
        }
        .padding(10)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isConnected ? Color.green.opacity(0.4) : Color.clear, lineWidth: 1)
        )
    }
}

// MARK: - MCP Server Row

private struct MCPServerRow: View {
    let server: [String: Any]
    let onDelete: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            let connected = server["connected"] as? Bool ?? false
            Circle()
                .fill(connected ? Color.green : Color.orange)
                .frame(width: 8, height: 8)
            VStack(alignment: .leading, spacing: 3) {
                Text(server["name"] as? String ?? "—")
                    .font(.system(size: 13, weight: .medium))
                HStack(spacing: 6) {
                    Text(server["transport"] as? String ?? "")
                        .font(.system(size: 10))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.15))
                        .cornerRadius(4)
                    if let cmd = server["command"] as? [String] {
                        Text(cmd.joined(separator: " "))
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                    if let url = server["url"] as? String, !url.isEmpty {
                        Text(url)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                }
                if let toolCount = server["tool_count"] as? Int {
                    Text("\(toolCount) 个工具")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }
            }
            Spacer()
            Button(role: .destructive) { onDelete() } label: {
                Image(systemName: "trash")
                    .foregroundColor(.red)
            }
            .buttonStyle(.borderless)
        }
        .padding(10)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
    }
}

// MARK: - Add MCP Server Sheet

private struct AddMCPServerSheet: View {
    @Binding var name: String
    @Binding var transport: String
    @Binding var command: String
    @Binding var url: String
    let onAdd: () -> Void
    let onCancel: () -> Void

    private var isValid: Bool {
        !name.trimmingCharacters(in: .whitespaces).isEmpty &&
        (transport == "http" ? !url.trimmingCharacters(in: .whitespaces).isEmpty : !command.trimmingCharacters(in: .whitespaces).isEmpty)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("添加 MCP 服务器")
                .font(.system(size: 16, weight: .semibold))

            VStack(alignment: .leading, spacing: 6) {
                Text("名称").font(.system(size: 12))
                TextField("例如: filesystem", text: $name)
                    .textFieldStyle(.roundedBorder)
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("传输方式").font(.system(size: 12))
                Picker("", selection: $transport) {
                    Text("stdio（子进程）").tag("stdio")
                    Text("http（HTTP POST）").tag("http")
                }
                .pickerStyle(.segmented)
            }

            if transport == "stdio" {
                VStack(alignment: .leading, spacing: 6) {
                    Text("启动命令").font(.system(size: 12))
                    TextField("例如: npx -y @modelcontextprotocol/server-filesystem /path", text: $command)
                        .textFieldStyle(.roundedBorder)
                    Text("整条命令，用空格分隔参数")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    Text("服务 URL").font(.system(size: 12))
                    TextField("例如: http://localhost:3001/mcp", text: $url)
                        .textFieldStyle(.roundedBorder)
                }
            }

            HStack {
                Button("取消", role: .cancel, action: onCancel)
                Spacer()
                Button("添加", action: onAdd)
                    .buttonStyle(.borderedProminent)
                    .disabled(!isValid)
            }
        }
        .padding(24)
        .frame(width: 420)
    }
}
