# REST API 端点参考

后端服务地址：`http://127.0.0.1:8765`，WebSocket：`ws://127.0.0.1:8765/ws`

---

## 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 基础健康检查 |
| GET | `/health/deep` | 深度检查（LLM/磁盘/内存/vector_db/tool_router/task_tracker/traces/evomap） |
| GET | `/server-status` | 服务器状态 |
| GET | `/connections` | WebSocket 连接数 |

---

## 配置管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/config` | 获取 LLM 配置 |
| PUT | `/config` | 更新 LLM 配置（provider/apiKey/baseUrl/model） |
| GET | `/config/smtp` | 获取邮件配置 |
| PUT | `/config/smtp` | 更新邮件配置 |
| GET | `/config/github` | 获取 GitHub 配置 |
| PUT | `/config/github` | 更新 GitHub 配置 |
| POST | `/config/install-langchain` | 安装 LangChain 依赖 |

---

## 对话与任务

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 非流式对话 |
| WebSocket | `/ws` | 流式对话（chat/autonomous/stop/resume 等） |

---

## 工具管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tools` | 列出所有已注册工具 |
| GET | `/tools/pending` | 查看待审批的工具变更 |
| POST | `/tools/approve` | 审批工具变更 |
| POST | `/tools/reload` | 重新加载所有工具 |

---

## MCP 服务管理 (v3.4)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/mcp/servers` | 列出所有 MCP 服务器及连接状态 |
| POST | `/mcp/servers` | 添加并连接 MCP 服务器 |
| DELETE | `/mcp/servers/{name}` | 断开并移除 MCP 服务器 |
| GET | `/mcp/tools` | 列出所有 MCP 工具 |
| POST | `/mcp/tools/call` | 调用 MCP 工具 |

### 添加 MCP 服务器请求体

```json
{
  "name": "filesystem",
  "transport": "stdio",
  "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
  "env": {},
  "url": "",
  "headers": {},
  "timeout": 30.0
}
```

### 调用 MCP 工具请求体

```json
{
  "server": "memory",
  "tool": "search_nodes",
  "arguments": {"query": "test"}
}
```

---

## 文件快照与回滚 (v3.4)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/rollback/snapshots` | 列出快照（支持 `task_id`/`session_id`/`limit` 参数） |
| POST | `/rollback` | 回滚到指定快照 |
| DELETE | `/rollback/snapshots/{id}` | 删除快照记录 |

---

## 上下文查询 (v3.4)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/context` | 完整上下文快照（可选 `session_id` 参数） |
| GET | `/context/tokens` | Token 用量统计 |
| GET | `/context/files` | 会话创建的文件列表 |

### 响应示例

```json
{
  "conversation": {
    "session_id": "abc123",
    "message_count": 15,
    "estimated_tokens": 3200,
    "max_context_tokens": 32000,
    "created_files": ["/tmp/report.md"]
  },
  "active_tasks": [],
  "available_tools": ["terminal", "screenshot", "web_search"],
  "mcp": {"servers": [], "tool_count": 0},
  "snapshots": [],
  "model_routing": {
    "stats": {"total": 42, "by_model": {}},
    "tier_configs": {
      "fast": {"provider": "local", "model": ""},
      "strong": {"provider": "deepseek", "model": "deepseek-reasoner"},
      "cheap": {"provider": "deepseek", "model": "deepseek-chat"}
    }
  },
  "phase_stats": {"total": 12, "gather": 4, "act": 5, "verify": 3},
  "feature_flags": {},
  "generated_at": 1740000000.0
}
```

---

## FeatureFlag 管理 (v3.3)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/feature-flags` | 查询所有 Flag（含默认值、来源、当前值） |
| PATCH | `/feature-flags` | 热更新单个 Flag（无需重启） |
| POST | `/feature-flags/reset` | 重置所有 Flag 为默认值 |

### PATCH 请求体

```json
{
  "flag": "ENABLE_HITL",
  "value": true
}
```

---

## HITL 人工审批 (v3.3)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/hitl/pending` | 查询等待确认的动作列表 |
| POST | `/hitl/confirm/{action_id}` | 确认执行某动作 |
| POST | `/hitl/reject/{action_id}` | 拒绝执行某动作 |

---

## 审计日志 (v3.3)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/audit` | 查询审计日志（支持 `type`/`task_id`/`session_id`/日期过滤） |
| GET | `/audit/stats` | 审计统计摘要 |
| GET | `/audit/{log_id}` | 单条审计记录详情 |

---

## 会话持久化 (v3.3)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions` | 列出所有可恢复的会话 |
| GET | `/sessions/{id}/checkpoints` | 列出会话的检查点 |
| POST | `/sessions/{id}/resume` | 从检查点恢复会话执行 |
| POST | `/sessions/{id}/fork` | 从检查点分支新会话 |

---

## SubAgent (v3.3)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/subagents` | 列出所有活跃 SubAgent |
| GET | `/subagents/{task_id}` | 查询特定任务的 SubAgent 状态 |

---

## Traces 可观测 (v3.2)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/traces` | 列出所有 trace（支持 `limit` 参数） |
| GET | `/traces/{task_id}` | 获取单个 trace 摘要 |
| GET | `/traces/{task_id}/spans` | 获取 trace 的所有 span（支持分页） |
| DELETE | `/traces/{task_id}` | 删除 trace |

---

## 监控与统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/monitor/episodes` | 历史情景记忆 |
| GET | `/monitor/statistics` | 统计摘要 |
| GET | `/usage-stats/overview` | 使用量概览（Token/RPM/TPM） |
| GET | `/usage-stats/model-analysis` | 模型使用分析 |
| GET | `/logs` | 系统日志（支持 `limit`/`since_index`） |

---

## 系统消息

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/system-messages` | 获取系统消息列表 |
| POST | `/system-messages/{id}/read` | 标记已读 |
| POST | `/system-messages/read-all` | 全部标记已读 |
| DELETE | `/system-messages` | 清除消息 |

---

## 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/workspace` | 上报工作区信息（cwd/open_files） |
| GET | `/permissions/status` | 权限状态检测 |
| GET | `/memory/status` | 向量记忆状态 |
| GET | `/local-llm/status` | 本地模型状态 |
| GET | `/model-selector/status` | 模型选择器状态 |
| POST | `/upgrade/self` | 触发自我升级 |
| GET | `/tunnel/status` | 隧道状态 |
| POST | `/tunnel/start` | 启动隧道 |
| POST | `/tunnel/stop` | 停止隧道 |
| GET | `/capsules` | 技能 Capsule 列表 |
| GET | `/evomap/*` | EvoMap 进化网络（需 ENABLE_EVOMAP=true） |
| GET | `/self-healing/*` | 自愈诊断与修复 |
| GET | `/auth/status` | 认证状态 |

---

## 环境变量配置

### v3.3 新增

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `MACAGENT_ENABLE_HITL` | false | 人工审批开关 |
| `MACAGENT_HITL_CONFIRMATION_TIMEOUT` | 120（秒） | 审批超时时间 |
| `MACAGENT_ENABLE_AUDIT_LOG` | true | 审计日志开关 |
| `MACAGENT_AUDIT_LOG_MAX_SIZE_MB` | 100 | 审计日志最大磁盘占用 |
| `MACAGENT_ENABLE_SESSION_RESUME` | false | 会话恢复开关 |
| `MACAGENT_ENABLE_SUBAGENT` | false | SubAgent 并行开关 |
| `MACAGENT_SUBAGENT_MAX_CONCURRENT` | 3 | 最大并行子 Agent 数 |
| `MACAGENT_SUBAGENT_TIMEOUT` | 300（秒） | 单个 SubAgent 超时 |
| `MACAGENT_ENABLE_IDEMPOTENT_TASKS` | false | 幂等任务开关 |
| `MACAGENT_IDEMPOTENT_CACHE_TTL` | 86400（秒） | 幂等缓存 TTL |
