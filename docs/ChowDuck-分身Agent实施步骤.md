# Chow Duck 分身 Agent 系统 — 实施步骤

> 基于 `chow_duck_agent_design.docx` 的设计文档，按 **可交付阶段** 拆分为 6 个阶段。每个阶段完成后可独立测试与验收。

---

## 阶段 1：基础通信协议与 Duck Registry（后端） ✅ 已完成

**目标**：建立主 Agent 与 Duck Agent 之间的通信基础设施。

### 1.1 定义 Duck 通信消息协议 ✅
- 文件：`backend/services/duck_protocol.py`
- 消息类型枚举 `DuckMessageType`：REGISTER / HEARTBEAT / RESULT / STATUS_REPORT / TASK / CANCEL_TASK / PING / CHAT / ACK
- Duck 类型枚举 `DuckType`：CRAWLER / CODER / IMAGE / VIDEO / TESTER / DESIGNER / GENERAL
- Duck 状态枚举 `DuckStatus`：ONLINE / BUSY / OFFLINE
- 任务状态枚举 `TaskStatus`：PENDING / ASSIGNED / RUNNING / COMPLETED / FAILED / CANCELLED
- Pydantic 模型：DuckMessage / DuckRegisterPayload / DuckTaskPayload / DuckResultPayload / DuckInfo / DuckTask

### 1.2 实现 Duck Registry ✅
- 文件：`backend/services/duck_registry.py`
- 单例模式 `DuckRegistry.get_instance()`
- CRUD：register / unregister / get / list_all / list_online / list_available
- 心跳：heartbeat / check_heartbeats（60s 超时）
- 状态管理：set_status / set_current_task / increment_completed / increment_failed
- 持久化：`backend/data/duck_registry.json`（自动创建）

### 1.3 建立 Duck WebSocket 端点 ✅
- 文件：`backend/routes/duck_ws.py`
- 路由：`/duck/ws?token=<token>&duck_id=<duck_id>`
- 认证：`verify_token()` 校验
- 消息处理：REGISTER / HEARTBEAT / RESULT / STATUS_REPORT / CHAT
- 心跳：30s 间隔发送 PING
- 断线清理：自动标记 OFFLINE
- Egg 连接识别：REGISTER 时检查 token 并标记 Egg 状态
- Duck 上线触发：reschedule_pending() 重新分配等待任务

### 1.4 Duck REST API ✅
- 文件：`backend/routes/duck_api.py`
- `GET /duck/list` — 列出所有已注册 Duck（支持按 type/status 过滤）
- `GET /duck/info/{duck_id}` — 查询单个 Duck 详细信息
- `DELETE /duck/remove/{duck_id}` — 删除 Duck
- `GET /duck/available` — 列出可用 Duck（可按类型过滤）
- `GET /duck/stats` — Duck 汇总统计
- `POST /duck/heartbeat-check` — 手动触发心跳巡检

### 1.5 路由注册 ✅
- `backend/routes/__init__.py` 中注册 `duck_api_router` + `duck_ws_router`

### 交付物
- [x] Duck 通信协议模型（10+ Pydantic 模型）
- [x] Duck Registry 服务（单例、持久化、心跳超时）
- [x] Duck WebSocket 端点（/duck/ws）
- [x] Duck REST API（6 个端点）
- [ ] 单元测试

---

## 阶段 2：任务调度引擎（后端） ✅ 已完成

**目标**：主 Agent 能拆解任务并分配给 Duck Agent。

### 2.1 任务模型定义 ✅
- 文件：`backend/services/duck_task_scheduler.py`
- DuckTask 模型：task_id / description / task_type / params / status / priority / timeout / assigned_duck_id / parent_task_id / output / error / 时间戳
- 调度策略 ScheduleStrategy：DIRECT / SINGLE / MULTI

### 2.2 任务调度器 ✅
- 三种调度策略：
  - **DIRECT**：指定 duck_id 直接分配
  - **SINGLE**：从可用池中选完成任务最少的 Duck（负载均衡）
  - **MULTI**：Fan-out 到所有可用 Duck，聚合结果
- 支持任务优先级（0=normal / 1=high / 2=urgent）
- 支持任务取消（通知 Duck + 清理状态）
- 自动识别本地/远程 Duck，内存队列 vs WebSocket 发送
- 超时 watcher（asyncio.Task 自动监控）
- PENDING 任务重新调度 `reschedule_pending()`

### 2.3 任务结果汇总 ✅
- 子任务完成后检查父任务 `_check_parent_completion()`
- 聚合成功/失败结果
- 支持部分完成（有成功子任务则父任务标记为 COMPLETED）
- 回调机制：ResultCallback 异步回调

### 2.4 集成到主 Agent ✅
- 文件：`backend/agent/autonomous_agent.py` → `_handle_delegate_duck()` 方法
- 参数：description / duck_type / duck_id / strategy / timeout / task_type / params / priority
- 调用 scheduler.submit() 提交任务
- 使用 asyncio.Future 等待结果

### 2.5 任务持久化 ✅
- 目录：`backend/data/duck_tasks/`（每个任务一个 JSON 文件）
- 启动时加载未完成任务

### 交付物
- [x] DuckTask 模型 + ScheduleStrategy
- [x] 任务调度器（三种策略 + 负载均衡）
- [x] 任务结果汇总（子任务聚合 + 回调）
- [x] 与 autonomous_agent 集成
- [x] 任务持久化（JSON 文件）
- [ ] 端到端测试

---

## 阶段 3：本地 Duck 模式（后端） ✅ 已完成

**目标**：在同一电脑上创建多个 Agent 会话作为本地 Duck。

### 3.1 Local Duck Worker ✅
- 文件：`backend/services/local_duck_worker.py`
- `LocalDuckWorker` 类：基于 asyncio 协程的子 Agent 执行上下文
- 每个 Local Duck 有独立的任务队列（`asyncio.Queue`）
- 通过内存队列与调度器通信（无需 WebSocket）
- 5s 间隔维护心跳
- 内置 LLM 调用能力（`_do_work()` → `llm_client.chat_completion()`）
- 可子类化以自定义特定 Duck 行为

### 3.2 Local Duck 管理 ✅
- `LocalDuckManager` 单例类
- 创建本地 Duck：生成 `local_xxx` ID，启动 worker，注册到 Registry（is_local=True）
- 销毁本地 Duck：停止 worker，从 Registry 注销
- 批量销毁 `destroy_all()`

### 3.3 调度器统一集成 ✅
- `_assign_to_duck()` 方法重构：自动检测 `duck_info.is_local`
  - 本地 Duck → `_send_to_local_duck()` 内存队列投递
  - 远程 Duck → `_send_to_remote_duck()` WebSocket 发送
- 对调度策略完全透明，本地/远程 Duck 统一调度

### 3.4 API 扩展 ✅
- `POST /duck/create-local` — 创建本地 Duck（指定 name / duck_type / skills）
- `DELETE /duck/local/{duck_id}` — 停止并删除本地 Duck
- `GET /duck/local/list` — 列出所有本地 Duck

### 交付物
- [x] Local Duck Worker（asyncio 协程、内存队列、LLM 调用）
- [x] Local Duck Manager（创建、销毁、批量销毁）
- [x] 与调度器统一集成（自动识别本地/远程）
- [x] API 扩展（3 个端点）
- [ ] 本地并行执行测试

---

## 阶段 4：Egg 生成系统（后端 + CLI） ✅ 已完成

**目标**：生成可部署的 Egg 包，复制到其他电脑即可启动 Duck Agent。

### 4.1 Duck 模板系统 ✅
- 文件：`backend/services/duck_template.py`
- 7 种内置模板（DuckTemplate dataclass）：
  - 🕷️ Crawler Duck — 爬虫鸭（web_crawl / data_extract / html_parse / api_fetch）
  - 💻 Coder Duck — 编程鸭（code_write / code_review / debug / refactor / test_write）
  - 🎨 Image Duck — 文生图鸭（image_generate / image_edit / image_analyze / ocr）
  - 🎬 Video Duck — 视频处理鸭（video_edit / video_transcode / video_analyze / subtitle）
  - 🧪 Tester Duck — 测试鸭（test_write / test_run / bug_report / performance_test）
  - 🎯 Designer Duck — 设计鸭（ui_design / ux_review / prototype / style_guide）
  - 🦆 General Duck — 通用鸭
- 每个模板定义：name / description / skills / system_prompt / required_tools / icon
- API：`get_template()` / `list_templates()` / `get_template_summary()`

### 4.2 Egg 打包器 ✅
- 文件：`backend/services/egg_builder.py`
- `EggBuilder` 单例类
- Egg 内容（ZIP 压缩）：
  - `duck_client.py` — 精简客户端（WebSocket 连接 + 自动注册 + 任务执行 + 自动重连）
  - `config.json` — 连接配置（egg_id / token / main_agent_url / 模板信息）
  - `start_duck.sh` — macOS/Linux 启动脚本（自动创建 venv + 安装依赖）
  - `start_duck.bat` — Windows 启动脚本
  - `requirements.txt` — Python 依赖（websockets / pydantic）
  - `README.md` — 部署说明
- 自动生成：唯一 egg_id + `secrets.token_urlsafe(32)` 认证 token
- Egg 记录持久化：`backend/data/duck_eggs.json`
- ZIP 存储：`backend/data/duck_eggs/`

### 4.3 Egg 部署引导 ✅
- `start_duck.sh`：
  - 检查 python3 → 创建 venv → 安装依赖 → 启动 duck_client.py
- `duck_client.py`：
  - 加载 config.json → WebSocket 连接 → 发送 REGISTER → 接收 TASK → 执行 → 返回 RESULT
  - 断线自动重连（指数退避，最大 60s）
  - 定期心跳响应 PING

### 4.4 API ✅
- `POST /duck/create-egg` — 创建新 Egg（指定 duck_type / name / main_agent_url）
- `GET /duck/egg/{egg_id}/download` — 下载 Egg ZIP（FileResponse）
- `GET /duck/eggs` — 列出所有已生成的 Egg
- `DELETE /duck/egg/{egg_id}` — 删除 Egg
- `GET /duck/templates` — 查看所有 Duck 模板

### 4.5 WebSocket 集成 ✅
- `duck_ws.py` REGISTER 处理：检测 Egg token → `egg_builder.mark_connected()`

### 交付物
- [x] Duck 模板系统（7 种模板，含 system_prompt + skills + icon）
- [x] Egg 打包器（ZIP 输出，含 6 个文件）
- [x] Egg 启动脚本（macOS + Windows，venv + 自动安装）
- [x] Egg 客户端（自动重连、心跳、任务执行）
- [x] Egg API（5 个端点）
- [x] Egg 连接追踪（mark_connected）
- [ ] 端到端测试：生成 Egg → 部署 → 连接主 Agent

---

## 阶段 5：Web/Mac 前端交互（前端） ✅ 已完成

**目标**：用户可通过 Web 和 Mac App 端使用 Chow Duck 功能。

### 5.1 Web 端 Duck 管理面板 ✅
- `web/src/services/api.ts` — 添加 11 个 Duck/Egg API 函数
- `web/src/stores/duckStore.ts` — Zustand 状态管理（Duck/Template/Egg/Stats）
- `web/src/components/DuckManagement.tsx` — 主管理弹窗（3 个 Tab）
  - Duck 列表 Tab：状态/类型/本地标识/任务统计/删除
  - Chow Duck Tab：选择模板 → 动画 → 生成 Egg / 创建本地 Duck
  - Eggs Tab：列表/下载/删除/连接状态显示
- `web/src/components/Toolbar.tsx` — 添加 🐦 Bird 图标按钮
- `web/src/components/Layout.tsx` — 懒加载 DuckManagement 弹窗

### 5.2 Chow Duck 动画 ✅
- `web/src/components/ChowDuckAnimation.tsx` — Framer Motion 4 阶段动画
  - eating → digesting → egg → done
  - 进度条 + 鸭子移动 → 嘴巴吃掉 → 齿轮消化 → 下蛋弹出
  - 每种鸭子类型不同 emoji 图标

### 5.3 Mac App Chow Duck 功能 ✅
- `MacAgentApp/MacAgentApp/Services/BackendService.swift` — 添加 10 个 Duck REST API 方法
- `MacAgentApp/MacAgentApp/ViewModels/AgentViewModel.swift` — Duck 状态属性 + 操作方法
  - `@AppStorage("chowDuckEnabled")` — 持久化开关
  - loadDuckData / createLocalDuck / destroyLocalDuck / removeDuck / createEgg / deleteEgg
- `MacAgentApp/MacAgentApp/Views/DuckSettingsView.swift` — Duck 设置页（新增）
  - Chow Duck 模式总开关
  - Stats 概览（在线/忙碌/总计）
  - 模板网格选择 + Chow 动画 + Egg 生成
  - 本地 Duck 创建按钮
  - Duck 列表（状态指示灯/类型标签/本地标识/删除）
  - Egg 列表（下载/删除/连接状态）
- `MacAgentApp/MacAgentApp/Views/SettingsView.swift` — 添加 "Chow Duck" 导航条目 (index 12, icon: bird)

### 交付物
- [x] Web Duck 管理面板（3 Tab 弹窗 + Toolbar 入口）
- [x] Chow Duck 动画效果（eating/digesting/egg/done 4 阶段）
- [x] Mac App Duck 设置页（开关 + 模板 + 列表 + Egg 管理）
- [x] iOS Duck 功能入口（暂未实现，低优先级）

---

## 阶段 6：协作与高级特性 ✅ 已完成

**目标**：多 Duck 协作执行复杂任务。

### 6.1 多 Duck 协作流 ✅
- `backend/services/duck_task_dag.py` — DAG 任务编排器
  - DAGNode 模型：node_id / description / depends_on / input_mapping
  - DAGExecution：dag_id / nodes / status / 节点执行状态
  - 拓扑排序 + 环检测
  - 依赖驱动调度：前置节点完成后自动触发下游
  - 失败传播：上游失败标记下游为 SKIPPED
  - 终端节点识别：自动汇总最终结果
- REST API：
  - `POST /duck/dag/create` — 创建 DAG
  - `POST /duck/dag/{id}/execute` — 执行 DAG
  - `POST /duck/dag/{id}/cancel` — 取消 DAG
  - `GET /duck/dag/{id}` — 查询 DAG 状态
  - `GET /duck/dag/list` — 列出所有 DAG

### 6.2 Duck 间通信 ✅
- `backend/services/duck_message_relay.py` — 消息中转服务
  - relay_message：自动检测本地/远程 Duck 并发送
  - broadcast_to_ducks：广播到所有在线 Duck
  - 消息日志（最大 1000 条）
- REST API：
  - `POST /duck/relay` — 发送中转消息
  - `GET /duck/relay/log` — 查询消息日志

### 6.3 数据持久化与恢复 ✅
- `duck_task_scheduler.py` 增强 `_load_from_disk()`:
  - 重启后 ASSIGNED/RUNNING 任务自动重置为 PENDING
  - 等待 Duck 重连后通过 reschedule_pending() 重新分配
- Duck Registry 已有 JSON 持久化（阶段 1）
- Egg Records 已有 JSON 持久化（阶段 4）

### 交付物
- [x] 多 Duck 协作任务流（DAG 编排 + 依赖调度）
- [x] Duck 间消息中转
- [x] 持久化与恢复（任务状态重置 + 重连调度）

---

## 实施优先级与当前进度

| 优先级 | 阶段 | 预估复杂度 | 依赖 | 状态 |
|--------|------|-----------|------|------|
| P0 | 阶段 1：通信协议与 Registry | 中 | 无 | ✅ 已完成 |
| P0 | 阶段 2：任务调度引擎 | 高 | 阶段 1 | ✅ 已完成 |
| P1 | 阶段 3：本地 Duck 模式 | 中 | 阶段 1+2 | ✅ 已完成 |
| P1 | 阶段 4：Egg 生成系统 | 高 | 阶段 1 | ✅ 已完成 |
| P2 | 阶段 5：前端交互 | 中 | 阶段 1+2+4 | ✅ 已完成 |
| P2 | 阶段 6：协作与高级特性 | 高 | 阶段 1+2+3 | ✅ 已完成 |

---

## 文件清单

### 新建文件
| 文件 | 阶段 | 说明 |
|------|------|------|
| `backend/services/duck_protocol.py` | 1 | 通信协议、消息模型 |
| `backend/services/duck_registry.py` | 1 | Duck 注册中心 |
| `backend/routes/duck_ws.py` | 1 | WebSocket 端点 |
| `backend/routes/duck_api.py` | 1+3+4+6 | REST API（22 个端点） |
| `backend/services/duck_task_scheduler.py` | 2 | 任务调度引擎 |
| `backend/services/local_duck_worker.py` | 3 | 本地 Duck Worker + Manager |
| `backend/services/duck_template.py` | 4 | Duck 模板系统（7 种） |
| `backend/services/egg_builder.py` | 4 | Egg 打包器 |
| `backend/services/duck_task_dag.py` | 6 | DAG 任务编排器 |
| `backend/services/duck_message_relay.py` | 6 | Duck 间消息中转 |
| `web/src/stores/duckStore.ts` | 5 | Zustand Duck 状态管理 |
| `web/src/components/DuckManagement.tsx` | 5 | Web Duck 管理弹窗 |
| `web/src/components/ChowDuckAnimation.tsx` | 5 | Chow Duck 吃鸭子动画 |
| `MacAgentApp/.../Views/DuckSettingsView.swift` | 5 | Mac App Duck 设置页 |

### 修改文件
| 文件 | 说明 |
|------|------|
| `backend/routes/__init__.py` | 注册 duck_api_router + duck_ws_router |
| `backend/agent/autonomous_agent.py` | `_handle_delegate_duck()` 委派方法 |
| `backend/services/duck_task_scheduler.py` | 本地/远程 Duck 统一调度 + 重启恢复 |
| `backend/routes/duck_ws.py` | Egg token 识别 + reschedule_pending |
| `web/src/services/api.ts` | 添加 11 个 Duck/Egg API 函数 |
| `web/src/components/Toolbar.tsx` | 添加 Bird 图标按钮 |
| `web/src/components/Layout.tsx` | 懒加载 DuckManagement 弹窗 |
| `MacAgentApp/.../Services/BackendService.swift` | 添加 10 个 Duck REST API 方法 |
| `MacAgentApp/.../ViewModels/AgentViewModel.swift` | Duck 状态属性 + 操作方法 |
| `MacAgentApp/.../Views/SettingsView.swift` | 添加 Chow Duck 导航条目 |

### API 端点汇总
| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/duck/list` | 列出所有 Duck |
| GET | `/duck/info/{duck_id}` | Duck 详情 |
| DELETE | `/duck/remove/{duck_id}` | 删除 Duck |
| GET | `/duck/available` | 可用 Duck |
| GET | `/duck/stats` | 统计信息 |
| POST | `/duck/heartbeat-check` | 心跳巡检 |
| POST | `/duck/create-local` | 创建本地 Duck |
| DELETE | `/duck/local/{duck_id}` | 销毁本地 Duck |
| GET | `/duck/local/list` | 本地 Duck 列表 |
| POST | `/duck/create-egg` | 创建 Egg |
| GET | `/duck/egg/{egg_id}/download` | 下载 Egg ZIP |
| GET | `/duck/eggs` | Egg 列表 |
| DELETE | `/duck/egg/{egg_id}` | 删除 Egg |
| GET | `/duck/templates` | Duck 模板列表 |
| POST | `/duck/relay` | Duck 间消息中转 |
| GET | `/duck/relay/log` | 消息中转日志 |
| POST | `/duck/dag/create` | 创建 DAG |
| POST | `/duck/dag/{id}/execute` | 执行 DAG |
| POST | `/duck/dag/{id}/cancel` | 取消 DAG |
| GET | `/duck/dag/{id}` | 查询 DAG 状态 |
| GET | `/duck/dag/list` | 列出所有 DAG |
| WS | `/duck/ws` | Duck WebSocket 连接 |
