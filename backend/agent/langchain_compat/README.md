# LangChain 兼容层（部分引入）

在保持 Chow Duck 主流程不变的前提下，**可选**接入 LangChain 能力，用于补齐「可组合性、可观测性、标准 Agent 循环」等能力。

## 启用方式

1. **安装可选依赖**（未安装时自动用原生 Agent，无报错）
   ```bash
   cd backend
   pip install -r requirements.txt -r requirements-langchain.txt
   ```

2. **兼容模式默认开启**  
   `ENABLE_LANGCHAIN_COMPAT` 默认为 `true`。若已安装 langchain，Chat 会优先走 LangChain；**执行中任一步骤抛错会自动回退到原生 `AgentCore`**，不影响对话可用性。  
   若要关闭兼容、始终用原生，可设置：
   ```bash
   export ENABLE_LANGCHAIN_COMPAT=false
   ```

## 行为说明

- **未安装 langchain**：始终使用原生 `AgentCore.run_stream`。
- **已安装且启用**：Chat 优先由 LangChain 的 `create_tool_calling_agent` + `AgentExecutor` 执行；**若执行失败则本次请求自动回退到原生**，并打 warning 日志。
- **已安装但关闭**（`ENABLE_LANGCHAIN_COMPAT=false`）：与「未安装」一致，仅用原生。

启用后（且未回退时）行为：
  - 使用同一套 Chow Duck 的 LLM（`LLMClient`）、工具（`ToolRegistry`）和上下文（`ContextManager`）。
  - 通过适配器将 `LLMClient` 转为 LangChain `BaseChatModel`，工具转为 LangChain `BaseTool`，从而获得 LCEL、`bind_tools`、Agent 循环等能力。
  - WebSocket 下发的 chunk 类型与原生一致（`content`、`tool_call`、`tool_result`、`stream_end` 等），前端无需改动。

## 模块说明

| 模块 | 作用 |
|------|------|
| `llm_adapter.py` | 将 `LLMClient` 适配为 LangChain `BaseChatModel`，支持 `bind_tools` 与 `tool_calls` 返回 |
| `tool_adapter.py` | 将 `ToolRegistry` / 语义裁剪后的工具转为 LangChain `StructuredTool`，执行仍走 `tools.router.execute_tool` |
| `memory_adapter.py` | 将 `ConversationContext` 转为 LangChain `BaseChatMessageHistory`，用于注入历史消息 |
| `runner.py` | `LangChainChatRunner`：使用 LangChain Agent 执行对话，产出与 `AgentCore.run_stream` 相同的 chunk 流 |

## 不足部分直接接入 LangChain 的对应关系

| 文档中分析的不足 | 接入方式 |
|------------------|----------|
| 无统一 Runnable / LCEL | 兼容模式下用 LangChain 的 Agent + LCEL 执行循环 |
| 工具无 Runnable | 通过 `tool_adapter` 转为 LangChain 工具，可参与 `bind_tools` 与链式调用 |
| 可观测 / Trace | `runner._get_trace_callbacks()` 预留 callback 列表，可挂 LangSmith/OpenTelemetry；设 `LANGCHAIN_TRACING_V2=true` 即可用 LangSmith |
| 记忆 / 多轮 | 仍用 Chow Duck 的 `ContextManager`；向量存储已按 `session_id` 隔离，后续可扩展命名空间（如 user_id）做跨会话长期记忆并设 token 上限 |

## 已实现的增强（与文档 4.x 对应）

| 增强项 | 实现位置 | 说明 |
|--------|----------|------|
| **可观测钩子** | `runner._get_trace_callbacks()`、`AgentExecutor(callbacks=...)` | 预留 callback 列表；设 `LANGCHAIN_TRACING_V2=true` 与 `LANGCHAIN_API_KEY` 即可接入 LangSmith，也可在此追加 OpenTelemetry 等 |
| **工具中间件** | `tools.middleware` + `tools.router.execute_tool` | 预执行钩子 `register_pre_hook(name, args)`、后执行钩子 `register_post_hook(name, args, result)`，用于校验、限流、结果截断/格式化等，与 LangChain 兼容层共用同一 `execute_tool` |
| **记忆与命名空间** | 当前 `get_vector_store(session_id)` 即按会话隔离 | 后续可在 `VectorMemoryStore` / `ContextManager` 增加可选 `namespace`（如 user_id），做跨会话检索并沿用 `max_context_tokens` / `semantic_count` 控制 token |
| **步骤抽象** | 兼容层已用 `create_tool_calling_agent`，内部为 AgentAction/AgentFinish | 若引入 LangGraph，可将「一步」显式为图的一跳，便于扩展人工审核、多步策略 |

## 可选依赖未安装时

未安装 `langchain-core` / `langchain` 时，本包可正常导入，但 `get_langchain_chat_runner()` 返回 `None`，`get_chat_runner()` 会退回使用原生 `AgentCore`，不会报错。

## 默认开启与风险评审

兼容模式**默认开启**；执行失败会**自动回退到原生**，详见：  
`docs/LangChain兼容模式-默认开启评审.md`

## 是否在启动时自动安装 LangChain？

**不建议**在主程序启动时自动执行 `pip install`：权限、网络、虚拟环境等容易导致失败或副作用。  
推荐：在设置中提供「启用 LangChain 兼容」开关，用户开启后若未安装依赖，后端仍用原生 Runner；若需使用 LangChain，由用户自行在终端执行：  
`pip install -r requirements-langchain.txt`。

## 客户端配置（用户选择是否开启）

- **GET /config** 返回中已包含 `langchain_compat: true/false`（当前是否启用）。
- **POST /config** 请求体可传 `{"langchain_compat": true}` 或 `{"langchain_compat": false}`，会写入 `backend/data/agent_config.json`，**无需重启后端**即生效。  
Mac/iOS 客户端可在「设置」中增加「使用 LangChain 进行对话」开关，调用上述接口即可。
