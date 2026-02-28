# MacAgent v3 本地版本说明

v3 为**修复底层框架缺陷**的升级，**融合在现有代码中**，不做单独 v3 分支或封装。

## 已实现（Phase 1）

- **统一错误模型** `backend/core/error_model.py`  
  `AgentError`、`ErrorCategory`、`ErrorSeverity`、`to_agent_error()`，自愈与日志可统一使用。

- **任务状态机** `backend/core/task_state_machine.py`  
  `TaskState`：PENDING → RUNNING → WAITING_TOOL → REFLECTING → RETRYING → COMPLETED | FAILED | TIMEOUT | ABORTED。  
  `AutonomousAgent.run_autonomous` 在关键节点做状态迁移，并产出 `task_state` chunk 便于观测。

- **并发限流** `backend/core/concurrency_limiter.py`  
  `MAX_CONCURRENT_AUTONOMOUS=2`、`MAX_CONCURRENT_LLM=4`，通过 `asyncio.Semaphore` 控制。  
  自主任务入口在 `ws_handler._autonomous_task_worker` 中通过 `autonomous_slot()` 限流。

## Phase 2：TimeoutPolicy 已融合

- **统一超时策略** `backend/core/timeout_policy.py`  
  `TimeoutPolicy` 已绑定：`llm_client.chat/chat_stream`、`tools/router.execute_tool`、`autonomous_agent` 内 LLM/反思、`ws_handler` 自主任务整体 `autonomous_timeout`。详见 [v3 升级检查报告](V3_UPGRADE_CHECK.md)。

- 执行轨迹持久化、幂等机制、审计日志、FeatureFlag 等见顶层 V3 Core Upgrade Plan；当前状态见 [V3_UPGRADE_CHECK.md](V3_UPGRADE_CHECK.md)。

## v3.1 已实现

- **结构化 memory + 上下文压缩**：`context.summarize_history_for_llm()` 已接入（`USE_SUMMARIZED_CONTEXT` 默认 true），Goal 重述每 `GOAL_RESTATE_EVERY_N` 步。
- **Plan-and-Execute**：`ENABLE_PLAN_AND_EXECUTE` 时先生成子任务列表，执行中展示当前建议子目标，失败升级时 Replan。
- **Escalation 智能触发**：基于 BGE embedding 相似度 + `ESCALATION_*` 配置，fallback 到 md5。
- **中途反思**：`ENABLE_MID_LOOP_REFLECTION` 时每 N 步或连续失败触发轻量反思，结果注入下一轮 prompt。
- **统一安全校验**：`agent/safety.py` 在 `_execute_action` 入口做危险命令/路径/工具参数校验。
详见 [V3.1_PLAN.md](V3.1_PLAN.md)。

## 冲击 2026 标杆级 Agent（v3.1 之后还需什么）

见 [ROADMAP_2026_BENCHMARK_AGENT.md](ROADMAP_2026_BENCHMARK_AGENT.md)：六维度差距分析（架构/可观测/安全/鲁棒/运维/人机协同），v3.2 必做（trace、执行轨迹、benchmark、沙箱、审计、/health/deep）与选做（幂等、HITL、回滚），以及版本节奏建议。

## Git 本地版本

在仓库根目录执行，为当前提交打 v3 标签（仅本地）：

```bash
git tag v3
# 或带注释: git tag -a v3 -m "v3 core: 统一错误模型、任务状态机、并发限流"
```

查看标签：`git tag -l`。推送标签（可选）：`git push origin v3`。
