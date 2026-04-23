# MacAgent Open Agent API — 生产级架构规范

**版本：** v1.0 (MVP)  
**协议层：** Agent Capability Protocol (ACP) over HTTP/2 + WebSocket  
**设计原则：** Machine-First, Zero-Inference, Autonomous-Native

---

## 架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                    External Agent / App Agent                        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  ACP (Agent Capability Protocol)
         ┌─────────────────▼──────────────────────┐
         │         /.well-known/agent.json          │  ← Phase 1
         │         Agent Manifest Entry Point        │
         └─────────────────┬──────────────────────┘
                           │
         ┌─────────────────▼──────────────────────┐
         │         /agent/capabilities             │  ← Phase 2
         │         Capability Graph (JSON-LD)      │
         └────┬────────────┬──────────────┬───────┘
              │            │              │
      ┌───────▼──┐  ┌──────▼────┐  ┌─────▼──────┐
      │  /agent/ │  │  /agent/  │  │  /agent/   │
      │  invoke  │  │  tasks    │  │  stream    │
      │ Phase 3  │  │ Phase 4   │  │ Phase 5    │
      └───────┬──┘  └──────┬────┘  └─────┬──────┘
              │            │              │
         ┌────▼────────────▼──────────────▼────┐
         │        MacAgent Internal Core         │
         │  ┌──────────┐  ┌──────────────────┐  │
         │  │AgentCore │  │AutonomousAgent   │  │
         │  │(ReAct)   │  │(Checkpoint-based)│  │
         │  └────┬─────┘  └────────┬─────────┘  │
         │  ┌────▼─────────────────▼──────────┐ │
         │  │    30+ Tools  |  Duck Registry   │ │
         │  │    Capsules   |  DAG Engine      │ │
         │  └─────────────────────────────────┘ │
         └─────────────────────────────────────-─┘
```

---

## Phase 1 — Agent Manifest (自描述入口)

### 目的
向任意外部 Agent 提供单一、零歧义的能力声明。外部 Agent 仅需访问一个 URL 即可完整理解 MacAgent 的所有执行模式、协议和鉴权方式，无需扫描端点。

### 架构决策
- 遵循 `/.well-known/` RFC 规范（类比 OpenID Connect Discovery）
- 格式：JSON (JSON-LD@context 扩展)
- HTTP: `GET /.well-known/agent.json` — 公开，无需鉴权
- 必须包含：能力图链接、调用标准、流协议、安全描述

### JSON Schema

```json
{
  "$schema": "https://agentprotocol.ai/schema/manifest/v1",
  "acp_version": "1.0",
  "agent": {
    "id": "macagent-primary",
    "name": "MacAgent",
    "version": "3.5.0",
    "description": "Autonomous multi-agent execution platform with 30+ tools",
    "type": "orchestrator",         // orchestrator | worker | hybrid
    "platform": "macos",
    "instance_id": "uuid-v4-here"  // 运行时唯一标识
  },
  "capabilities": {
    "graph_url": "/agent/capabilities",
    "modes": ["chat", "autonomous", "dag", "capsule"],
    "autonomous": true,
    "delegation": {
      "strategies": ["direct", "single", "multi"],
      "duck_types": ["general","coder","crawler","designer","tester","image","video"]
    },
    "hitl": true,
    "session_resume": true,
    "subagents": { "max_concurrent": 3 },
    "streaming": { "sse": true, "websocket": true }
  },
  "protocols": {
    "invocation": "/agent/invoke",
    "tasks": "/agent/tasks",
    "stream": "/agent/stream/{task_id}",
    "negotiate": "/agent/negotiate",
    "deeplink_scheme": "agent://macagent"
  },
  "auth": {
    "methods": ["none", "bearer", "capability_token"],
    "token_endpoint": "/agent/auth/token",
    "scope_info": "/agent/auth/scopes"
  },
  "limits": {
    "max_task_seconds": 3600,
    "max_concurrent_tasks": 10,
    "max_payload_bytes": 10485760
  },
  "metadata": {
    "contact": "https://macagent.ai",
    "docs": "/agent/docs",
    "openapi": "/openapi.json"
  }
}
```

### 内部实现映射

```python
# backend/routes/agent_manifest.py  (新建)
from fastapi import APIRouter
from app_state import feature_flags, get_llm_client

router = APIRouter()

@router.get("/.well-known/agent.json", include_in_schema=False)
async def agent_manifest():
    return AgentManifest(
        acp_version="1.0",
        agent=AgentInfo(id="macagent-primary", ...),
        capabilities=build_capabilities_from_state(),
        ...
    )

def build_capabilities_from_state() -> CapabilityBlock:
    # 从 app_state.feature_flags 读取 ENABLE_HITL, ENABLE_SUBAGENT 等
    # 从 DuckRegistry 读取当前 duck 类型
    ...
```

### 迁移策略
无破坏性变更。新增 `/.well-known/` 路由，不修改现有 `/health` 端点。

### 风险
| 风险 | 缓解 |
|------|------|
| manifest 与实际状态不同步 | 运行时动态生成，不缓存 |
| 暴露内部拓扑 | 可配置 `detail_level: minimal|full`，受 token 等级控制 |

---

## Phase 2 — Capability Graph Model

### 目的
提供机器可读的能力图谱，Agent 无需扫描端点即可理解 tools、capsules、ducks、DAG 的关系与调用路径。

### 架构决策
- 格式：JSON-LD（兼容 Schema.org Action 模型）
- 核心实体：`Tool`、`Capsule`、`DuckType`、`DAGTemplate`、`Workflow`
- HTTP: `GET /agent/capabilities?format=graph|flat|openapi`

### Graph Schema

```json
{
  "@context": "https://agentprotocol.ai/context/v1",
  "@type": "AgentCapabilityGraph",
  "generated_at": "2026-03-18T00:00:00Z",
  "nodes": {
    "tools": [
      {
        "id": "tool:terminal",
        "type": "Tool",
        "name": "TerminalTool",
        "description": "Execute shell commands with streaming output",
        "tags": ["system", "code", "shell"],
        "input_schema": {
          "type": "object",
          "required": ["command"],
          "properties": {
            "command": { "type": "string" },
            "timeout": { "type": "integer", "default": 30 },
            "stream": { "type": "boolean", "default": false }
          }
        },
        "output_schema": {
          "type": "object",
          "properties": {
            "stdout": { "type": "string" },
            "exit_code": { "type": "integer" }
          }
        },
        "requires_permissions": ["terminal"],
        "latency_hint_ms": 500,
        "autonomous_safe": true
      }
    ],
    "capsules": [
      {
        "id": "capsule:email.send",
        "type": "Capsule",
        "name": "SendEmail",
        "task_type": "email_send",
        "tags": ["email", "automation"],
        "capability": ["mail", "template"],
        "input_schema": { ... },
        "output_schema": { ... },
        "step_count": 3,
        "avg_duration_ms": 4000
      }
    ],
    "duck_types": [
      {
        "id": "duck:coder",
        "type": "DuckType",
        "variant": "CODER",
        "specialty": ["python", "javascript", "debugging", "review"],
        "accepts_tasks": ["code_generation", "debugging", "testing"],
        "available_count": 2,   // 运行时动态填充
        "busy_count": 0
      }
    ],
    "dag_templates": [
      {
        "id": "dag:research-write-publish",
        "type": "DAGTemplate",
        "name": "Research → Write → Publish",
        "nodes": [
          { "id": "n1", "tool": "tool:web_search", "depends_on": [] },
          { "id": "n2", "tool": "duck:writer",     "depends_on": ["n1"] },
          { "id": "n3", "tool": "capsule:publish", "depends_on": ["n2"] }
        ]
      }
    ]
  },
  "relations": [
    { "from": "capsule:email.send", "uses": "tool:mail", "type": "uses" },
    { "from": "duck:coder",         "can_use": "tool:terminal", "type": "can_use" }
  ]
}
```

### 内部实现映射

```python
# backend/routes/agent_capability.py
from tools.registry import ToolRegistry
from capsules.manager import CapsuleManager
from services.duck_registry import DuckRegistry

@router.get("/agent/capabilities")
async def capability_graph(format: str = "graph"):
    tools = ToolRegistry.get_all()
    capsules = CapsuleManager.list_all()
    ducks = await DuckRegistry.get_instance().list_all()
    return build_graph(tools, capsules, ducks)
```

### 迁移策略
从现有 `/tools`、`/capsules`、`/duck/list` 聚合数据，现有端点不变。

---

## Phase 3 — Agent Action Schema (统一调用标准)

### 目的
用单一 `agent.invoke(action)` 格式统一 tools、capsules、DAG、duck delegation 调用，消除外部 Agent 学习各端点的负担。

### 架构决策
- HTTP: `POST /agent/invoke`
- 同步响应 + 可选流式 (`stream: true` → 返回 task_id)
- 基于 `target` 字段路由：`tool:X` / `capsule:X` / `dag:X` / `duck:X`

### 请求 Schema

```json
POST /agent/invoke
Authorization: Bearer <token>

{
  "request_id": "req-uuid-external",
  "target": "tool:terminal",           // tool: | capsule: | dag: | duck:
  "action": "execute",
  "params": {
    "command": "ls -la /tmp",
    "timeout": 10
  },
  "execution": {
    "mode": "sync",                    // sync | async | stream
    "timeout_ms": 5000,
    "priority": "normal",              // low | normal | high | critical
    "retry": { "max": 2, "backoff_ms": 500 }
  },
  "context": {
    "session_id": "sess-123",          // 可选，用于状态关联
    "caller_agent_id": "gpt-agent-001",
    "trace_id": "trace-abc"
  }
}
```

### 响应 Schema (sync)

```json
{
  "request_id": "req-uuid-external",
  "task_id": "task-uuid-internal",
  "status": "completed",             // pending | running | completed | failed
  "result": {
    "stdout": "file1.txt\nfile2.txt",
    "exit_code": 0
  },
  "meta": {
    "duration_ms": 243,
    "tool_used": "tool:terminal",
    "tokens_used": 0,
    "cost_usd": 0.0
  }
}
```

### 响应 Schema (async)

```json
{
  "request_id": "req-uuid-external",
  "task_id": "task-uuid-internal",
  "status": "pending",
  "stream_url": "/agent/stream/task-uuid-internal",
  "poll_url": "/agent/tasks/task-uuid-internal",
  "estimated_ms": 30000
}
```

### 路由适配映射

```python
# backend/routes/agent_invoke.py

TARGET_ROUTERS = {
    "tool":    route_to_tool,       # → ToolRegistry.execute()
    "capsule": route_to_capsule,    # → CapsuleManager.execute()
    "dag":     route_to_dag,        # → DagOrchestrator.execute()
    "duck":    route_to_duck,       # → DelegateTaskScheduler.delegate()
    "agent":   route_to_agent_chat  # → AgentCore.run()
}

@router.post("/agent/invoke")
async def agent_invoke(req: InvokeRequest, token=Depends(verify_capability_token)):
    prefix, name = req.target.split(":", 1)
    handler = TARGET_ROUTERS.get(prefix)
    if not handler:
        raise HTTPException(400, f"Unknown target prefix: {prefix}")
    return await handler(name, req)
```

### 风险
| 风险 | 缓解 |
|------|------|
| target 注入攻击 | 白名单校验 `prefix`；`name` 在 Registry 中查找 |
| sync 超时阻塞 | 默认 `timeout_ms: 30000`，超时自动降级为 async |

---

## Phase 4 — Autonomous Task API

### 目的
允许外部 Agent 以安全、可检查点、可恢复的方式发起自主执行任务，无需保持长连接。

### 架构决策
- 创建：`POST /agent/tasks`
- 查询：`GET /agent/tasks/{task_id}`
- 恢复：`POST /agent/tasks/{task_id}/resume`
- Fork：`POST /agent/tasks/{task_id}/fork`
- 取消：`DELETE /agent/tasks/{task_id}`
- 自主任务 = AutonomousAgent + TaskPersistence + CheckpointManager

### 任务创建请求

```json
POST /agent/tasks
{
  "goal": "研究竞争对手定价，生成对比表格并发送邮件",
  "mode": "autonomous",              // autonomous | chat | capsule | dag
  "execution_policy": {
    "max_steps": 50,
    "max_duration_s": 3600,
    "require_hitl_for": ["send_email", "delete_file"],  // 敏感动作触发人工审批
    "auto_checkpoint": true,
    "checkpoint_interval_steps": 10,
    "on_failure": "pause"            // pause | retry | abort
  },
  "context": {
    "session_id": "sess-abc",        // 可选，关联到已有会话
    "inputs": { "recipient": "ceo@company.com" },
    "constraints": ["no_external_calls_after_midnight"]
  },
  "caller": {
    "agent_id": "external-agent-001",
    "callback_url": "https://external.ai/hooks/task-complete"  // Webhook
  }
}
```

### 任务状态响应

```json
GET /agent/tasks/{task_id}
{
  "task_id": "task-uuid",
  "status": "running",
  "goal": "研究竞争对手...",
  "progress": {
    "steps_completed": 12,
    "steps_total_estimate": 30,
    "current_action": "web_search: site:competitor.com pricing",
    "last_checkpoint_id": "ckpt-0010"
  },
  "checkpoints": [
    {
      "id": "ckpt-0010",
      "step": 10,
      "timestamp": "2026-03-18T12:00:00Z",
      "summary": "已完成网页抓取3个竞争对手"
    }
  ],
  "hitl_pending": null,
  "created_at": "2026-03-18T11:00:00Z",
  "estimated_completion": "2026-03-18T12:30:00Z"
}
```

### Webhook 回调格式

```json
POST {caller.callback_url}
{
  "event": "task.completed",
  "task_id": "task-uuid",
  "result": { ... },
  "duration_s": 4230,
  "steps_executed": 28
}
```

### 内部实现映射

```python
# 映射到现有 AutonomousAgent + task_persistence.py
class AutonomousTaskAPIHandler:
    async def create(self, req: TaskCreateRequest) -> TaskResponse:
        # 1. 生成 task_id
        # 2. 调用 AutonomousAgent.run(goal, policy) — 后台 asyncio.create_task
        # 3. 注册到 TaskTracker (已有)
        # 4. 返回 task_id + poll URL
    
    async def on_checkpoint(self, task_id, checkpoint):
        # 存入 task_persistence.py (已有)
        # 若 caller.callback_url 存在 → 触发 Webhook
```

---

## Phase 5 — Streaming Protocol Standard

### 目的
定义标准化流式事件格式，替代现有自定义 WebSocket 消息，同时支持 SSE 和 WebSocket，保持语义一致。

### 架构决策
- EventType 统一枚举（替换现有散乱 type 字符串）
- SSE: `GET /agent/stream/{task_id}` (Accept: text/event-stream)
- WS: `WS /agent/ws/{task_id}`
- 可见性级别：`minimal` / `standard` / `verbose` / `debug`

### 标准事件 Taxonomy

```
event: agent.thinking        ← LLM 推理阶段 (可含 reasoning_tokens)
event: agent.planning        ← 生成执行计划
event: agent.action          ← 工具调用发起
event: agent.action_result   ← 工具调用结果
event: agent.progress        ← 进度更新 (step N/M)
event: agent.checkpoint      ← 检查点保存
event: agent.hitl_request    ← 等待人工审批
event: agent.hitl_resolved   ← 人工审批结果
event: agent.delegated       ← 委托给 Duck/SubAgent
event: agent.delegation_done ← 委托结果返回
event: agent.done            ← 任务完成
event: agent.error           ← 错误（含恢复建议）
event: agent.cancelled       ← 任务取消
```

### SSE 事件格式

```
id: evt-001
event: agent.action
data: {
  "task_id": "task-uuid",
  "seq": 5,
  "timestamp": "2026-03-18T12:00:00.123Z",
  "visibility": "standard",
  "payload": {
    "tool": "tool:terminal",
    "params": { "command": "ls /tmp" },
    "estimated_duration_ms": 200
  }
}

id: evt-002
event: agent.action_result
data: {
  "task_id": "task-uuid",
  "seq": 6,
  "timestamp": "2026-03-18T12:00:00.400Z",
  "payload": {
    "tool": "tool:terminal",
    "success": true,
    "result": { "stdout": "file1.txt", "exit_code": 0 },
    "duration_ms": 243
  }
}

id: evt-099
event: agent.done
data: {
  "task_id": "task-uuid",
  "seq": 99,
  "payload": {
    "summary": "任务已完成，已发送邮件至 ceo@company.com",
    "artifacts": [
      { "type": "file", "path": "/tmp/report.csv", "url": "/agent/artifacts/task-uuid/report.csv" }
    ],
    "stats": { "steps": 28, "duration_s": 4230, "tokens_used": 12400 }
  }
}
```

### 可见性级别控制

```json
GET /agent/stream/{task_id}?visibility=standard
```

| 级别 | 包含事件 |
|------|---------|
| `minimal` | done, error, checkpoint |
| `standard` | + action, progress, delegated |
| `verbose` | + thinking, planning, action_result |
| `debug` | 全部，含内部 token 流 |

### 内部实现映射

```python
# backend/routes/agent_stream.py
# 适配现有 ws_handler.py 输出到标准事件格式

class StreamingAdapter:
    """将 ws_handler 的内部消息映射到标准 ACP 事件"""
    
    MAPPING = {
        "thinking":          "agent.thinking",
        "action":            "agent.action",
        "progress":          "agent.progress",
        "duck_delegated":    "agent.delegated",
        "duck_task_complete":"agent.delegation_done",
        "done":              "agent.done",
        "error":             "agent.error",
    }
    
    def adapt(self, raw_msg: dict) -> ACPEvent:
        event_type = self.MAPPING.get(raw_msg["type"], "agent.unknown")
        return ACPEvent(event=event_type, payload=raw_msg)
```

---

## Phase 6 — Capability Negotiation

### 目的
两个 Agent 在任务委托前交换能力声明、资源限制、执行模式偏好，避免不兼容的任务分配。

### 架构决策
- HTTP: `POST /agent/negotiate`
- 一次往返完成协商（非多轮握手，减少延迟）
- 返回：匹配能力、执行建议、合约 token

### 协商请求

```json
POST /agent/negotiate
{
  "proposer": {
    "agent_id": "external-agent-001",
    "version": "2.1.0",
    "capabilities": ["web_search", "text_generation", "summarization"],
    "limits": {
      "max_task_seconds": 300,
      "preferred_mode": "async"
    }
  },
  "task_hint": {
    "type": "research_and_code",
    "estimated_steps": 20,
    "requires": ["terminal", "browser", "code_execution"],
    "preferred_duck": "coder",
    "constraints": ["no_external_api_calls"]
  },
  "negotiation": {
    "required_capabilities": ["terminal", "code_execution"],
    "optional_capabilities": ["docker", "git"],
    "max_cost_usd": 0.50,
    "timeout_s": 600
  }
}
```

### 协商响应

```json
{
  "negotiation_id": "neg-uuid",
  "accepted": true,
  "matched_capabilities": ["terminal", "code_execution", "git"],
  "unavailable": [],
  "execution_plan": {
    "recommended_target": "duck:coder",
    "available_ducks": 2,
    "estimated_duration_s": 180,
    "estimated_cost_usd": 0.12,
    "mode": "async"
  },
  "contract": {
    "token": "cap-token-xyz",        // 能力令牌，限定任务范围
    "expires_at": "2026-03-18T13:00:00Z",
    "allowed_tools": ["terminal", "file", "git"],
    "denied_tools": ["network", "docker"]
  },
  "warnings": [
    "docker capability available but excluded per constraint"
  ]
}
```

### 内部实现

```python
# backend/routes/agent_negotiate.py
@router.post("/agent/negotiate")
async def negotiate(req: NegotiateRequest):
    available = set(ToolRegistry.get_all_ids())
    matched = req.negotiation.required_capabilities & available
    
    if not req.negotiation.required_capabilities.issubset(available):
        return NegotiateResponse(accepted=False, reason="Missing required capabilities")
    
    contract_token = CapabilityTokenFactory.create(
        allowed_tools=matched | req.negotiation.optional_capabilities & available,
        ttl_s=req.negotiation.timeout_s,
        task_bound=True
    )
    return NegotiateResponse(accepted=True, contract=contract_token, ...)
```

---

## Phase 7 — Agent Deep-Linking

### 目的
支持通过 URI scheme 从任意上下文（App Agent、自动化触发器、CLI、跨 Agent 链）直接调用 MacAgent 能力。

### Deep-Link URI 规范

```
格式:  agent://macagent/<resource>?<params>

示例:
  agent://macagent/run?capsule=email.send&to=ceo@co.com
  agent://macagent/run?tool=terminal&command=ls%20-la
  agent://macagent/run?goal=写一个爬虫&mode=autonomous
  agent://macagent/dag/execute?template=research-write-publish
  agent://macagent/duck/delegate?type=coder&task=debug%20this%20function
  agent://macagent/session/resume?session_id=sess-123
```

### HTTP 转换层

```
GET /agent/deeplink?uri=agent://macagent/run?capsule=email.send
```

从 macOS App Agent (MacAgentApp) 注册 URL scheme，通过 `NSWorkspace.open(url)` 触发。

### macOS App Agent 集成

```swift
// MacAgentApp 注册 URL scheme
// Info.plist: CFBundleURLSchemes = ["agent"]

func application(_ app: NSApplication, open urls: [URL]) {
    for url in urls {
        guard url.host == "macagent" else { return }
        AgentDeepLinkRouter.handle(url)
    }
}

class AgentDeepLinkRouter {
    static func handle(_ url: URL) {
        let path = url.path          // /run, /dag/execute, etc.
        let params = url.queryParameters
        // 转换为 POST /agent/invoke 请求
        BackendClient.invoke(target: resolveTarget(path, params), params: params)
    }
}
```

### 跨 Agent 链调用

```
Agent A → agent://macagent/run?goal=X → MacAgent 执行
MacAgent → agent://remote-agent/run?goal=Y → 远程 Agent 执行（EvoMap）
```

### 安全约束
- Deep-link 调用必须携带 `?token=<capability_token>`
- macOS scheme 仅接受本地调用（`localhost` 源）
- 禁止 `agent://macagent/admin/...` 等管理路径

---

## Phase 8 — Security & Trust Model

### 目的
提供分层、能力范围内的安全模型，支持 HITL 升级，防止未授权 Agent 滥用高风险动作。

### 架构：4 层信任链

```
Layer 0: Public        ← /.well-known/agent.json, /agent/capabilities (只读)
Layer 1: Session Token ← 基础调用能力 (聊天、工具只读类)
Layer 2: Capability Token ← 协商后范围限定令牌 (允许特定工具集)
Layer 3: Admin Token   ← 配置变更、Duck 管理、特征标志修改
```

### Token 结构 (JWT)

```json
{
  "sub": "external-agent-001",
  "iss": "macagent-primary",
  "iat": 1710720000,
  "exp": 1710723600,
  "scope": {
    "tier": 2,
    "allowed_tools": ["terminal", "file", "git"],
    "denied_tools": ["network", "docker", "mail"],
    "allowed_modes": ["chat", "autonomous"],
    "max_task_duration_s": 600,
    "hitl_bypass": false,        // false = 敏感动作强制 HITL
    "max_cost_usd": 1.00
  },
  "delegation_chain": [
    "root-agent",
    "orchestrator-001",
    "external-agent-001"
  ]
}
```

### 委托信任链

```
Root Agent (Admin Token)
  └─ delegates to → Orchestrator Agent (Tier 2 Token, scope=reduced)
       └─ delegates to → Duck/Sub-Agent (Tier 1 Token, scope=task-only)
```

每一层委托只能收窄权限，不能扩展。由 Token Factory 强制：

```python
def delegate_token(parent_token: CapabilityToken, 
                   requested_scope: Scope) -> CapabilityToken:
    # 新令牌范围 = 父令牌范围 ∩ requested_scope
    new_scope = parent_token.scope.intersect(requested_scope)
    return CapabilityToken(scope=new_scope, delegation_chain=parent_token.chain + [self.agent_id])
```

### HITL 触发规则

```python
HITL_TRIGGERS = {
    "tool:mail":   ["send"],          # 发邮件强制 HITL
    "tool:file":   ["delete"],        # 删除文件强制 HITL
    "tool:terminal": ["rm -rf", "sudo"],  # 危险命令强制 HITL
    "tool:docker": ["*"],             # Docker 操作全部 HITL
}

class HITLMiddleware:
    async def pre_execute(self, tool_id, action, params):
        if self.should_trigger_hitl(tool_id, action, params):
            if not token.scope.hitl_bypass:
                request_id = await hitl_service.create_request(tool_id, action, params)
                await self.wait_for_approval(request_id, timeout=120)
```

### OWASP 对应防护

| 风险 | 防护措施 |
|------|---------|
| Broken Access Control | 能力令牌scope强制交叉 |
| Injection (Command) | terminal 工具参数沙箱化，禁止拼接执行 |
| SSRF | network 工具目标 URL 白名单校验 |
| Auth Failures | JWT 签名 + exp 强制校验，无 none 算法 |
| Logging Failures | 所有 Tier ≥ 2 操作写 audit log |

---

## Phase 9 — 兼容层 (Backward Compatibility Adapter)

### 策略
**零破坏**：所有现有端点保持不变。新 ACP 层作为独立路由前缀 `/agent/` 叠加。

### 适配器架构

```
外部 Agent (新协议)     内部现有路由
─────────────────       ─────────────────
POST /agent/invoke  →   ToolRegistry.execute()
                    →   CapsuleManager.execute()
                    →   DagOrchestrator.execute()
                    →   DelegateTaskScheduler.delegate()

GET /agent/tasks/{id} → app_state.TaskTracker.get()
DELETE /agent/tasks/{id} → AgentCore.stop()

GET /agent/stream/{id} → connection_manager (现有 WS 事件转 SSE)

/.well-known/agent.json → 聚合 /health + /tools + /duck/stats + /capsules
/agent/capabilities    → 聚合 /tools + /capsules + /duck/list
```

### 路由冲突处理

```python
# main.py 注册顺序
app.include_router(agent_acp_router, prefix="")   # 新路由 /agent/*
app.include_router(all_routers)                   # 现有路由不变
```

### 双协议并行支持期

```
v1.0 (MVP): /agent/* 与原始路由并存
v2.0:       废弃公告附加在原始路由响应头: Deprecation: "2027-01-01"
v3.0:       原始路由迁移为 /legacy/* (可选保留)
```

---

## Phase 10 — 未来 Agent 生态

### Agent Marketplace (技能市场)

```
POST /agent/marketplace/publish
{
  "skill_id": "capsule:email-campaign-optimizer",
  "author_agent_id": "coder-duck-001",
  "schema": { ... },
  "price_per_call_usd": 0.01,
  "trust_level": "verified"         // verified | unverified
}

GET /agent/marketplace/search?tags=email,marketing&max_price=0.05
```

### Federated Execution (联邦执行)

```
agent://remote-macagent.partner.ai/run?goal=...

内部流程:
1. /agent/negotiate → 远程 MacAgent 实例
2. 收到 contract_token (范围限定)
3. POST /agent/invoke → 远程实例
4. 通过 SSE /agent/stream 接收结果
```

### Agent Identity & DID

```json
GET /.well-known/agent-did.json
{
  "did": "did:macagent:sha256:abc123",
  "publicKey": "ed25519-public-key-base64",
  "serviceEndpoint": "https://macagent.local:8765/agent",
  "capabilities_hash": "sha256:xyz789"  // capabilities 内容哈希，可验证
}
```

### Discovery Registry (注册中心)

```
GET /agent/registry/peers        ← 已知 MacAgent 实例列表
POST /agent/registry/announce    ← 向 EvoMap 广播自身
GET /agent/registry/search?capability=docker
```

---

## 核心 Schema 汇总

### InvokeRequest

```python
class InvokeRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target: str               # "tool:terminal" | "capsule:email.send" | "duck:coder" | "dag:X"
    action: str = "execute"
    params: Dict[str, Any]
    execution: ExecutionPolicy = ExecutionPolicy()
    context: Optional[InvokeContext] = None

class ExecutionPolicy(BaseModel):
    mode: Literal["sync", "async", "stream"] = "sync"
    timeout_ms: int = 30000
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    retry: RetryPolicy = RetryPolicy()

class InvokeContext(BaseModel):
    session_id: Optional[str] = None
    caller_agent_id: Optional[str] = None
    trace_id: Optional[str] = None
    capability_token: Optional[str] = None
```

### ACPEvent

```python
class ACPEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:8]}")
    event: str                # agent.action | agent.done | ...
    task_id: str
    seq: int
    timestamp: datetime
    visibility: str = "standard"
    payload: Dict[str, Any]
```

---

## 实现优先级路线图

### MVP (4 周)

| 优先级 | 模块 | 工作量 |
|-------|------|-------|
| P0 | `/.well-known/agent.json` (Phase 1) | 2天 |
| P0 | `POST /agent/invoke` 路由分发 (Phase 3) | 3天 |
| P0 | `GET /agent/stream/{id}` SSE 适配 (Phase 5) | 3天 |
| P1 | `/agent/capabilities` 图谱聚合 (Phase 2) | 2天 |
| P1 | `/agent/tasks` CRUD (Phase 4) | 3天 |
| P1 | Capability Token 生成与校验 (Phase 8) | 3天 |

### v2.0 (8 周后)

- Phase 6: 能力协商 `/agent/negotiate`
- Phase 7: Deep-link URI scheme
- Phase 9: 原始端点废弃公告

### v3.0 (16 周后)

- Phase 10: 联邦执行 + Agent Identity (DID)
- Marketplace
- 跨实例 DAG

---

## 关键实施注意事项

1. **`/agent/invoke` 中 `target` 字段必须白名单校验** — 防止路径遍历注入
2. **流式事件 `seq` 字段必须单调递增** — 外部 Agent 可检测丢包
3. **Capability Token 使用 RS256 签名** — 私钥不离开 MacAgent 实例
4. **协商返回的 `contract.token` 有任务生命周期** — 任务结束自动失效
5. **Webhook 回调使用 HMAC-SHA256 签名** — 防止伪造回调
6. **所有 `/agent/*` 端点写 audit log** — 满足 Phase 8 可观测性要求 