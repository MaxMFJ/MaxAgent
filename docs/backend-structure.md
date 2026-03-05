# Backend 目录与模块说明

后端采用「入口 + 领域包」结构，避免根目录堆砌过多单文件。

---

## 顶层布局

```
backend/
├── main.py                 # 入口：lifespan、FastAPI、路由注册
├── app_state.py            # 全局状态（LLM/agent 单例、TaskTracker、FeatureFlags）
├── auth.py                 # 认证
├── connection_manager.py   # WebSocket 连接与 session 广播
├── ws_handler.py           # WebSocket /ws 消息分发
├── config/                 # 配置持久化（合并原根目录 4 个 config 文件）
├── core/                   # v3 框架层（错误模型、状态机、限流、超时）
├── agent/                  # Agent 能力（对话、自主执行、自愈、升级等）
├── routes/                 # HTTP 路由
├── tools/                  # 工具实现
├── runtime/                # 平台适配（mac/win/linux）
├── llm/                    # LLM 解析/修复等小工具
├── data/                   # 运行时数据（配置、上下文、episodes 等）
└── scripts/                # 脚本
```

---

## 命名区分

| 名称 | 含义 | 位置 |
|------|------|------|
| **core** | v3 底层框架（错误、状态机、并发、超时） | `backend/core/` |
| **agent.core** | 对话核心（ReAct、流式、工具调用） | `backend/agent/core.py` |
| **config** | 所有持久化配置的入口包 | `backend/config/` |

---

## config/ 包（配置合并）

原根目录的 `agent_config.py`、`llm_config.py`、`smtp_config.py`、`github_config.py` 已合并到 `config/` 包，数据仍写在 `backend/data/`：

- `config.agent_config` — Agent（如 LangChain 兼容）配置
- `config.llm_config` — LLM 提供商、API、模型、远程回退
- `config.smtp_config` — 发信 SMTP
- `config.github_config` — GitHub Token（技能源 / Capsule 同步）

引用方式：`from config.llm_config import load_llm_config` 等。

---

## core/ 包（v3 框架）

- `error_model` — AgentError、ErrorCategory、to_agent_error
- `task_state_machine` — TaskState、TaskStateMachine
- `concurrency_limiter` — Autonomous/LLM 并发限流
- `timeout_policy` — 统一超时配置（占位）

---

## agent/ 包

- **核心执行**：`core.py`（AgentCore）、`autonomous_agent.py`、`action_schema.py`、`stop_policy.py`
- **上下文与记忆**：`context_manager.py`、`task_context_manager.py`、`episodic_memory.py`（v3.2：重要性加权 memory）
- **反思**：`reflect_engine.py`（v3.2：失败分类 + 专用 prompt 模板）
- **LLM/模型**：`llm_client.py`（v3.2：extra_body/Extended Thinking）、`local_llm_manager.py`、`model_selector.py`
- **Capsule/技能**：`capsule_*.py`、`skill_adapter.py`、`open_skill_sources.py`
- **自愈**：`self_healing/`、`self_healing_worker.py`、`error_service.py`
- **自升级**：`self_upgrade/`、`upgrade_service.py`
- **EvoMap**：`evomap_*.py`
- **事件与通知**：`event_bus.py`、`event_schema.py`、`system_message_service.py`
- **LangChain 兼容**：`langchain_compat/`

---

## routes/ 与 tools/

- **routes/**：按领域拆分的 APIRouter。已注册路由：
  - `health`（含 `/health/deep` v3.2 新增）
  - `auth`、`config`、`chat`、`tools`、`upgrade`
  - `logs`、`memory`、`self_healing`、`evomap`、`capsules`
  - `workspace`、`monitor`、`usage_stats`、`tunnel`、`permissions`、`files`
  - `traces`（v3.2 新增，`/traces` REST API）
- **tools/**：各工具实现；`generated/` 为动态生成工具；工具注册与路由在 `tools/router.py`、`tools/registry.py`。

---

## scripts/ 目录

- `scripts/run_benchmark.py`（v3.2 新增）：Benchmark 自动化脚本，B1-B7 用例，通过 WebSocket 连接后端执行，输出成功率/耗时统计。
- `scripts/check_ollama.py`：Ollama 本地 LLM 可用性检测。
- `scripts/test_local_parse.py`：本地模型输出解析测试。

---

## 数据与脚本

- **data/**：由各 config 与 agent 模块读写（如 `data/llm_config.json`、`data/contexts/`、`data/episodes/`、`data/traces/`）。不纳入版本控制的运行时文件应已在 `.gitignore`。
- **scripts/**：独立脚本（如下载 embedding 模型、SMTP 测试），非服务常驻代码。

---

## 相关文档

- 文档总览与主线目标点：[README.md](README.md)
- 目标与路线图：[主线目标与路线图.md](主线目标与路线图.md)
