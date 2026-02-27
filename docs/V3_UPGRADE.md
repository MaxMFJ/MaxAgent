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

## Git 本地版本

在仓库根目录执行，为当前提交打 v3 标签（仅本地）：

```bash
git tag v3
# 或带注释: git tag -a v3 -m "v3 core: 统一错误模型、任务状态机、并发限流"
```

查看标签：`git tag -l`。推送标签（可选）：`git push origin v3`。
