# RPA JSON 标准化流程功能评审：是否需要保留？

## 一、你已实现的能力（简要）

| 能力 | 实现位置 | 说明 |
|------|----------|------|
| **Runbook 数据模型** | `runbook_models.py` | 标准化流程：id/name/description/steps（tool、args、condition、retry、on_error）、inputs/outputs |
| **注册与匹配** | `runbook_registry.py` | 从 `runbooks/` 加载；`find_by_query()` 按描述/标签做关键词打分；支持用户导入、删除 |
| **Prompt 注入** | `prompt_loader.py` | 仅当 **执行类意图**（非简单问答）时，注入「与当前请求匹配」的 Runbook 列表（最多 3 条），标记为 `[可用 RPA 自动化流程]` |
| **前端导入** | `RPASettingsView.swift` | 用户可导入 JSON/YAML，上传到后端并持久化到 `runbooks/` |
| **Agent 行为** | `runbook.md` | 要求 LLM：请求与某 Runbook 高度吻合时**优先建议或直接执行**该流程，不重新发明轮子；「一键完成/自动化/按流程」类描述必须检查是否有匹配 Runbook |

效果：**用户导入 RPA JSON → 系统按意图匹配并注入 prompt → Agent 主动选用标准化流程执行**，无需改代码即可扩展「可被 Agent 调用的标准化工作流」。

---

## 二、评审结论：**建议保留**

### 2.1 为什么值得保留

1. **确定性 + 可审计**  
   像「PDF 合并」「批量重命名」「Excel 转 CSV」这类任务，有固定、可复现的步骤。Runbook 把「正确做法」固化下来，Agent 按步骤调用工具即可，减少 LLM 编造错误命令或漏步骤的情况，也便于排查和审计。

2. **用户可扩展，无需改代码**  
   用户（或管理员）通过设置页导入 JSON/YAML 就能新增流程，适合团队/公司内部的标准操作（如「周报汇总」「数据导出到某系统」）。这是纯「自然语言 + 通用工具」难以稳定覆盖的。

3. **与「主 Agent + Duck」的定位一致**  
   主 Agent 负责理解意图、选流程；Runbook 负责「怎么一步步做」。你已有 Duck/委派机制，Runbook 相当于**主 Agent 侧的标准作业程序（SOP）**，和 Duck 的执行能力是互补的，不是重复。

4. **实现成本已付出，边际成本低**  
   注入只在「执行类意图」时触发，且只带少量匹配项；不匹配时几乎无额外开销。保留的维护成本主要是：Runbook 格式稳定、文档说明、少量内置 Runbook 的维护。

### 2.2 什么时候可能显得「多余」

- **用户几乎从不导入自定义 Runbook**：若 99% 场景只用内置的十来个 Runbook，理论上可以把它们写进 system prompt 或写死列表。但那样会失去「用户自定义扩展」和「按需注入」的灵活性，且你已支持导入，保留更一致。
- **LLM 对内置工具已经用得足够好**：若未来模型对「用 terminal / file 做 PDF 合并」等已经非常稳，Runbook 的「纠偏」价值会下降，但仍有**标准化、可复用、可审计**的价值，尤其在企业/团队场景。

综上：**没有强理由砍掉该功能**，保留的收益大于成本。

---

## 三、可选优化（已实现部分）

1. **Prompt 里的笔误**  
   已修复：`prompt_loader.py` 中「RAP」已改为「RPA」。

2. **匹配质量**  
   已实现：
   - **注入阈值**：仅当匹配分数 ≥ `MACAGENT_RUNBOOK_INJECT_MIN_SCORE`（默认 `0.45`）时才注入 Runbook 提示，减少弱相关流程干扰。
   - **类别过滤**：可选环境变量 `MACAGENT_RUNBOOK_INJECT_CATEGORIES`（逗号分隔，如 `pdf,general`），仅注入指定 category 的 Runbook；未设置则不按类别过滤。
   - `runbook_registry.find_by_query_with_scores()` 返回 `(Runbook, score)` 列表，供调用方按阈值与类别过滤。

3. **执行统计与反馈**  
   你已有 `record_execution(runbook_id)` 和 `execute_count`，若在 UI 或日志里暴露「某 Runbook 被选用/执行成功与否」，便于用户判断哪些流程有用、哪些需要调整。

4. **和 Duck 的配合**  
   已实现：
   - **Runbook 模型**：新增字段 `prefer_duck: bool = False`；在 JSON 中可设置 `"prefer_duck": true`，**导入后生效**（见下方「如何导入 Runbook」）。
   - **Prompt 注入**：注入列表中会为 `prefer_duck=true` 的 Runbook 追加「（可委派 Duck）」提示。
   - **runbook.md**：已补充执行方式「委派 Duck」——若 Runbook 标记为可委派 Duck 且有可用分身，优先考虑 `delegate_duck`，实现「主 Agent 选 Runbook → Duck 执行」闭环。

---

## 四、如何导入 Runbook（「导入后生效」指什么）

**「导入后生效」** = 把一份 Runbook 的 JSON/YAML 文件交给系统，系统会把它存到 `backend/runbooks/` 并加入内存注册表；之后 Agent 在做执行类请求时，就会按匹配结果注入这些 Runbook，`prefer_duck` 等字段也才会被用到。

### 方式一：Mac App 设置页（推荐）

1. 打开 **设置 → RPA 流程**（或侧栏「RPA 流程」）。
2. 点击 **「导入 Runbook」** 按钮。
3. 在文件选择器中选一个 **.json 或 .yaml/.yml** 文件（内容需符合 Runbook 格式，且包含 `id` 等必填字段）。
4. 导入成功后，该 Runbook 会出现在列表中，并立即被后端加载，**无需重启**；之后对话/自主任务中即可被匹配和注入。

### 方式二：HTTP API

- **上传文件**：`POST /runbooks/upload`，表单字段 `file` 为 JSON/YAML 文件，可选查询参数 `overwrite=true` 覆盖同 id。
- **JSON body**：`POST /runbooks/import`，body 为 `{"data": { ... Runbook 对象 ... }, "overwrite": false}`。

### Runbook JSON 里如何写 `prefer_duck`

在任意 Runbook 的 JSON 顶层增加一行即可，例如：

```json
{
  "id": "rpa_pdf_merge",
  "name": "PDF 合并",
  "description": "...",
  "prefer_duck": true,
  "steps": [ ... ]
}
```

保存后通过上述任一方式导入，该流程在注入时会出现「（可委派 Duck）」提示，且 runbook.md 会引导 Agent 优先用 `delegate_duck` 执行。

---

## 五、一句话总结

**需要这个功能。** 它把「用户可导入的 RPA JSON 标准化流程」和「Agent 主动选用标准化工作流」结合起来了，能提高常见任务的确定性和可扩展性，且已与现有架构（Runbook 注册、执行意图、prompt 注入）对齐，建议保留；若担心存在感不足，可通过统计与 UI 反馈强化「哪些 Runbook 被用到了」。
