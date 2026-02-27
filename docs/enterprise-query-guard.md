# 企业级 Query 分级与 Execution Guard

## 1. Query 分级（静态规则 + ML 占位）

- **模块**：`agent/query_classifier.py`
- **意图**：`Intent.EXECUTION` | `INFORMATION` | `GREETING` | `UNKNOWN`
- **层级**：`QueryTier.SIMPLE`（LITE prompt）/ `QueryTier.COMPLEX`（FULL prompt）
- **流程**：优先 ML（`QUERY_CLASSIFIER_ML_ENABLED=true` 时），否则静态规则。
- **扩展**：在 `_classify_with_ml()` 中接入本地/远程分类器；静态规则在 `_classify_static()` 中可配置化扩展。

## 2. 分层 Prompt（FULL vs LITE）

- **LITE**：简单对话、信息追问、问候；提示模型「根据历史回答、不要执行创建/命令」。
- **FULL**：需要工具调用的复杂任务。
- **Intent 注入**：在 `get_system_prompt_for_query()` 中根据 `Intent` 追加 `[当前判定：...]`，显式约束行为。

## 3. Execution Guard

- **模块**：`agent/execution_guard.py`
- **逻辑**：当 `intent == INFORMATION` 时，对写/执行类工具（如 write_file、run_shell、create_and_run_script）禁止执行，返回占位结果并提示模型「根据对话历史直接回答」。
- **接入**：在 `AgentCore.run_stream` 中，执行工具前按 `intent_result.intent` 与工具名调用 `guard_check()`，对被拦截的调用注入 `ToolResult(success=False, error=...)`，不真实执行。

## 4. 向量检索增强上下文

- **保障**：`context_manager.get_context_messages()` 在从磁盘加载会话时会 `_sync_recent_to_vector_store()`，保证 BGE 有完整历史可检索；返回过少时回退到 `recent_messages`。
- **效果**：纯追问（如「项目目录在哪里」）能拿到足够历史，配合 Guard 与分层 Prompt 减少误执行。

## 5. 日志与监控

- **Query 分级**：每次 `classify()` 打结构化日志（intent、tier、source、query_preview）；可选写入 `data/query_classifier_metrics.jsonl`（`ENABLE_QUERY_METRICS_LOG=true`）。
- **Execution Guard**：每次 `check()` 可选写入 `data/execution_guard_metrics.jsonl`。
- **用途**：规则调优、ML 训练样本、监控拦截率与误判率。

### 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `ENABLE_QUERY_METRICS_LOG` | 是否写入 query/guard 的 jsonl 日志 | `true` |
| `QUERY_METRICS_DIR` | 日志目录 | `backend/data` |
| `QUERY_CLASSIFIER_ML_ENABLED` | 是否启用 ML 分类器（占位） | `false` |
