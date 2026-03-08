# Chow Duck 分身逻辑完整检查报告

本文档输出 Chow Duck 分身全流程、各子 Duck 运转/失败逻辑，并针对用户任务「设计无畏契约战绩分析网页设计图 PNG + 制作 HTML」进行完成性预测。

---

## 一、全流程概览

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 1. 用户 Chat 消息                                                                 │
│    "设计一个 无畏契约战绩分析的 网页设计图 png 只要主页 然后 去制作html"            │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 2. ws_handler._handle_chat                                                       │
│    - query_classifier: "设计一个"、"制作" → EXECUTION + COMPLEX tier              │
│    - session_stream_tasks[session_id] = asyncio.create_task(_run_stream_and_send) │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 3. ChatRunner.run_stream(session_id)                                             │
│    - LLM 可选: duck_status / delegate_duck / file_operations / terminal 等         │
│    - tools.md 规定: 网页设计、视觉设计、HTML 制作 → 必须优先 delegate_duck          │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 4. DelegateDuckTool.execute / AutonomousAgent._handle_delegate_duck                │
│    - 注入 actual_desktop_path 到 description                                     │
│    - DuckTaskScheduler.submit(description, duck_type, source_session_id)         │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 5. DuckTaskScheduler.submit                                                       │
│    - 持久化到 data/duck_tasks/dtask_xxx.json                                     │
│    - _schedule_single / _schedule_direct / _schedule_multi                        │
│    - DuckRegistry.list_available(duck_type) → 仅 ONLINE 且未 BUSY 的 Duck          │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 6. _assign_to_duck(task, duck_id)                                                │
│    - 本地 Duck: LocalDuckWorker.enqueue_task(payload)                             │
│    - 远程 Duck: duck_ws.send_to_duck(duck_id, TASK)                               │
│    - registry.set_current_task(duck_id, task_id) → Duck 变为 BUSY                   │
│    - 启动 _timeout_watcher(task.timeout + 120s)                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐
│ 7a. Local Duck (LocalDuckWorker)      │  │ 7b. 远程 Duck (duck_ws)               │
│ - _run_loop: 每 5s 取队列任务          │  │ - WebSocket 收 TASK 消息               │
│ - _execute_task → _do_work_with_      │  │ - 本地进程执行 run_autonomous          │
│   monitoring                           │  │ - 回传 RESULT 到主 Backend              │
│ - get_autonomous_agent().run_         │  │                                        │
│   autonomous(description)              │  │                                        │
└──────────────────────────────────────┘  └──────────────────────────────────────┘
                    │                                       │
                    └───────────────────┬───────────────────┘
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 8. Duck 执行 (AutonomousAgent.run_autonomous)                                    │
│    - 注入 Duck 身份: name, duck_type, skills                                      │
│    - 可选 override_llm（分身独立 LLM 配置）                                       │
│    - 流式 chunk 广播到 source_session 的监控面板                                  │
│    - 工具: terminal, file_operations, screenshot, web_search, delegate_duck 等    │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 9. 任务完成 / 失败                                                                │
│    - Local: scheduler.handle_result(duck_id, DuckResultPayload)                   │
│    - 远程: duck_ws._handle_result → scheduler.handle_result                       │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 10. handle_result 逻辑                                                            │
│     - 成功: registry.set_current_task(duck_id, None), increment_completed         │
│     - 失败且 retry_count < max_retries: _auto_retry_task → 重新 _assign_to_duck    │
│     - 失败且耗尽重试: _notify_session_duck_complete(success=False)                │
│     - 成功: _notify_session_duck_complete(success=True)                           │
│     - 提取 created_paths → context_manager.add_created_file / add_duck_output     │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 11. 广播 duck_task_complete 到 session                                            │
│     - connection_manager.broadcast_to_session(session_id, msg)                    │
│     - ctx_mgr.add_message("assistant", content)                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 12. _on_duck_task_complete 钩子 (ws_handler 注册)                                 │
│     - 若主 Agent 忙 → 不插队，直接 return                                         │
│     - 若失败: _run_agent_and_broadcast_result(失败通知) → 主 Agent 亲自处理        │
│     - 若成功: _run_agent_and_broadcast_result(续步提示) → 主 Agent 判断下一步     │
│       - 续步提示含: 工作区产出、文件路径、是否需 delegate_duck 下一步               │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 13. 主 Agent 续步 (ChatRunner.run_stream)                                         │
│     - 若还有待执行步骤（如设计图→HTML）: 再次 delegate_duck(引用设计图路径)       │
│     - 若全部完成: 向用户汇报最终产出与文件路径                                      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、各子 Duck 运转逻辑

### 2.1 本地 Duck (LocalDuckWorker)

| 阶段 | 逻辑 |
|------|------|
| **启动** | `start()` → 注册到 DuckRegistry(ONLINE) → `_run_loop()` 协程 |
| **取任务** | `asyncio.wait_for(_task_queue.get(), 5.0)`，超时则 `heartbeat(duck_id)` |
| **执行** | `_do_work_with_monitoring` → `set_duck_context` → `agent.run_autonomous(description)` |
| **流式** | 每个 chunk 广播到 `source_session`，`last_active` 更新 |
| **超时** | 每 20s 检查：`inactivity > 90s` → 卡死取消；`now >= hard_deadline` → 总超时取消 |
| **结果检测** | `_check_output_is_plan_not_result`：若返回计划而非结果 → 重试一次（强制执行模式） |
| **降级** | Agent 失败且任务**不涉及**文件创建 → 用 LLM 纯对话补全；涉及文件创建 → 直接抛错 |

### 2.2 远程 Duck (duck_ws)

| 阶段 | 逻辑 |
|------|------|
| **连接** | WebSocket `/duck/ws?token=xxx&duck_id=xxx` |
| **注册** | `REGISTER` → `registry.register(info)` → `reschedule_pending()` 分配 PENDING 任务 |
| **心跳** | 主 Backend 每 30s 发 PING；Duck 发 HEARTBEAT → `registry.heartbeat(duck_id)` |
| **收任务** | `TASK` 消息 → Duck 进程执行 → 回传 `RESULT` |
| **断线** | `finally` 中 `set_status(duck_id, OFFLINE)` |

### 2.3 DuckRegistry.list_available

```python
# 仅返回 status == ONLINE 的 Duck（BUSY 不返回）
if d.status != DuckStatus.ONLINE:
    continue
if duck_type and d.duck_type != duck_type:
    continue
```

- **ONLINE** = 空闲可接任务  
- **BUSY** = 正在执行，不参与 `list_available`  
- **OFFLINE** = 离线

---

## 三、失败逻辑

### 3.1 调度器层 (DuckTaskScheduler)

| 场景 | 处理 |
|------|------|
| **无可用 Duck** | 任务保持 PENDING，等 Duck 上线后 `reschedule_pending()` 重新分配 |
| **发送失败** | 任务回退 PENDING，`assigned_duck_id=None`，释放 Duck |
| **超时** | `_timeout_watcher` 超时 → `_fail_task` → 通知 session |
| **Duck 返回失败** | `retry_count < max_retries(2)` → `_auto_retry_task` 增强描述后重新分配 |
| **耗尽重试** | `_notify_session_duck_complete(success=False)`，触发续步钩子 |

### 3.2 自动重试 (_auto_retry_task)

- 第 1 次：增强描述「立即使用工具直接操作，不要先描述计划」
- 第 2 次：更强指令「换一种方式：run_shell 安装依赖、write_file 写脚本、执行」
- 重试时：`_notify_main_agent_retry` 广播 `duck_task_retry` 给 session

### 3.3 Local Duck 层

| 场景 | 处理 |
|------|------|
| **返回计划而非结果** | 第一次重试（强制执行模式）；第二次仍为计划 → `RuntimeError` |
| **总超时** | `TimeoutError` → `RuntimeError(str(e))` |
| **90s 无 chunk** | 判定卡死 → `TimeoutError` |
| **Agent 异常** | 若任务涉及文件创建 → 直接抛错；否则 LLM 降级补全 |

### 3.4 续步钩子（失败时）

```
[系统通知] Duck 子任务执行失败
失败的 Duck：xxx
任务描述：xxx
失败原因：xxx

⚡ 你现在必须亲自处理此任务（Duck 已多次尝试失败）：
1. 创建 HTML/代码/文档：直接用 write_file，不要再委派 Duck
2. 运行脚本：用 terminal
3. 完成后向用户汇报实际文件路径
⚠️ 禁止再次 delegate_duck 相同内容
```

主 Agent 会收到上述提示并执行 `_run_agent_and_broadcast_result`，用工具完成任务后广播给用户。

---

## 四、用户任务完成性预测

**用户输入**：`设计一个 无畏契约战绩分析的 网页设计图 png 只要主页 然后 去制作html`

### 4.1 任务拆解

| 步骤 | 内容 | 预期 Duck 类型 | 所需能力 |
|------|------|----------------|----------|
| 1 | 设计无畏契约战绩分析网页设计图（PNG，主页） | designer / image | 生成 PNG 图片 |
| 2 | 根据设计图制作 HTML | coder | write_file 写 HTML/CSS |

### 4.2 串行依赖

- 步骤 2 依赖步骤 1 产出的 PNG 路径
- tools.md 规定：必须串行委派，先 designer 完成，再 coder 用**完整路径**委派

### 4.3 潜在问题

#### 问题 1：PNG 设计图生成能力缺失

- **Designer Duck** 模板 `required_tools=["image_gen", "file_edit"]`
- **Image Duck** 模板 `required_tools=["image_gen", "image_process"]`
- 当前 Backend **没有** `image_gen` 工具（无文生图 API 集成）
- Designer/Image Duck 实际只有 `file_operations`、`terminal`、`screenshot` 等通用工具

**影响**：Designer Duck 无法直接「文生图」生成 PNG，只能通过：
- `run_shell` + Python 脚本（如 PIL、matplotlib）画图
- `write_file` 写 HTML+CSS 布局，再用 headless 浏览器截图导出 PNG
- 或仅输出 HTML 原型，不生成 PNG

#### 问题 2：Duck 可能只输出计划

- `_check_output_is_plan_not_result` 会检测「只描述计划未执行」
- 若 Designer 只输出「我将设计一个包含…的页面」而未实际写文件，会被判失败并重试
- 重试后若仍无文件产出，最终失败，主 Agent 接管

#### 问题 3：续步路径依赖文件路径

- 续步提示依赖 `_extract_file_paths_from_output` 从 Duck 输出中提取路径
- 若 Designer 用 `write_file` 保存了 PNG，输出中应包含路径，可被正确提取
- 若 Designer 未写文件或路径格式不符合正则，coder 无法获得设计图路径

### 4.4 完成性结论

| 场景 | 完成概率 | 说明 |
|------|----------|------|
| **有 Designer Duck 且能写文件** | 中高 | 用 HTML+CSS 或 Python 脚本生成 PNG 并保存，续步后 coder 做 HTML |
| **Designer 只描述不执行** | 低 | 被判计划而非结果，重试后仍失败，主 Agent 接管 |
| **无 Designer/Image Duck** | 中 | 可能委派给 general Duck，或主 Agent 直接处理 |
| **主 Agent 接管后** | 高 | 续步钩子会明确要求用 write_file/terminal 完成，主 Agent 有完整工具 |

**综合预测**：任务**有可能完成**，但存在以下风险：
1. PNG 设计图可能退化为「HTML 原型」或「Python 脚本生成的简单图」，而非精细设计稿
2. 若 Designer Duck 多次失败，主 Agent 会接管，需用户或主 Agent 明确「先做设计图再做 HTML」的步骤
3. 建议：若需高质量设计图，可考虑接入 image_gen 类工具（如 DALL·E、Stable Diffusion API）或明确要求「用 HTML+CSS 画出布局并截图导出 PNG」

---

## 五、逻辑正确性检查小结

| 检查项 | 状态 | 说明 |
|--------|------|------|
| Chat → delegate_duck 入口 | ✅ | tools.md 规定设计/网页类任务优先委派 |
| 调度器分配逻辑 | ✅ | list_available 正确排除 BUSY |
| 本地/远程 Duck 分发 | ✅ | is_local 区分，分别走队列/WebSocket |
| 串行续步 | ✅ | 续步提示明确要求引用完整路径 |
| 失败重试 | ✅ | 调度器 2 次重试 + Local Duck 1 次计划检测重试 |
| 失败后主 Agent 接管 | ✅ | 续步钩子会触发主 Agent 用工具完成 |
| PENDING 重分配 | ✅ | 新 Duck 注册时 reschedule_pending |
| 超时与卡死检测 | ✅ | 调度器 timeout+120s，Local Duck 90s 无进展 |

**发现的潜在改进点**：
1. Designer/Image Duck 的 `required_tools` 与实际可用工具不一致，可能导致用户期望与能力不符
2. 无 `image_gen` 时，设计图类任务应优先引导为「HTML 原型 + 截图」或「Python 绘图脚本」，而非纯文生图
