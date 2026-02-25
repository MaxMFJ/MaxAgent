# MacAgent 工具自我升级系统设计

## 一、概述

当用户请求的功能无法被现有工具满足时，系统应能：
1. **检测** 无法执行的任务
2. **规划** 通过 LLM 分配升级任务
3. **调度** 电脑资源（Cursor、终端等）完成代码升级
4. **反馈** 向用户通报升级状态，形成闭环

---

## 二、无法执行任务的检测场景

| 场景 | 检测点 | 触发条件 |
|------|--------|----------|
| 工具不存在 | `ToolRegistry.execute()` | `未知工具: {name}` |
| 工具执行失败 | `ToolResult.success=False` | 特定错误码或关键词 |
| LLM 调用未知工具 | AgentCore `_execute_tools` | 工具未注册 |
| 用户显式请求新能力 | 语义分析 | "添加"、"实现"、"支持" + 功能描述 |
| DynamicTool 不足以满足 | dynamic_tool 返回建议 | 需要服务器级新工具 |

---

## 三、升级流程（闭环）

```
用户请求 → 检测无法执行 → 触发升级流程
                              ↓
                    ┌─────────────────────────┐
                    │  LLM 升级规划器          │
                    │  - 分析需要的工具        │
                    │  - 选择执行方式          │
                    │    (Cursor / Terminal)   │
                    └───────────┬─────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │  1. 广播升级状态         │
                    │     status: upgrading   │
                    │  2. 下发 Chat 通知用户   │
                    │     "系统正在升级..."    │
                    └───────────┬─────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │  资源调度器              │
                    │  - open Cursor + 路径    │
                    │  - 终端执行脚本/命令     │
                    └───────────┬─────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │  升级完成                │
                    │  - 动态加载新工具        │
                    │  - 或 安排服务器重启     │
                    │  - 广播 status: normal   │
                    └─────────────────────────┘
```

---

## 四、资源调度

### 4.1 Cursor 调度

- **用途**：需要编辑项目代码、创建新工具文件时
- **实现**：`open -a "Cursor" /path/to/MacAgent` 或 AppleScript
- **增强**：可写入 `.cursor/prompts/upgrade.md` 指定 AI 要完成的任务

### 4.2 终端调度

- **用途**：pip install、创建文件、执行脚本
- **实现**：复用 `TerminalTool`，或独立 `ResourceDispatcher`

### 4.3 调度决策（LLM）

LLM 根据「需要创建的代码类型」选择：
- 需要改 Python 工具 → Cursor
- 需要安装依赖 / 执行命令 → Terminal
- 两者都需 → 先 Terminal 再 Cursor

---

## 五、反馈机制

### 5.1 服务端状态

```python
class ServerStatus(str, Enum):
    NORMAL = "normal"       # 正常运行
    UPGRADING = "upgrading" # 升级中
    RESTARTING = "restarting"  # 即将重启
```

### 5.2 WebSocket 消息

| 类型 | 字段 | 说明 |
|------|------|------|
| `status_change` | `status`, `message` | 状态变更，所有客户端接收 |
| `content` | `content` | 作为系统消息："系统正在升级，请稍候..." |
| `upgrade_progress` | `phase`, `detail` | 升级进度（可选） |

### 5.3 连接状态统一

- `ConnectionManager` 维护全局 `server_status`
- 新连接建立时，`connected` 消息附带 `server_status`
- `/health` 返回 `status` 字段
- 前端：根据 status 显示「升级中」、「即将重启」等 UI

### 5.4 升级前通知

```
1. 设置 server_status = UPGRADING
2. broadcast_all({ type: "status_change", status: "upgrading", message: "..." })
3. broadcast 一条 content："系统正在升级，请稍候..."
4. 执行升级逻辑
5. 如需重启：status = RESTARTING，再次广播，然后退出
6. 重启后 status = NORMAL
```

---

## 六、新工具自动引入

### 6.1 轻量级：动态注册

- 新工具写在 `data/generated_tools/*.py`
- `ToolRegistry` 支持 `load_from_directory()`
- 升级完成后调用 `registry.load_from_directory()` 并刷新 schema

### 6.2 完整级：修改 __init__.py + 重启

- LLM 生成新工具代码
- 写入 `tools/xxx_tool.py`
- 修改 `tools/__init__.py` 的 `get_all_tools()`
- 安排重启，重启后自动加载

---

## 七、实现文件规划

| 文件 | 职责 |
|------|------|
| `agent/self_upgrade/` | 升级流程编排、Planner、Strategy Router、Executors、Validation、Activation |
| `agent/resource_dispatcher.py` | Cursor/终端调度实现 |
| `main.py` | ServerStatus、status_change 广播、/health |
| `tools/registry.py` | 动态加载扩展 |
| `agent/core.py` | 检测无法执行 → 触发 orchestrator |

---

## 八、前端对接说明

### 8.1 WebSocket 消息

| 消息类型 | 说明 | 前端处理 |
|----------|------|----------|
| `connected` | 连接成功，含 `server_status` | 显示连接状态，若 `server_status === "upgrading"` 则显示「升级中」 |
| `status_change` | 状态变更 | 更新 UI：`upgrading` → 显示升级中，`normal` → 正常 |
| `tool_upgrade_needed` | 检测到工具不存在 | 显示「正在升级以支持该功能」 |
| `content` + `is_system` | 系统消息（如升级通知） | 以系统消息样式显示 |

### 8.2 HTTP 接口

| 接口 | 说明 |
|------|------|
| `GET /health` | 含 `server_status` 字段 |
| `GET /server-status` | 仅返回 `server_status` |
| `POST /upgrade/trigger` | 手动触发升级，Body: `{ reason, user_message }` |
| `POST /tools/reload` | 动态加载 `tools/generated/` 下新工具，无需重启 |
| `POST /upgrade/restart?delay=5` | 触发重启流程：先广播 restarting，延迟后退出 |

### 8.3 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `MACAGENT_AUTO_TOOL_UPGRADE` | 是否自动触发工具升级 | `true` |

### 8.4 动态加载目录

- 新工具文件放入 `tools/generated/`，格式参考 `example_tool.py`
- 启动时自动加载；运行中可通过 `POST /tools/reload` 加载新文件

---

## 九、安全与限制

- 升级触发可配置：`MACAGENT_AUTO_TOOL_UPGRADE=false` 关闭自动升级
- **安全加固**：沙箱、签名校验、行为白名单、Git 回滚 详见 **[UPGRADE_SECURITY_DESIGN.md](./UPGRADE_SECURITY_DESIGN.md)**
- GitHub 仓库设置：**[GITHUB_SETUP_GUIDE.md](./GITHUB_SETUP_GUIDE.md)**
