# v3 升级检查报告

用于核对 Phase 2 与后续功能的接入状态，以及 v3 对主结构的影响评估。

---

## 一、Phase 1 状态（已落地）

| 项目 | 状态 | 说明 |
|------|------|------|
| 统一错误模型 | ✅ | `core/error_model.py`，`autonomous_agent` 异常处使用 `to_agent_error` 填充 error_id/category |
| 任务状态机 | ✅ | `core/task_state_machine.py`，`run_autonomous` 内状态迁移 + `task_state` chunk |
| 并发限流 | ✅ | `core/concurrency_limiter.py`，`ws_handler._autonomous_task_worker` 使用 `autonomous_slot()` |

**Token 消耗**：Phase 1 无新增 token（无回喂、无额外 LLM 调用）。

---

## 二、Phase 2：TimeoutPolicy 绑定情况

**结论**：`TimeoutPolicy` 已**全部绑定**到下列调用点；无 core 时各点 fallback 为原有硬编码超时或无限等待。

### 已绑定调用点清单

| 调用点 | 文件 | 状态 | 说明 |
|--------|------|------|------|
| **LLM 非流式** | `agent/llm_client.py` | ✅ | `chat()` 内 create 用 `get_timeout_policy().with_llm_timeout()` 包装 |
| **LLM 流式** | `agent/llm_client.py` | ✅ | `chat_stream()` 内 create 用 `with_llm_timeout()`；per-chunk 仍 90s |
| **ReAct 对话** | `agent/core.py` | ✅ | 通过 `self.llm.chat` / `chat_stream` 走 llm_client，已在 LLM 层统一 |
| **Tool 执行** | `tools/router.py` | ✅ | `reg.execute(...)` 用 `policy.with_tool_timeout()`，超时返回 ToolResult(error=...) |
| **自主 LLM 单次** | `agent/autonomous_agent.py` | ✅ | `_generate_action` 用 `get_timeout_policy().with_llm_timeout(chat_coro)`，无 policy 时 fallback 120s |
| **自主反思** | `agent/autonomous_agent.py` | ✅ | 反思请求用 `with_llm_timeout(..., timeout=60)`，无 policy 时 fallback 60s |
| **自主整任务** | `ws_handler` | ✅ | `_run_with_timeout()` 用 `asyncio.wait_for(..., policy.autonomous_timeout)`，超时发 error chunk 并通知 |

### 建议

上线前做**小规模集成测试**（一次对话、一次自主任务、一次工具调用），确认超时触发时前端收到明确错误、无挂死、无额外 token。

---

## 三、Phase 2 及后续：其他功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 执行轨迹持久化 | 📋 规划/占位 | 目标 `data/executions/{task_id}.json`，保存 prompt / tool_calls / tool_results / stop_reason / model；默认不回喂，不增加 token |
| 幂等机制 | 📋 规划/占位 | 副作用接口支持 `idempotency_key`，服务端缓存近期 key |
| 审计日志 | 📋 规划/占位 | 系统级 who/action/tool/args/timestamp 记录 |
| FeatureFlag | 📋 部分存在 | `app_state` 已有 ENABLE_EVOMAP、AUTO_TOOL_UPGRADE 等；与规划中的 vector_search/evomap/auto_upgrade/reflection/model_selection 可逐步对齐 |
| 深度健康检查 `/health/deep` | 📋 规划/占位 | LLM/向量/Capsule/EvoMap 等可用性检查 |
| 沙箱强化 | 📋 规划/占位 | 文件限制在 backend/sandbox/、subprocess 资源限制、命令白名单 |
| 统一 ID（UUID v7） | 📋 规划/占位 | session_id / task_id / tool_call_id 等 |
| 模型能力基线检测 | 📋 规划/占位 | 启动时检测 tool_calls/stream/usage/context 长度 |

**Token 注意**：执行轨迹默认不回喂；若启用「轨迹回喂」或更多「反思循环」策略，需单独评估 token 与成本。

---

## 四、v3 对主结构冲击评估

### 结论：**对主结构无破坏性冲击，为增量叠加。**

| 方面 | 说明 |
|------|------|
| **入口与路由** | `main.py`、`ws_handler.py`、`routes/` 未改协议、未删接口；仅在 `ws_handler` 中增加对 `get_concurrency_limiter()` 的可选使用（try/import，失败则不限流）。 |
| **Agent 核心** | `agent/core.py`（ReAct）、`agent/autonomous_agent.py` 未改对外接口；autonomous 内对 `TaskStateMachine`、`to_agent_error` 为 **try 导入、无则跳过**，无 core 包时行为与升级前一致。 |
| **配置与状态** | `config/` 仅为原根目录 4 个 config 文件的物理合并，读写路径仍为 `backend/data/`，对主流程无逻辑变更。 |
| **依赖方向** | 主结构依赖 `agent`、`routes`、`tools`；v3 的 `core` 只被 `agent/autonomous_agent` 与 `ws_handler` 可选引用，**无反向依赖**，不形成循环。 |
| **兼容性** | 未安装或移除 `core` 包时，现有逻辑仍可运行（状态机与错误模型退化为不启用，限流退化为不限制）。 |

### 建议

- Phase 2 的 TimeoutPolicy 绑定建议在 **LLM/Tool 单一入口** 完成（如 `llm_client`、`router.execute_tool`），避免在大量散点重复写超时逻辑。
- 执行轨迹、幂等、审计、FeatureFlag 等建议**按需、分阶段**接入，每步做小规模集成测试，确认无阻塞、无额外 token 后再铺开。

---

## 五、Phase 2 上线前建议

1. **TimeoutPolicy**：✅ 已完成 LLM / Tool / Autonomous 全链路绑定；建议跑通一次 Chat + 一次自主任务 + 一次工具调用（含一次故意超时场景）。
2. **回归**：确认现有对话、自主任务、自愈/升级流程无回归。
3. **Token**：若启用轨迹回喂或更多反思策略，需单独评估并配置开关。
4. **文档**：本检查报告与 `V3_UPGRADE.md` 保持一致，随后续功能接入更新「其他功能」表格。
