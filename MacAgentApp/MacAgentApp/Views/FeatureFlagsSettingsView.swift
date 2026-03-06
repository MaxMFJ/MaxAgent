import SwiftUI

/// 功能开关管理页 — 对应 v3.3 Feature Flag 体系
struct FeatureFlagsSettingsContent: View {
    @EnvironmentObject var viewModel: AgentViewModel
    @State private var editingValues: [String: String] = [:]   // for int/float inline edit

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("功能开关 (Feature Flags)")
                        .font(CyberFont.body(size: 14, weight: .semibold))
                    Text("热更新功能开关，无需重启后端。修改后立即生效。")
                        .font(CyberFont.body(size: 11))
                        .foregroundColor(.secondary)
                }
                Spacer()
                Button {
                    Task { await viewModel.loadFeatureFlags() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .disabled(viewModel.isLoadingFeatureFlags)
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)

            if viewModel.isLoadingFeatureFlags {
                ProgressView("加载中…").frame(maxWidth: .infinity).padding()
            } else if viewModel.featureFlags.isEmpty {
                Text("暂无可用 Flag，请确认后端已启动")
                    .foregroundColor(.secondary)
                    .font(CyberFont.body(size: 12))
                    .frame(maxWidth: .infinity)
                    .padding()
            } else {
                // Sort: bool first (toggles), then int/float (numbers)
                let flags = viewModel.featureFlags.sorted { a, b in
                    let aType = a["type"] as? String ?? ""
                    let bType = b["type"] as? String ?? ""
                    if aType == bType { return (a["name"] as? String ?? "") < (b["name"] as? String ?? "") }
                    if aType == "bool" { return true }
                    if bType == "bool" { return false }
                    return (a["name"] as? String ?? "") < (b["name"] as? String ?? "")
                }
                ForEach(Array(flags.enumerated()), id: \.offset) { idx, flag in
                    FeatureFlagRow(
                        flag: flag,
                        editValue: Binding(
                            get: { editingValues[flag["name"] as? String ?? ""] ?? "" },
                            set: { editingValues[flag["name"] as? String ?? ""] = $0 }
                        )
                    ) { name, newValue in
                        Task { await viewModel.setFeatureFlag(name: name, value: newValue) }
                    }
                }
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear {
            Task { await viewModel.loadFeatureFlags() }
        }
    }
}

// MARK: - Feature Flag Row

private struct FeatureFlagRow: View {
    let flag: [String: Any]
    @Binding var editValue: String
    let onUpdate: (String, Any) -> Void

    private var name: String { flag["name"] as? String ?? "" }
    private var flagType: String { flag["type"] as? String ?? "bool" }
    private var desc: String { flag["description"] as? String ?? "" }
    private var source: String { flag["source"] as? String ?? "" }

    // Backend sends int 0/1 for bools; use "type" field to distinguish
    private var currentBool: Bool {
        if let b = flag["current"] as? Bool { return b }
        if let n = flag["current"] as? Int { return n != 0 }
        if let n = (flag["current"] as? NSNumber) { return n.boolValue }
        return false
    }
    private var currentInt: Int { (flag["current"] as? Int) ?? ((flag["current"] as? NSNumber)?.intValue ?? 0) }
    private var currentDouble: Double { (flag["current"] as? Double) ?? ((flag["current"] as? NSNumber)?.doubleValue ?? 0) }

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            // Left: name + description
            VStack(alignment: .leading, spacing: 3) {
                Text(friendlyName(name))
                    .font(CyberFont.body(size: 12, weight: .medium))
                if !desc.isEmpty {
                    Text(desc)
                        .font(CyberFont.body(size: 10))
                        .foregroundColor(.secondary)
                }
                HStack(spacing: 6) {
                    Text(name)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundColor(CyberColor.cyan.opacity(0.7))
                    if source != "default" {
                        Text(source)
                            .font(CyberFont.body(size: 9))
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(CyberColor.cyan.opacity(0.15))
                            .cornerRadius(4)
                            .foregroundColor(CyberColor.cyan)
                    }
                }
            }
            Spacer()
            // Right: control based on type
            Group {
                if flagType == "bool" {
                    Toggle("", isOn: Binding(get: { currentBool }, set: { onUpdate(name, $0) }))
                        .toggleStyle(.switch)
                        .controlSize(.small)
                } else if flagType == "int" {
                    TextField("", text: $editValue)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 70)
                        .font(.system(size: 12, design: .monospaced))
                        .onSubmit {
                            if let v = Int(editValue) { onUpdate(name, v) }
                        }
                        .onAppear { editValue = "\(currentInt)" }
                } else if flagType == "float" {
                    TextField("", text: $editValue)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 80)
                        .font(.system(size: 12, design: .monospaced))
                        .onSubmit {
                            if let v = Double(editValue) { onUpdate(name, v) }
                        }
                        .onAppear { editValue = String(format: "%.2f", currentDouble) }
                } else {
                    Text(String(describing: flag["current"] ?? ""))
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding(10)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
    }

    private func friendlyName(_ key: String) -> String {
        let map: [String: String] = [
            "ENABLE_HITL": "HITL 人工审批",
            "ENABLE_AUDIT_LOG": "审计日志",
            "ENABLE_SESSION_RESUME": "会话恢复",
            "ENABLE_IDEMPOTENT_TASKS": "幂等任务缓存",
            "ENABLE_SUBAGENT": "子 Agent 调度",
            "ENABLE_EVOMAP": "EvoMap 服务",
            "ENABLE_LANGCHAIN_COMPAT": "LangChain 兼容模式",
            "ENABLE_PLAN_AND_EXECUTE": "Plan-and-Execute",
            "ENABLE_MID_LOOP_REFLECTION": "中途反思",
            "ENABLE_EXTENDED_THINKING": "Extended Thinking",
            "ENABLE_ON_DEMAND_SKILL_FETCH": "Skill 按需拉取",
            "AUTO_TOOL_UPGRADE": "工具自动升级",
            "USE_SUMMARIZED_CONTEXT": "压缩上下文",
            "TRACE_TOKEN_STATS": "Token 统计追踪",
            "TRACE_TOOL_CALLS": "工具调用追踪",
            "ENABLE_FAILURE_TYPE_REFLECTION": "失败分类反思",
            "ENABLE_IMPORTANCE_WEIGHTED_MEMORY": "重要性加权 Memory",
            "HITL_CONFIRMATION_TIMEOUT": "HITL 超时（秒）",
            "SUBAGENT_MAX_CONCURRENT": "子 Agent 并发数",
            "SUBAGENT_TIMEOUT": "子 Agent 超时（秒）",
            "AUDIT_LOG_MAX_SIZE_MB": "审计日志上限（MB）",
            "IDEMPOTENT_CACHE_TTL": "幂等缓存 TTL（秒）",
            "GOAL_RESTATE_EVERY_N": "目标重述间隔（步）",
            "MID_LOOP_REFLECTION_EVERY_N": "中途反思间隔（步）",
            "ESCALATION_FORCE_AFTER_N": "强制升级阈值（次）",
            "ESCALATION_SKILL_AFTER_N": "技能降级阈值（次）",
            "ESCALATION_SIMILARITY_THRESHOLD": "升级相似度阈值",
            "ON_DEMAND_SKILL_FETCH_TIMEOUT": "Skill 拉取超时（秒）",
            "ON_DEMAND_SKILL_MAX_FETCH": "单次最多拉取 Skill 数",
            "HEALTH_DEEP_LLM_TIMEOUT": "深度健康检查超时（秒）",
            "EXTENDED_THINKING_BUDGET_TOKENS": "CoT Token 预算",
        ]
        return map[key] ?? key.replacingOccurrences(of: "_", with: " ").capitalized
    }
}
