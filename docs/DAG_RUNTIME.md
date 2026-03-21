# DAG Runtime — Duck Agent 分布式任务运行时

> 版本: v3.0 Final | 最后更新: 2025-01

## 概述

DAG Runtime 是 MacAgent 的核心子系统，负责将复杂任务拆解为 **有向无环图（DAG）** 并通过多个专职 Duck Agent 并行执行。系统从 v1（事件推送）演进至 v3.0（分布式 Pull 协议 + 完整可观测性），具备生产级可靠性。

---

## 架构总览

```
┌──────────────────────────────────────────────────────────┐
│                    Main Agent (编排层)                     │
│  - 用户对话理解 → 任务拆解 → DAG 构建                        │
└────────────────────────┬─────────────────────────────────┘
                         │ create_dag()
                         ▼
┌──────────────────────────────────────────────────────────┐
│               DAGTaskOrchestrator (DAG 引擎)              │
│  - 依赖解析 + remaining_deps 计数器                        │
│  - 就绪节点 → Ready Queues                                │
│  - 回调驱动: 子节点完成 → 解锁下游 → 入队                    │
│  - 防重放: execution_emitted 标志                          │
│  - 慢 DAG 检测: p95 × 3 阈值                              │
└────────────────────────┬─────────────────────────────────┘
                         │ enqueue_ready_node()
                         ▼
┌──────────────────────────────────────────────────────────┐
│              Duck Ready Queues (Pull 调度层)               │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌─────────┐       │
│  │ coder   │ │ crawler │ │ designer │ │ general │ ...    │
│  │ Queue   │ │ Queue   │ │ Queue    │ │ Queue   │       │
│  │ max=100 │ │ max=100 │ │ max=100  │ │ max=100 │       │
│  └────┬────┘ └────┬────┘ └────┬─────┘ └────┬────┘       │
│       │           │           │             │            │
│  Overflow Pending (溢出暂存 → 5s drain loop)              │
│  Fair Round-Robin (加权轮转跨类型协助)                      │
│  Adaptive Backpressure (压力 > 0.8 → RETRY_LATER)        │
└────────────────────────┬─────────────────────────────────┘
                         │ worker_pull_loop()
                         ▼
┌──────────────────────────────────────────────────────────┐
│                  Duck Workers (执行层)                     │
│                                                          │
│  本地 Duck          远程 Duck (v3.0)                       │
│  ┌──────────┐      ┌───────────────────────┐             │
│  │ coder    │      │ HTTP Pull Protocol    │             │
│  │ crawler  │      │ POST /workers/pull    │             │
│  │ designer │      │ POST /workers/complete│             │
│  │ tester   │      │ Bearer Token Auth     │             │
│  └──────────┘      └───────────────────────┘             │
└──────────────────────────────────────────────────────────┘
```

---

## 核心组件

### 1. 任务状态机 (`duck_protocol.py`)

```
   CREATED → PENDING → ENQUEUED → ASSIGNED → RUNNING → COMPLETED
                │          │         │          │
                │          │         │          └→ FAILED
                │          │         └→ FAILED_TEMP → PENDING (重试)
                │          └→ PENDING (reschedule)
                └→ CANCELLED
```

| 状态 | 含义 |
|------|------|
| CREATED | 任务对象刚创建 |
| PENDING | 等待调度分配 |
| ENQUEUED | 已入 Ready Queue，等待 Worker Pull |
| ASSIGNED | 已分配给 Duck，等待确认 |
| RUNNING | Duck 正在执行 |
| COMPLETED | 执行成功（终态）|
| FAILED | 最终失败（终态）|
| FAILED_TEMP | 临时失败，可重试 |
| CANCELLED | 已取消（终态）|

状态转换由 `_VALID_TRANSITIONS` 表严格约束，`transition_task()` 验证合法性。

### 2. DAG 引擎 (`duck_task_dag.py`)

**DAGNode** — DAG 中的子任务节点：
- `depends_on`: 前驱节点 ID 列表
- `remaining_deps`: 未完成的依赖计数（原子递减）
- `input_mapping`: 上游输出到本节点参数的映射
- `execution_emitted`: 防重放标志

**DAGExecution** — 一次 DAG 执行实例：
- 状态: pending → running → completed / failed
- 包含所有 DAGNode 及其运行时状态

**执行流程**:
1. `create_dag()` 初始化 → 计算 `remaining_deps` → 入队根节点
2. 根节点执行完成 → `_decrement_and_enqueue()` 递减下游依赖
3. `remaining_deps == 0` 的节点自动入队
4. 所有节点完成 / 任何关键节点失败 → DAG 完成

### 3. Pull-Based Ready Queues (`duck_ready_queues.py`)

**核心设计**: Worker 主动拉取任务，而非被动推送。

- **Bounded Queue**: 每个 duck_type 一个 `asyncio.Queue(maxsize=100)`
- **Overflow Pending**: 队列满时溢出到暂存列表，5s 定期 drain
- **Fair Round-Robin**: 加权轮转跨类型协助（coder: 2, 其他: 1）
- **Worker Pull Loop**: 每个 Duck 一个 `worker_pull_loop()` 协程
  - 优先从自身类型队列 pull（2s 超时）
  - 超时后通过 `fair_select_queue()` 从其他队列协助

### 4. 调度器 (`duck_task_scheduler.py`)

- **提交**: `submit()` 创建任务 → 按策略调度（direct / single / multi）
- **分配**: `_assign_to_duck()` 设置 ASSIGNED + 启动 lease timeout watcher
- **结果**: `handle_result()` 幂等处理（终态检查） → 指标记录 → 回调触发
- **Watchdog**: 20s 周期扫描 PENDING 任务 → 触发 reschedule
- **Lease Scanner**: 10s 扫描，120s 超时 → 僵尸任务重排队
- **自动重试**: 失败任务检查 retry_count < max_retries → 重新调度

### 5. Duck Registry (`duck_registry.py`)

- 管理所有 Duck Agent 的注册/注销/心跳
- `on_duck_available()` 钩子：Duck 空闲时立即触发 reschedule
- `set_current_task()` 状态翻转时发射可用事件

---

## 可靠性保障

### Runtime Journal (`runtime_journal.py`)

**Append-only JSON Lines** — 记录所有状态转换事件：

```json
{"ts": 1706000000, "event": "TASK_CREATED", "task_id": "abc123", "extra": {"strategy": "single"}}
{"ts": 1706000001, "event": "TASK_ASSIGNED", "task_id": "abc123", "duck_id": "duck_coder_1"}
{"ts": 1706000010, "event": "TASK_COMPLETED", "task_id": "abc123", "duck_id": "duck_coder_1"}
```

事件类型: `TASK_CREATED`, `TASK_ENQUEUED`, `TASK_ASSIGNED`, `TASK_COMPLETED`, `TASK_FAILED`, `LEASE_EXPIRED`, `DAG_CREATED`, `DAG_COMPLETED`

**崩溃恢复**: `recover_runtime_state()` 从 journal 重建内存状态：
- ASSIGNED / RUNNING 的任务 → 重置为 PENDING
- 已完成的任务 → 跳过

**Journal Compaction**: 每 10 分钟压缩，仅保留每个 task/DAG 的最新事件（原子 rename）。

### 幂等完成守卫

`handle_result()` 检查任务是否已在终态（COMPLETED / FAILED / CANCELLED），如是则直接丢弃重复结果，防止重复回调。

### Replay Protection

DAGNode 的 `execution_emitted` 标志确保每个节点只被入队一次。防止依赖递减中的竞态导致重复执行。

### Worker Lease 超时

- **Lease Scanner**: 10s 间隔扫描所有 ASSIGNED / RUNNING 任务
- **超时阈值**: 120s 无活跃信号 → 释放 Duck + 任务重排队
- **重试预算**: `retry_count < max_retries` → PENDING 重试；否则 FAILED

---

## 自适应调度

### 背压控制 (v2.3)

```
pressure = queue_fill_ratio × 0.5 + active_workers_ratio × 0.3 + retry_rate × 0.2
```

- `pressure > 0.8` → DAG 入口拒绝新节点（返回 RETRY_LATER）
- queue_fill_ratio = 已用容量 / 总容量（含 overflow）
- retry_rate 从 RuntimeMetrics 获取

### Worker 健康评分 (v2.3)

```
health = success_rate × 0.6 + (1 - exec_penalty) × 0.2 + (1 - lease_penalty) × 0.2
```

- `health < 0.3` → 自动隔离（quarantine 5 分钟，停止 pull loop）
- 隔离期间 worker 不参与任务调度
- exec_penalty: Duck 平均执行时间 / 全局平均 × 3
- lease_penalty: lease 过期次数 / 总任务数 × 5

### 慢 DAG 检测 (v2.3)

- 记录最近 100 个 DAG 执行时间
- 当某 DAG 执行时间 > p95 × 3 → 标记为 slow DAG
- 计入 `slow_dag_count` 指标

---

## 分布式执行 (v3.0)

### Remote Pull Protocol

远程 Worker 通过 HTTP API 拉取任务，无需 WebSocket 长连接。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/workers/register` | POST | 注册远程 Worker |
| `/workers/pull` | POST | 拉取一个任务（204 = 无任务）|
| `/workers/heartbeat` | POST | 心跳 + 续约 lease |
| `/workers/complete` | POST | 提交执行结果 |

**认证**: Bearer Token（环境变量 `DUCK_WORKER_TOKEN`）

**远程 Worker 参考客户端**: `workers/remote_worker.py`
```bash
python workers/remote_worker.py \
  --server http://host:8765 \
  --worker-id my-worker \
  --duck-type coder \
  --token <DUCK_WORKER_TOKEN>
```

---

## 可观测性 (v3.0 Final)

### 运行时指标 (`runtime_metrics.py`)

| 指标 | 说明 |
|------|------|
| total_tasks_executed | 已执行任务总数 |
| total_tasks_failed | 失败任务总数 |
| total_retries | 重试总次数 |
| lease_expired_count | lease 过期次数 |
| backpressure_count | 背压触发次数 |
| retry_exhausted_count | 重试预算耗尽次数 |
| slow_dag_count | 慢 DAG 检测次数 |
| remote_pull_count | 远程 Pull 次数 |

指标每 30s 持久化为 JSON snapshot（`data/runtime_metrics_snapshot.json`）。

### 健康端点 (`GET /runtime/health`)

返回系统就绪状态：

```json
{
  "status": "OK",
  "reasons": [],
  "pressure": 0.23,
  "active_workers": 3,
  "queue_sizes": {"coder": 2, "general": 0},
  "suspected_stuck_tasks": 0,
  "overflow_total": 0,
  ...
}
```

**就绪等级**:
| 等级 | 条件 |
|------|------|
| OK | 无告警 |
| DEGRADED | 重试耗尽 / stuck 任务 / 降级 worker / 高压力 (0.8-0.95) |
| CRITICAL | 无活跃 worker / overflow 增长 / lease 过期激增 / 极端压力 (>0.95) |

### 任务解释 (`GET /runtime/task/{task_id}`)

单任务深度诊断：状态、归属 Duck、重试次数、排队等待时间、执行时间、最近 10 条 journal 事件。

### 队列状态 (`GET /runtime/queues`)

各类型队列的容量、使用率、溢出量、活跃 pull loop。

### Worker 诊断 (`GET /runtime/workers`)

每个 Duck Worker 的详情：类型、健康评分、lease 剩余、隔离状态、worker 状态分类（HEALTHY / STALE / LOST / QUARANTINED / DEGRADED）。

### Stuck Task Detector

后台 30s 周期扫描：
- ASSIGNED / RUNNING 且无活跃信号超过 `lease_timeout × 0.8` → 标记为 suspected stuck
- 结果反映在 `/runtime/health` 的 `suspected_stuck_tasks` 和就绪等级中

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `services/duck_protocol.py` | 消息类型、Duck/Task 状态机 |
| `services/duck_registry.py` | Duck Agent 注册/发现 |
| `services/duck_task_scheduler.py` | 任务调度引擎 |
| `services/duck_task_dag.py` | DAG 编排引擎 |
| `services/duck_ready_queues.py` | Pull-Based Ready Queues |
| `services/runtime_metrics.py` | 运行时指标收集器 |
| `services/runtime_journal.py` | Append-only 执行日志 |
| `services/runtime_health.py` | 健康快照 & 诊断函数 |
| `services/remote_pull_protocol.py` | 远程 Pull 协议核心逻辑 |
| `routes/runtime_health.py` | 健康/诊断 API 端点 |
| `routes/remote_workers.py` | 远程 Worker API 端点 |
| `workers/remote_worker.py` | 远程 Worker 参考客户端 |

---

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `DEFAULT_QUEUE_MAXSIZE` | 100 | 每个 duck_type 队列容量 |
| `PRESSURE_THRESHOLD` | 0.8 | 背压拒绝阈值 |
| `_lease_timeout` | 120s | Worker lease 超时 |
| `_lease_scan_interval` | 10s | Lease 扫描间隔 |
| `_watchdog_interval` | 20s | Pending 任务 watchdog 间隔 |
| `_QUARANTINE_COOLDOWN` | 300s | 隔离冷却时间 |
| `DUCK_WORKER_TOKEN` | (env) | 远程 Worker 认证 Token |

---

## 版本演进

| 版本 | 里程碑 |
|------|--------|
| v1.0 | 事件推送调度 + Duck可用钩子 + Watchdog |
| v2.0 | Pull-Based Ready Queues + remaining_deps 计数器 |
| v2.1 | 背压控制 + Worker Lease + 公平调度 + 指标持久化 |
| v2.2 | 状态机 + 幂等守卫 + Journal + 崩溃恢复 + 防重放 |
| v2.3 | 自适应背压 + Worker 健康评分 + Journal 压缩 + 慢 DAG |
| v3.0 | Remote Pull Protocol + Bearer 认证 + 远程指标 |
| v3.0 Final | Task Explain + Queue State + Worker 诊断 + Stuck 检测 + 就绪等级 |
