# 冲击 2026 标杆级 Agent 框架：差距分析与进阶路线图

在 **v3（底层稳固）+ v3.1（上下文/规划/反思/安全/目标对齐）** 之后，本文档定义「2026 标杆级 Agent」的常见要件，对照当前能力做差距分析，并给出 **v3.1 之后还需什么** 才能达到可对外对标、可复现评估的标杆级框架。

---

## 一、2026 标杆级 Agent 框架的常见维度（共识来源）

基于 SWE-bench / MAESTRO / MemoryAgentBench / TRAIL / HITL-CHEQ / Sherlock 等 2025–2026 研究与实践，归纳为以下维度（不要求全部满分，但标杆框架通常在这些方向有明确设计）。

| 维度 | 标杆常见要件 | 典型参考 |
|------|----------------|----------|
| **1. 架构与推理** | Plan-and-Execute、Replan、结构化/长程 memory、可选多智能体 | SWE-agent, Plan-and-Execute, Reflexion, MemoryAgentBench |
| **2. 可观测与可评估** | 全链路 trace、成本/延迟/成功率可测、可复现 benchmark 跑分 | MAESTRO, TRAIL, Traceloop, PacaBench |
| **3. 安全与可控** | 沙箱、统一审计、危险动作拦截、HITL 审批/回滚 | CHEQ, Sherlock, GA-Rollback, Magentic-UI |
| **4. 鲁棒与自愈** | 错误分类、智能 escalation、反思/验证、幂等 | v3 error_model, v3.1 escalation/reflection |
| **5. 运维与扩展** | 深度健康检查、FeatureFlag、统一 ID、多租户就绪 | v3 部分已做 |
| **6. 人机协同** | 关键动作确认、共规划、动作守卫、可回滚 | CHEQ, Magentic-UI, Sherlock |

---

## 二、当前状态：v3 + v3.1 已覆盖与未覆盖

### 已具备（v3）

- 统一错误模型（AgentError/category/severity）
- 任务状态机（显式生命周期）
- 并发限流与统一超时（TimeoutPolicy 全链路）
- 配置合并与后端结构清晰（config/, core/, docs）

### v3.1 计划内（完成后）

- 结构化 memory + 上下文压缩（`summarize_history_for_llm` 已占位）
- Plan-and-Execute 可选 + Replan
- Escalation 智能触发（embedding 相似度 + failure_type）
- 反思时机与模型（mid-loop + 可选 remote）
- 危险命令/工具统一校验 + action log 持久化
- Goal 重述与对齐

### v3.1 仍不足、需「v3.2+」补足的方向

下面按**六维度**列出：v3.1 更新后**还缺什么**才能达到标杆级。

---

## 三、差距分析：v3.1 之后还需什么

### 1. 架构与推理（部分达标，需补强）

| 能力 | v3.1 后状态 | 差距 | 建议 |
|------|-------------|------|------|
| Plan-and-Execute + Replan | v3.1 计划内有 | 需落地并做**可配置/可关闭**，便于 A/B 与 benchmark | 按 V3.1_PLAN 实施；增加 FeatureFlag `enable_plan_and_execute` |
| 结构化 / 长程 memory | 已有 `get_structured_history` + `summarize_history_for_llm` | 需**默认接入**（或 Flag 切换），并考虑「重要性加权」保留（不只最近 N 条） | 在 autonomous_agent 中接入 summarize；可选：重要失败/成功步优先保留 |
| 多智能体 / 协作 | 无 | 非必须；若要做「标杆级多智能体」，需单独路线图 | 可列为 v4 或更远期 |

**结论**：v3.1 落地后，架构与推理维度可达到**单智能体标杆**水平；多智能体为加分项。

---

### 2. 可观测与可评估（当前缺口最大）

| 能力 | v3.1 后状态 | 差距 | 建议 |
|------|-------------|------|------|
| **全链路 trace** | 仅有 action_log 与状态机；无统一「请求级 trace_id / span」 | 缺少 LLM 调用、tool 调用、子步骤的**统一 trace**，难以做成本/延迟归因 | 引入**轻量 trace 层**：每个 task 一个 trace_id，每次 LLM/tool 一个 span（含 model、tokens、latency、error）；可写 `data/traces/{trace_id}.json` 或对接 OpenTelemetry |
| **成本/延迟/成功率可测** | 无系统化采集 | 无法回答「单任务 token 消耗、P99 延迟、成功率」 | 在 trace 中记录 token_usage、latency_ms、success；聚合接口或脚本输出「每任务/每会话」统计 |
| **可复现 benchmark** | 无 | 无法像 SWE-bench 那样跑「同一批任务、同一配置」并比较前后版本 | 定义**内部 benchmark 集**（如 20 个典型任务 + 预期结果），跑一次产出「通过率 + 平均步数/ token」；CI 或手动跑，用于验证 v3.1/v3.2 不退化 |
| **执行轨迹持久化** | v3 规划/占位 | 与 trace 可合并：每任务 `data/executions/{task_id}.json` 含 prompt / tool_calls / results / stop_reason / model / tokens / latency | 落地 v3 执行轨迹，并和 trace 字段对齐 |

**结论**：**可观测与可评估**是冲击 2026 标杆的**关键短板**。v3.1 之后优先补：**trace + 执行轨迹持久化 + 内部 benchmark 套件**。

---

### 3. 安全与可控（部分有，需体系化）

| 能力 | v3.1 后状态 | 差距 | 建议 |
|------|-------------|------|------|
| 沙箱 | v3 规划/占位 | 文件与子进程未严格限制 | 落地**沙箱**：工具可写目录限制在 `backend/sandbox/`，subprocess 资源限制，命令白名单（与 v3 规划一致） |
| 统一审计 | v3 规划/占位 | 无系统级 who/action/tool/args/timestamp | 所有**副作用动作**（run_shell、call_tool、写文件等）写审计 log（可先写文件或后续接日志系统） |
| 危险动作拦截 | v3.1 计划内统一 validator | 需覆盖 call_tool 参数与自定义工具 | 在 `_execute_action` 统一做 `validate_action_safe`，并扩展至 call_tool |
| **HITL / 审批** | 无 | 无法「高危操作需用户确认后再执行」 | 可选：对部分 action_type 或 tool 标记 `requires_approval`，执行前通过 WS/API 向客户端请求确认，确认后再执行；或对接 CHEQ 类协议 |
| **回滚** | 无 | 错误后无法回滚到「上一验证点」 | 可选：对关键步骤做 checkpoint（如写文件前备份路径列表），验证失败时回滚；参考 Sherlock 的「验证失败回退到最后已验证输出」 |

**结论**：v3.1 补齐「统一校验 + action log 持久化」后，安全与可控可达**基础标杆**；**HITL 与回滚**为进阶项（v3.2+），用于「高敏感/高价值场景」标杆。

---

### 4. 鲁棒与自愈（v3 + v3.1 已较强）

| 能力 | v3.1 后状态 | 差距 | 建议 |
|------|-------------|------|------|
| 错误分类与统一模型 | ✅ v3 | — | 保持 |
| 智能 escalation | v3.1 计划内 | 落地 embedding 相似度 + 配置阈值 | 按 V3.1_PLAN 实施 |
| 反思与验证 | v3.1 计划内（mid-loop + remote） | 可选：**显式 verifier**（如执行前用轻量规则/模型做一步合法性检查） | 与「危险校验」结合即可；单独 verifier 可后续加 |
| 幂等 | v3 规划/占位 | 副作用接口未支持 idempotency_key | 对「写操作/发信/部署」等接口支持 idempotency_key，服务端缓存近期 key，重复请求返回原结果 |

**结论**：v3.1 完成后，鲁棒与自愈维度已接近标杆；补**幂等**即可更稳。

---

### 5. 运维与扩展（v3 已有基础）

| 能力 | v3.1 后状态 | 差距 | 建议 |
|------|-------------|------|------|
| 深度健康检查 | v3 规划/占位 | `/health/deep` 未实现 | 实现：检查 LLM 可用性、向量模型、Capsule、EvoMap、关键目录可写等 |
| FeatureFlag | 部分存在 | 与规划中的开关（plan_and_execute、reflection_remote、use_summarized_context）等对齐 | 集中到 config 或 app_state，文档化 |
| 统一 ID（UUID v7） | v3 规划/占位 | task_id 等仍为短 id | 可选：新任务/新会话用 UUID v7，便于分布式与排序 |
| 多租户 | 无 | 非单机标杆必需 | 可列为更远期 |

**结论**：实现 **/health/deep** 与 **FeatureFlag 体系化** 即可达到运维侧标杆预期。

---

### 6. 人机协同（当前缺失，属进阶）

| 能力 | v3.1 后状态 | 差距 | 建议 |
|------|-------------|------|------|
| 关键动作确认 | 无 | 无法「执行前弹窗确认」 | 定义「需确认」的 action 列表或规则，WS 下发 `pending_approval` 事件，客户端确认后服务端再执行 |
| 共规划 / 动作守卫 | 无 | 无法人类修改计划或拦截某步 | 可选：plan 生成后通过 UI 展示并允许编辑；或某步前发送「即将执行」事件，允许取消/修改 |
| 回滚 | 见上「安全与可控」 | — | 与安全回滚统一 |

**结论**：**人机协同**是「高可信/企业级」标杆的加分项；可在 v3.2 做**最小可行**：仅「高危操作需确认」+ 可选「任务级取消」。

---

## 四、v3.1 之后要达到「标杆级」的必做与选做

### 必做（无则难以对外称标杆）

1. **可观测与可评估**
   - **Trace 层**：task 级 trace_id，LLM/tool 级 span（model、tokens、latency、error）；落盘或对接 OTel。
   - **执行轨迹持久化**：每任务 `data/executions/{task_id}.json`（与 v3 规划一致），与 trace 字段对齐。
   - **内部 benchmark**：固定任务集 + 通过率/步数/token 统计，用于回归与对比。

2. **安全与可控**
   - **沙箱**：工具可写路径与 subprocess 限制（v3 规划）。
   - **统一审计**：所有副作用动作写审计 log（v3 规划）。
   - **统一危险校验**：v3.1 已计划，需覆盖 call_tool。

3. **运维**
   - **/health/deep**：LLM、向量、Capsule、EvoMap、磁盘等检查（v3 规划）。

### 选做（显著提升「标杆感」与可信度）

4. **幂等**：副作用接口 idempotency_key（v3 规划）。
5. **HITL 最小可行**：高危操作执行前需用户确认（WS 确认流）。
6. **FeatureFlag 体系化**：plan_and_execute、use_summarized_context、reflection_remote 等集中管理并文档化。
7. **回滚**：关键步骤 checkpoint + 验证失败回退（可先做「任务级取消」再演进到步骤级回滚）。

---

## 五、建议版本与节奏（对标 2026）

| 阶段 | 内容 | 目标 |
|------|------|------|
| **v3.1** | 按 V3.1_PLAN 落地：结构化 memory 接入、Plan-and-Execute、Escalation、反思、安全校验、Goal 重述 | 单智能体推理与鲁棒性达到标杆水平 |
| **v3.2** | Trace + 执行轨迹持久化 + 内部 benchmark 套件；/health/deep；沙箱 + 审计；幂等 | **可观测、可评估、安全与运维**达标，可对外说「可复现、可测」 |
| **v3.3 或 v4** | HITL 最小可行（高危确认）；FeatureFlag 体系化；可选回滚/任务取消 | **人机协同与可控性**达标，适合「高敏感/企业级」标杆叙事 |

---

## 六、一句话总结

- **v3**：底层稳固（错误模型、状态机、超时、并发、配置）。
- **v3.1**：推理与鲁棒达标（memory、规划、escalation、反思、安全校验、目标对齐）。
- **v3.1 之后要冲击 2026 标杆**，最关键的是：**可观测（trace + 执行轨迹）+ 可评估（benchmark 套件）+ 安全与运维（沙箱、审计、/health/deep）**；在此基础上再补幂等、HITL、回滚即可达到**标杆级 Agent 框架**的完整叙事。
