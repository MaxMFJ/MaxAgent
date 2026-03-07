# Chow Duck 子 Agent 架构与实施方案

> 基于 Egg 系统，升级为「子 Duck = Mac App + 独立 Backend」架构，支持任务板编排、用户直聊子 Duck、跨机协作。

---

## 一、架构概览

### 1.1 目标与原则

| 项目 | 说明 |
|------|------|
| **平台** | 当前仅考虑 macOS；Windows / Linux 后续通过 Web 端扩展 |
| **统一 App** | 主 Agent 与子 Duck 均使用 **Chow Duck Mac App**（同一二进制） |
| **独立 Backend** | 子 Duck **不连接**主 Agent 的 backend，运行**自己的 backend** |
| **配置作用** | 配置文件建立通讯，使主工作流知道另一台 PC 已接入、可分配任务 |
| **权限划分** | 子 Duck 按 `permissions` 白名单过滤工具，部分功能不可用 |

### 1.2 架构示意

```
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│  主 Mac (PC A)                       │     │  子 Duck Mac (PC B)                  │
│  ┌─────────────┐  ┌───────────────┐ │     │  ┌─────────────┐  ┌───────────────┐ │
│  │ Chow Duck   │  │ Main Backend  │ │     │  │ Chow Duck   │  │ Duck Backend  │ │
│  │ App (主)    │──│ (主 Agent)    │ │     │  │ App (Duck)  │──│ (独立端口)     │ │
│  └─────────────┘  └───────┬───────┘ │     │  └─────────────┘  └───────┬───────┘ │
│                            │         │     │                            │         │
│                    分配任务 │  WebSocket   │                    执行任务 │         │
│                            └────────────────┼────────────────────────────┘         │
└─────────────────────────────────────┘     └─────────────────────────────────────┘
```

### 1.3 子 Duck 类型区分（设计决策）

| 类型 | 说明 | 创建入口 | 通信方式 |
|------|------|----------|----------|
| **本机子 Duck** | 与主 Backend 同进程，无 UI 能力，仅 LLM 补全 | Mac App 设置 / Web 面板 → 创建本地 Duck | 内存队列，无需 WebSocket |
| **其他 PC 子 Duck** | 另一台 Mac 的 Chow Duck App + Duck Backend，有 UI 能力 | Egg 导入 / duck_client.py 部署 | WebSocket 连接主 Backend |

- **本机子 Duck**：`POST /duck/create-local` 创建，`is_local=true`，由 `LocalDuckWorker` 执行，适合纯 LLM 任务（代码、文案等）。
- **其他 PC 子 Duck**：通过 Egg 或 Mac App 导入配置，`is_local=false`，有 screenshot、input_control 等 UI 工具，适合需要操作本机界面的任务。

iOS / Web 的 Duck 列表统一展示两类，通过 `is_local` 区分显示「本地」标签；`chat_to_duck` 对两类均支持。

### 1.4 Egg 形态（设计决策）

| 形态 | 说明 | 适用 |
|------|------|------|
| **新架构 Egg** | 生成 `duck_config.json` 配置包（可含 ZIP），供 Mac App 导入 | macOS 子 Duck（其他 PC） |
| **轻量 Egg** | 保留 `duck_client.py` 的 zip，供非 Mac 或快速部署 | 可选，非主路径 |

主路径：主 Agent 创建 Egg → 生成 `duck_config.json`（或含 config 的 zip）→ 用户导入到**另一台 Mac** 的 Chow Duck App → 以 Duck 模式启动。

---

## 二、任务流程与任务板

### 2.1 完整工作流

```
1. 任务下发 → 2. 主 Agent 拆解 → 3. 分配 + 建任务板 → 4. 子 Agent 领取执行返回
→ 5. 更新任务板 → 6. 主 Agent 汇总 → 7. 任务板全部完成 → 8. 主 Agent 主动在对应 Chat 返回
→ 9. 关联所有结果文件
```

### 2.2 任务板与调度器关系（设计决策）

- **任务板** = `duck_task_scheduler` 的持久化 + 可视化视图
- 主 Agent 拆解时通过 `delegate_duck` 或 DAG 提交到 scheduler
- 任务板监听 scheduler 状态，供主 Agent 轮询/订阅
- 现有 `duck_task_scheduler` 扩展：增加任务板 API（列表、状态、产出文件）

### 2.3 关键设计点

| 设计点 | 说明 |
|--------|------|
| **任务板** | 中心化看板，跟踪子任务状态（待领取/执行中/完成/失败） |
| **Chat 关联** | 顶层任务 ↔ Chat session 映射，完成时主 Agent 在该 Chat 主动返回 |
| **结果文件** | 子 Duck 上传到主 Backend，返回时附带链接/引用 |

### 2.4 错误与兜底

| 场景 | 应对 |
|------|------|
| 子任务失败/超时 | 主 Agent 可兜底的自己执行；不可兜底的标记失败并报告 |
| 超时检测 | 任务板对「执行中」设超时，超时后自动失败，触发兜底或重试 |
| 依赖环 | 拆解时做依赖环检测 |
| 子 Agent 重复领取 | 任务板加领取锁，先到先得 |
| 结果文件跨机 | 子 Duck 通过 `POST /duck/upload-result` 上传到主 Backend，主 Backend 返回 URL 给用户 |
| Chat 会话丢失 | 推送失败时落库/通知，用户重开可看到 |
| 主 Agent 崩溃 | 任务板持久化，重启后恢复编排状态 |

---

## 三、配置与接入

### 3.1 duck_config.json

```json
{
  "mode": "duck",
  "main_agent_url": "ws://192.168.1.100:8765/duck/ws",
  "token": "xxx",
  "duck_id": "duck_coder_001",
  "duck_type": "coder",
  "permissions": ["screenshot", "input_control", "app_control", "file_operations", "terminal", "web_search"],
  "llm_config": {}
}
```

- `main_agent_url`：主 Backend 的 Duck WebSocket。同机用 `ws://127.0.0.1:8765/duck/ws`，跨机用主 Backend 的局域网 IP 或隧道 URL
- `llm_config`：可选，子 Duck 独立调用 LLM 时的配置；不填则从主 Backend `GET /config` 拉取或使用默认

### 3.2 本机子 Duck：创建与管理

| 入口 | 说明 |
|------|------|
| **Mac App** | 设置 → Chow Duck → 选择模板 →「创建本地 Duck」 |
| **Web 面板** | Toolbar 鸟图标 → Chow Duck Tab → 选择模板 →「创建本地 Duck」 |
| **API** | `POST /duck/create-local`（name / duck_type / skills） |
| **删除** | `DELETE /duck/local/{duck_id}`，或 Web/Mac 列表中的删除按钮 |
| **启动** | `POST /duck/local/{duck_id}/start` — 后端重启后本地 Duck 会离线，用户需在列表中点击「启动」恢复 |

本机子 Duck 无需 Egg、无需导入，创建后立即注册到 Registry，可被主 Agent 委派或用户直聊。**后端重启后**本地 Duck 会离线（Worker 进程丢失），需用户在分身列表中点击「启动」按钮重新启动。

### 3.3 Mac 端：导入 Egg 启动其他 PC 子 Duck

| 步骤 | 说明 |
|------|------|
| 1. 设置 → Chow Duck → 导入 Egg | 选择 Egg ZIP 或 `duck_config.json` |
| 2. 解析并写入 | 保存到 `~/Library/Application Support/ChowDuck/duck_config.json` |
| 3. 重启生效 | 下次启动以 Duck 模式运行 |
| 4. 退出 Duck 模式 | 设置中「退出 Duck 模式」删除/重命名 config，或 `mode: "main"`，重启 |

> 注：导入 Egg 用于**另一台 Mac**；本机若需子 Duck，用「创建本地 Duck」即可。

### 3.4 其他 PC 子 Duck：启动与端口

| 步骤 | 说明 |
|------|------|
| 检测 Duck 模式 | 存在 `duck_config.json` 且 `mode: "duck"` |
| 寻找可用端口 | 从 8766 起探测，同机多 Duck 各占一端口（8766、8767…） |
| 启动 Duck Backend | Mac App 以子进程启动 `python backend/main.py --duck-mode --port <port>` |
| 连接主工作流 | Duck Backend 连接 `main_agent_url` 注册 |

本机子 Duck 无需端口，由主 Backend 的 `LocalDuckWorker` 在进程内直接执行。

---

## 四、权限与禁用

### 4.1 子 Duck 需禁用的功能

| 功能 | 禁用原因 |
|------|----------|
| `delegate_duck` / Chow Duck | 防无限递归 |
| 创建 Egg、创建本地 Duck、导入 Egg | 子 Duck 不再衍生 Duck |
| `duck/dag` 委派、`duck/relay` 主动发起 | 防间接递归，由主 Agent 协调 |
| `request_tool_upgrade` | 保持权限边界 |
| Tunnel、模型/全局配置 | 主 Agent 管理 |
| HITL | 委派即授权，可禁用或改为向主 Agent 请求 |

### 4.2 实现方式

- Backend：执行前检查 `is_duck_mode`，Duck 则拒绝上述能力
- Mac App：Duck 模式下隐藏 Chow Duck 设置、导入 Egg、隧道、模型配置等入口

---

## 五、iOS / Web 端：用户直聊子 Duck

### 5.1 方案 A：主 Backend 转发（采用）

- iOS/Web 仍连主 Backend，新增 `chat_to_duck` 消息类型
- 主 Backend 转发给对应 Duck，Duck 可远程

### 5.2 流程

1. **iOS**：用户选择 Duck → 发送 `chat_to_duck`（`duck_id`、`content`、`session_id`）
2. **主 Backend**：生成 `task_id`，记录 `session_id + duck_id + task_id` 映射，转发给 Duck，标记 Duck 忙碌
3. **子 Duck**：执行，流式/最终返回带 `task_id`、`duck_id`、`is_direct_chat: true`
4. **主 Backend**：根据映射找到用户 WebSocket，流式转发结果
5. **恢复**：完成后释放 Duck 忙碌状态

### 5.3 设计决策汇总

| 问题 | 决策 |
|------|------|
| **session 映射** | connection_manager 已维护 session_id↔WebSocket；chat_to_duck 额外记录 `(session_id, duck_id, task_id)` 三元组 |
| **task_id 生成** | 主 Backend 在转发时生成，随请求发给 Duck |
| **流式返回** | Duck agent 每轮输出经主 Backend 实时转发，复用现有 stream 消息格式 |
| **会话模型** | 用户选 Duck 时新建「Duck 专属会话」，conversation 增加 `target_type: "main"|"duck"`、`target_duck_id?` |
| **Duck 列表** | iOS 通过 `GET /duck/list` 或 connected 消息中的 `duck_list` 获取；含本机子 Duck（`is_local: true`）与其他 PC 子 Duck（`is_local: false`），UI 用「本地」标签区分 |
| **Duck 离线** | 主 Backend 检查在线状态，离线则返回 `chat_to_duck_error`，iOS 提示「该 Duck 已离线」 |
| **直聊超时** | 默认 600s，超时后释放 busy，向用户推送超时提示 |

### 5.4 Duck 忙碌与调度

| 规则 | 说明 |
|------|------|
| **busy_reason** | `direct_chat`（用户直聊）、`assigned_task`（主 Agent 委派）、空=可用 |
| **调度排除** | 分配任务时排除**所有** busy 的 Duck（无论 direct_chat 还是 assigned_task） |
| **双重忙碌** | Duck 已 assigned_task 时，用户发 chat_to_duck 应拒绝：「该 Duck 正在执行任务，请稍后或选择其他 Duck」 |
| **单任务** | Duck 同一时刻只处理一个任务 |

### 5.5 结果文件

- 子 Duck 产出文件通过 `POST /duck/upload-result` 上传主 Backend
- 主 Backend 返回 URL 或 base64，随结果转发给用户

### 5.6 Web 端

- 与 iOS 相同：连主 Backend，`chat_to_duck` 逻辑一致

---

## 六、实现要点速查

| 层级 | 改动 |
|------|------|
| **主 Backend** | `chat_to_duck` 消息；session+duck+task 映射；流式转发；Duck 离线/忙碌检查；`POST /duck/upload-result`；`POST /duck/create-local` 创建本机 Duck |
| **Duck Registry** | `busy_reason` 扩展；`is_local` 区分本机/远程 |
| **任务调度器** | 排除所有 busy 的 Duck；本地 Duck 走内存队列，远程 Duck 走 WebSocket |
| **子 Duck** | 直聊任务返回带 `task_id`、`duck_id`、`is_direct_chat`；结果文件上传 |
| **Mac App** | 导入 Egg（其他 PC）；创建本地 Duck；Duck 模式启动 Python 子进程；端口探测；Tab 布局（分身/Chow/Egg）；生成 Egg 与创建本地 Duck 均强制至少 3s 吃鸭子动画 |
| **iOS** | 选择对话对象 UI；`chat_to_duck`；Duck 列表（含本机/远程，`is_local` 标签）；解析返回 |

---

## 附录：子 Duck 类型与能力对比

### 本机子 Duck vs 其他 PC 子 Duck

| 维度 | 本机子 Duck | 其他 PC 子 Duck |
|------|-------------|-----------------|
| **创建方式** | Mac/Web 面板「创建本地 Duck」 | Egg 导入 / duck_client 部署 |
| **运行位置** | 主 Backend 进程内 | 另一台 Mac 的独立进程 |
| **通信** | 内存队列 | WebSocket |
| **UI 工具** | 无（screenshot、input_control 等不可用） | 有（在目标 Mac 上执行） |
| **适用场景** | 纯 LLM 任务（代码、文案、分析） | 需操作目标机界面的任务 |
| **chat_to_duck** | 支持 | 支持 |

### 问题本质

- 需要**操作本机界面**的子任务，必须由**其他 PC 子 Duck**（Mac App + Duck Backend）在目标机上执行
- 本机子 Duck 适合无 UI 依赖的并行 LLM 任务
- 结果文件跨机需通过 `POST /duck/upload-result` 上传主 Backend 中转

---

## 七、实现完成情况与闭环分析（2025-07 更新）

> 三端（Mac App / iOS App / 主 Backend）功能覆盖评估

---

### 7.1 主 Backend ✅ 全部完成

| 功能点 | 文件 | 状态 |
|--------|------|------|
| Duck 模式全局开关与端口支持 | `app_state.py`、`start.sh` | ✅ 完成 |
| Duck 模式 WS 客户端（远程 Duck ↔ 主 Backend） | `services/duck_client_ws.py` | ✅ 完成 |
| 本地 Duck 工作器（进程内 AutonomousAgent） | `services/local_duck_worker.py` | ✅ 完成 |
| Duck 注册表（CRUD、心跳、busy_reason） | `services/duck_registry.py` | ✅ 完成 |
| Duck 任务调度器（本地/远程分发、超时） | `services/duck_task_scheduler.py` | ✅ 完成 |
| `chat_to_duck` WS 消息处理（离线/忙碌检查、回调映射） | `ws_handler.py` | ✅ 完成 |
| `chat_to_duck_accepted` 回包 | `ws_handler.py` | ✅ 完成 |
| `chat_to_duck_result` 路由回用户 WS | `ws_handler.py`、`routes/duck_ws.py` | ✅ 完成 |
| Duck WS 端点（注册/心跳/状态上报/结果上报） | `routes/duck_ws.py` | ✅ 完成 |
| 结果文件上传 `POST /duck/upload-result` | `routes/duck_api.py` | ✅ 完成 |
| 结果文件下载 `GET /duck/result-file/{duck_id}/{task_id}` | `routes/duck_api.py` | ✅ 完成 |
| Duck 模式禁用（create-egg、tunnel、delegate_duck 嵌套） | 多处 | ✅ 完成 |
| `GET /duck/list`、`POST /duck/create-local`、`DELETE /duck/local/{id}` | `routes/duck_api.py` | ✅ 完成 |

---

### 7.2 Mac App ✅ 全部完成

| 功能点 | 文件 | 状态 |
|--------|------|------|
| EggModeManager（读写 duck_config.json/ZIP） | `Services/EggModeManager.swift` | ✅ 完成 |
| 导入 Egg UI（fileImporter、退出 Duck 模式） | `Views/DuckSettingsView.swift` | ✅ 完成 |
| Duck Backend 子进程启动（环境变量注入、端口探测） | `Services/ProcessManager.swift` | ✅ 完成 |
| BackendService 动态端口切换 | `Services/BackendService.swift` | ✅ 完成 |
| 启动时自动应用 Duck 模式 | `ViewModels/AgentViewModel.swift` | ✅ 完成 |
| BUILD SUCCEEDED（xcodebuild 验证） | — | ✅ 已验证 |

> **闭环链路（Mac App）**：  
> 导入 Egg → 保存 config → App 启动 → `applyDuckModeIfNeeded()` → 端口探测 → `startDuckBackend()` → 进程启动 → `duck_client_ws.py` 连接主 Backend → 注册成功 → 主 Backend 可分配任务。具体为完整闭环 ✅

---

### 7.3 iOS App ✅ 全部完成（本次修复后）

| 功能点 | 文件 | 状态 |
|--------|------|------|
| Duck 模型（duckId/name/status/isLocal） | `Models/Duck.h/m` | ✅ 完成 |
| Duck 列表 API（GET /duck/list） | `Services/DuckApiService.h/m` | ✅ 完成 |
| 选择对话对象 UI（主 Agent / Duck 列表，isLocal 标签，离线禁选） | `ViewControllers/DuckTargetSelectorViewController.m` | ✅ 完成 |
| 导航栏鸟图标入口（showDuckTargetSelector） | `ViewControllers/ChatViewController.m` | ✅ 完成 |
| Duck 专属会话（createNewConversationWithDuckId:） | `Models/ConversationManager.m` | ✅ 完成 |
| 发送 `chat_to_duck` WS 消息 | `Services/WebSocketService.m` | ✅ 完成 |
| 处理 `chat_to_duck_error`（Alert + 占位消息更新） | `Services/WebSocketService.m`、`ChatViewController.m` | ✅ 完成 |
| 处理 `chat_to_duck_accepted`（占位消息显示"处理中"） | `Services/WebSocketService.m`、`ChatViewController.m` | ✅ **本次修复** |
| 处理 `chat_to_duck_result`（显示结果/错误、停止 loading） | `Services/WebSocketService.m`、`ChatViewController.m` | ✅ **本次修复** |

**修复内容说明：**  
修复前，iOS 的 `WebSocketService.m` 不处理 `chat_to_duck_accepted` 和 `chat_to_duck_result` 消息类型，导致用户发送消息后 loading 状态永不消除、结果无法显示（沉默失败）。本次新增：
- `WebSocketServiceDelegate` 增加 `didAcceptChatToDuck:taskId:` 和 `didReceiveChatToDuckResult:duckId:taskId:success:error:` 两个可选方法
- `WebSocketService.m` 新增两个 `else if` 分支解析对应消息并回调 delegate
- `ChatViewController.m` 实现两个 delegate 方法，更新占位消息内容与状态、停止 loading

> **闭环链路（iOS）**：  
> 点击鸟图标 → 拉取 Duck 列表 → 选择 Duck → 创建 Duck 专属会话 → 发送消息 → `sendChatToDuck` → 收到 `accepted`（显示"处理中"）→ 收到 `result`（显示结果）。**完整闭环 ✅**

---

### 7.4 整体闭环评估

```
[iOS / Web 用户]
      │ 选择 Duck，发送消息
      ▼
[主 Backend ws_handler.py]
      │ 参数校验 → 检查在线/忙碌 → 生成 task_id
      │ → 发送 chat_to_duck_accepted 给用户
      │ → 本地 Duck: 内存队列 → LocalDuckWorker → AutonomousAgent
      │ → 远程 Duck: duck_ws.py → TASK 消息 → duck_client_ws.py
      ▼
[Duck 执行完毕]
      │ _on_task_done callback → chat_to_duck_result → 用户 WS
      │ 远程 Duck: duck_ws.py _handle_result → 同上
      ▼
[iOS ChatViewController]
      │ didReceiveChatToDuckResult → 更新消息 + 停止 loading
      ▼
[用户看到结果]

附：结果文件链路
[Duck Backend]
      │ POST /duck/upload-result → 主 Backend 保存
      ▼  
[主 Backend 返回 URL]
      │ 随 chat_to_duck_result.output 中的链接传递给用户
```

**三端闭环状态：完整 ✅**

---

### 7.5 待完善项（非阻塞）

| 项目 | 描述 | 优先级 |
|------|------|--------|
| Mac App：创建本地 Duck UI | 设置页「创建本地 Duck」入口，当前仅有导入 Egg；本机 Duck 需通过 Web/API 创建 | 中 |
| Mac App：Duck 模式隐藏无关 UI | Duck 模式下隐藏 Chow Duck 设置、隧道、模型配置等（文档设计目标，尚未实现） | 中 |
| iOS streaming 支持 | 当前 duck 直聊结果为单次返回（非流式），无增量渲染 | 低 |
| iOS：chat_to_duck 超时提示 | 600s 超时后 backend 解除 busy、WS 侧无主动推超时消息给用户 | 低 |
| Web 端 chat_to_duck UI | Web 前端暂未实现 Duck 选择 UI，仅有 API 封装 | 中 |
