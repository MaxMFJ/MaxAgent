# Agent 任务执行与主 Duck / 分身 Duck 完整机制

本文档说明：主 Agent 与分身 Duck 的任务执行模型、主/分线程（任务类型）关系、委派与调度机制、当前架构缺陷，以及「主 Agent 忙时自动委派给 Duck」的完整设计与实现思路。

---

## 一、概念与术语

| 概念 | 含义 |
|------|------|
| **主 Agent** | 跑在主 Backend 上的唯一 Agent 实例，处理用户直接发起的 Chat / Autonomous 任务。 |
| **分身 Duck** | 独立进程或本机 LocalDuckWorker，向主 Backend 注册，接收主 Agent 委派的子任务并执行。 |
| **主线程任务** | 与「主 Agent 所在会话」绑定的任务，即 Chat 或 Autonomous，由主 Agent 在单 session 上串行执行。 |
| **分线程任务** | 由主 Agent 通过 `delegate_duck` 显式委派给 Duck 的子任务，在 Duck 侧异步执行，与主任务并行。 |
| **Session** | 会话 ID，一个用户/客户端对应一个 session_id，用于关联 Chat / Autonomous 任务与断线重连。 |

---

## 二、主 Agent 任务执行机制（主线程任务）

### 2.1 任务类型与入口

所有用户发起的任务都通过 **WebSocket `/ws`** 进入 `ws_handler.py`，按 `message.type` 分发：

| 消息类型 | Handler | 说明 |
|----------|---------|------|
| `chat` | `_handle_chat` | 流式对话，走 ChatRunner，可调用工具（含 `delegate_duck`） |
| `autonomous_task` | `_handle_autonomous_task` | 自主任务，走 AutonomousAgent.run_autonomous，可调用动作（含 `delegate_duck`） |

### 2.2 每 Session 同一时刻只有「一个 Chat + 一个 Autonomous」

- **Chat**：用 `session_stream_tasks[session_id]` 存当前流式任务的 `asyncio.Task`；新 Chat 到来会 **先 cancel 旧 Task**，再 `session_stream_tasks[session_id] = asyncio.create_task(_run_stream_and_send())`。
- **Autonomous**：用 `TaskTracker` 按 `(session_id, task_type=TaskType.AUTONOMOUS)` 注册；`tracker.register()` 时若该 session 已有 RUNNING 的 autonomous 任务，会 **先 cancel 其 asyncio_task**，再注册新任务。

因此：**同一 session 下，任意时刻最多一个正在执行的 Chat、一个正在执行的 Autonomous**；新任务会覆盖/取消同类型旧任务。

### 2.3 主线程任务的数据流

```
用户 → WS "chat" / "autonomous_task"
  → ws_handler._handle_chat / _handle_autonomous_task
  → session_stream_tasks (chat) 或 TaskTracker.register (autonomous)
  → ChatRunner.run_stream() 或 AutonomousAgent.run_autonomous()
  → 若 LLM 输出 delegate_duck → _handle_delegate_duck → DuckTaskScheduler.submit()
```

- **Chat**：`get_chat_runner().run_stream()`，内部会调用工具；若工具为 `delegate_duck`，则进入委派逻辑。
- **Autonomous**：`get_autonomous_agent().run_autonomous()`，内部按动作循环执行；若动作为 `delegate_duck`，则 `_handle_delegate_duck` → `DuckTaskScheduler.submit()`。

---

## 三、分身 Duck 与委派机制（分线程任务）

### 3.1 主 Duck vs 分身 Duck

| 角色 | 运行形态 | 职责 |
|------|----------|------|
| **主 Agent（主 Duck）** | 主 Backend 进程内的 AutonomousAgent + AgentCore | 处理用户直接发起的 Chat/Autonomous，并**显式**委派子任务给分身 |
| **分身 Duck** | 1）本机 LocalDuckWorker（同进程内队列） 2）远程 Duck 进程（WebSocket 连主 Backend） | 只执行主 Agent 下发的 TASK，不接用户直连任务 |

主 Backend 启动时 **不是** Duck 模式（`IS_DUCK_MODE=False`）；以 `DUCK_MODE=1` 启动的进程才是「分身」，会向主 Backend 的 Duck WebSocket 注册。

### 3.2 Duck 委派是「显式」的，没有自动分发

- 委派**仅**在以下情况发生：
  - 主 Agent 的 LLM 在 Chat 或 Autonomous 中**主动输出** `delegate_duck` 动作/工具调用；
  - 然后由 `AutonomousAgent._handle_delegate_duck` 或 Chat 侧 `DelegateDuckTool.execute` 调用 `DuckTaskScheduler.submit()`。
- **没有**以下逻辑：
  - 主 Agent 忙时，把「新用户任务」自动转给 Duck；
  - 任务队列 + 调度器根据「主 Agent 是否空闲」决定任务给主还是给 Duck。

因此：**主 Agent 忙时，新任务不会自动分配给 Duck**；新任务会走「同一 session 取消/覆盖旧任务」的路径，仍然由主 Agent 处理（或等待当前任务被取消后再执行新任务）。

### 3.3 委派后的完整链路

```
主 Agent 执行 delegate_duck
  → DuckTaskScheduler.submit(description, strategy, target_duck_id/type, callback, source_session_id)
  → _schedule_direct / _schedule_single / _schedule_multi
  → DuckRegistry.list_available(duck_type)  // 只选 ONLINE 且未 BUSY 的 Duck
  → _assign_to_duck(task, duck_id)
  → 本地: LocalDuckWorker.enqueue_task(payload)  远程: duck_ws.send_to_duck(TASK)
  → Duck 执行: AutonomousAgent.run(description) 或 run_autonomous
  → 完成: handle_result → callback / duck_task_complete 通知源 session
```

- **DuckRegistry**：维护所有 Duck 的注册、心跳、`current_task_id`；`list_available` 只返回 `status==ONLINE` 且未占用的 Duck（执行中会被设为 BUSY）。
- **DuckTaskScheduler**：任务持久化、策略（direct/single/multi）、超时、结果回调和 `duck_task_complete` 推送。
- **LocalDuckWorker**：本机 Duck，从内存队列取任务，用主 Backend 进程内的 `get_autonomous_agent()` 执行；远程 Duck 通过 WebSocket 收 TASK，在己方进程执行后再回传 RESULT。

---

## 四、当前架构小结（图）

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                    WebSocket /ws                         │
                    │         (chat | autonomous_task | resume_* | stop)       │
                    └───────────────────────────┬─────────────────────────────┘
                                                │
                    ┌───────────────────────────▼─────────────────────────────┐
                    │  ws_handler: 每 session 同时仅 1 个 Chat + 1 个 Autonomous   │
                    │  - chat → 先 cancel session_stream_tasks[sid]，再起新流    │
                    │  - autonomous_task → TaskTracker.register 先 cancel 旧再注册 │
                    └───────────────────────────┬─────────────────────────────┘
                                                │
         ┌─────────────────────────────────────┼─────────────────────────────────────┐
         │                                     ▼                                       │
         │  ┌──────────────────────────────────────────────────────────────────────┐  │
         │  │  主 Agent (主 Duck)                                                    │  │
         │  │  - ChatRunner.run_stream() / AutonomousAgent.run_autonomous()          │  │
         │  │  - 只有 LLM 显式输出 delegate_duck 时才委派                             │  │
         │  └─────────────────────────────────────┬────────────────────────────────┘  │
         │                                        │ delegate_duck                       │
         │                                        ▼                                     │
         │  ┌──────────────────────────────────────────────────────────────────────┐  │
         │  │  DuckTaskScheduler.submit()                                            │  │
         │  │  - 选 Duck: DuckRegistry.list_available()                              │  │
         │  │  - 不负责「该任务该不该给 Duck」的决策，只负责「委派请求来了就派活」      │  │
         │  └─────────────────────────────────────┬────────────────────────────────┘  │
         │                                        │                                     │
         └────────────────────────────────────────┼─────────────────────────────────────┘
                                                  │
                    ┌─────────────────────────────▼─────────────────────────────┐
                    │  Duck 侧（分身）                                            │
                    │  - 本地: LocalDuckWorker 队列 + AutonomousAgent.run()       │
                    │  - 远程: Duck WS 收 TASK → 执行 → RESULT 回传                │
                    └──────────────────────────────────────────────────────────┘
```

---

## 五、当前架构缺陷与问题

### 5.1 主 Agent 忙时，新任务不会自动给 Duck

- **现象**：用户在主 Agent 正跑一个长任务时再发一个新任务，新任务会 **cancel 当前主任务**（或覆盖注册），然后由主 Agent 执行新任务；不会自动把新任务交给空闲 Duck。
- **原因**：任务入口（`_handle_chat` / `_handle_autonomous_task`）没有「主 Agent 忙 → 查 Duck 可用 → 自动走 DuckTaskScheduler」的分支，委派完全依赖 LLM 的 `delegate_duck` 输出。

### 5.2 没有任务队列与调度策略

- 没有「待执行任务队列」：新任务要么在主 Agent 上执行（并可能取消当前任务），要么不执行；没有「排队等主 Agent 或 Duck 空闲」的抽象。
- DuckTaskScheduler 只做「委派请求已确定后的派发与结果回收」，不做「该请求该由主执行还是由 Duck 执行」的决策。

### 5.3 同一 Session 严格单任务

- 同一 session 同时只保留一个 Chat、一个 Autonomous；适合「单会话串行」，但不支持「同一用户多任务并行」（例如一个给主、一个给 Duck）。

---

## 六、完整设计：如何支持「主 Agent 忙时自动委派给 Duck」

### 6.1 目标行为

- 当 **新任务**（chat 或 autonomous_task）到达时：
  1. 若 **主 Agent 当前对该 session 空闲**：照旧由主 Agent 执行。
  2. 若 **主 Agent 当前对该 session 正在执行任务**：
     - 若有 **可用 Duck**：将新任务自动提交给 DuckTaskScheduler（等价于自动委派），不 cancel 主任务；
     - 若无可用 Duck：可选「排队等待」或「拒绝并提示用户」或「仍 cancel 主任务由主执行」（可配置）。

### 6.2 实现要点（在 ws_handler 任务入口增加调度层）

1. **判断「主 Agent 是否正在执行该 session 的任务」**
   - Chat：`session_id in session_stream_tasks and not session_stream_tasks[session_id].done()`；
   - Autonomous：`tracker.get_by_session(session_id, TaskType.AUTONOMOUS)` 且 `status == RUNNING`。
   - 可选：抽象为 `is_main_agent_busy(session_id)`，并区分 chat / autonomous 两种「忙」。

2. **主 Agent 忙时，查 Duck 是否可用**
   - `DuckRegistry.get_instance().list_available(duck_type=None)`（或按任务类型选 duck_type），若有结果则视为可自动委派。

3. **自动委派路径**
   - 不创建主 Agent 的 Chat 流 / Autonomous 协程；
   - 构造与当前 session 关联的「自动委派任务」，调用 `DuckTaskScheduler.submit(..., source_session_id=session_id)`；
   - 可选：对用户回复一条「任务已转交分身 Duck 执行」的提示，结果仍通过现有 `duck_task_complete` 等机制推回该 session。

4. **无可用 Duck 时的策略**
   - 策略 A：拒绝新任务，返回「主 Agent 忙且无可用 Duck，请稍后或稍后再试」；
   - 策略 B：将任务写入「待执行队列」，等主或 Duck 空闲时再调度（需要额外队列与 worker）；
   - 策略 C：保持现有行为，cancel 主任务并由主执行新任务（可通过配置开关选择）。

### 6.3 配置与扩展建议

- 在配置或环境变量中增加开关，例如 `AUTO_DELEGATE_WHEN_MAIN_BUSY=true`，仅当为 true 时走「忙则查 Duck → 自动委派」逻辑。
- 「自动委派」时建议打上来源标记（如 `auto_delegated=true`），便于日志与监控区分「用户/LLM 显式委派」与「系统自动委派」。
- 若未来引入任务队列，可将「新任务入口」统一为一个「任务提交 API」，先入队，再由统一调度器决定分配给主 Agent 还是 Duck，便于扩展多 Duck、优先级等。

---

## 七、实现方案 checklist（自动委派）

| 步骤 | 内容 |
|------|------|
| 1 | 在 `ws_handler` 中实现 `is_main_agent_busy(session_id, task_type)`（查 stream_tasks + TaskTracker）。 |
| 2 | 在 `_handle_chat` / `_handle_autonomous_task` 开头，若 `AUTO_DELEGATE_WHEN_MAIN_BUSY` 为 true 且主忙，则调用 `DuckRegistry.list_available()`。 |
| 3 | 若有可用 Duck，则调用 `DuckTaskScheduler.submit(..., source_session_id=session_id)`，并向前端返回「已转交 Duck」的 ack，不启动主 Agent 流/协程。 |
| 4 | 若无可用 Duck，按所选策略：拒绝 / 入队 / 或沿用当前「cancel 主任务并由主执行」。 |
| 5 | 配置项与日志：增加 `AUTO_DELEGATE_WHEN_MAIN_BUSY` 及自动委派时的日志与标记。 |

---

## 八、相关代码位置速查

| 模块 | 文件 | 说明 |
|------|------|------|
| WS 入口与 Chat/Autonomous 分发 | `ws_handler.py` | `_handle_chat`, `_handle_autonomous_task`, `session_stream_tasks` |
| 主 Agent 任务状态 | `app_state.py` | `TaskTracker`, `session_stream_tasks`, `get_task_tracker()` |
| 委派入口（Autonomous） | `agent/autonomous_agent.py` | `_handle_delegate_duck` |
| 委派工具（Chat） | `tools/delegate_duck_tool.py` | `DelegateDuckTool.execute` |
| 调度与派发 | `services/duck_task_scheduler.py` | `submit`, `_schedule_single`, `_assign_to_duck` |
| Duck 注册与可用性 | `services/duck_registry.py` | `list_available`, `set_current_task` |
| 本地 Duck 执行 | `services/local_duck_worker.py` | `enqueue_task`, `_execute_task` |
| 协议与状态 | `services/duck_protocol.py` | `DuckStatus`, `TaskStatus`, `DuckTaskPayload` |

---

本文档描述了当前「主/分线程任务」与「主 Duck / 分身 Duck」的完整机制、设计边界和「主 Agent 忙时自动委派给 Duck」的完整实现思路；按上述 checklist 即可在现有框架上实现自动委派，并保留后续队列与多 Duck 调度的扩展空间。
