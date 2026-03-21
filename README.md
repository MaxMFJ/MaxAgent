# Chow Duck - macOS AI 智能助手

基于 SwiftUI + Python 后端的 macOS 本地 AI Agent。支持**流式对话（ReAct）**与**自主长任务（Autonomous）**两种模式，具备多模型选择、上下文向量检索、技能 Capsule、工具自我升级与自愈能力，Mac/iOS 多端会话同步。

---

## 功能特性

### 对话与执行
- **流式对话（Chat）**：ReAct 循环，按需调用工具（文件、终端、应用、截图、邮件等），支持断线重连
- **自主任务（Autonomous）**：长 horizon 多步执行，三阶段主循环（Gather → Act → Verify），可选反思、模型选择、自适应停止
- **基础工具**：文件、终端、应用控制、系统信息、剪贴板、截图、浏览器、邮件、日历、通知
- **扩展工具**：Docker、网络诊断、数据库、开发工具、联网搜索、视觉、鼠标键盘模拟
- **MCP 生态**：通过 Model Context Protocol 连接外部 MCP 服务器（GitHub、Brave Search、Filesystem 等），即插即用

### Mac 客户端
- **监控仪表板**：执行时间线、系统状态、历史分析、实时日志流、Token 统计
- **MCP 管理**：内置 6 个 MCP 服务一键连接，支持自定义添加
- **语音输入**：实时语音识别（中/英）、静音自动提交
- **TTS 朗读**：流式按句朗读，支持中英文
- **权限管理**：辅助功能、屏幕录制、自动化状态检测与引导
- **HITL 人工审批**：危险操作弹窗确认（如删除文件、高风险命令）
- **快照回滚**：文件操作前自动快照，支持 write/delete/move/copy 一键 undo

### 架构与运维
- **上下文与记忆**：BGE 向量检索（可关）、会话持久化、情景记忆
- **工具自我升级**：Planner → Strategy → Executor → Validation → Activation，沙箱执行
- **自愈**：诊断引擎、修复计划与执行
- **多客户端**：Mac/iOS 同时连接，按 session 同步；可选 Cloudflared 隧道

### DAG 分布式任务运行时
- **DAG 编排**：复杂任务自动拆解为有向无环图，子任务由专职 Duck Agent 并行执行
- **Pull-Based 调度**：类型化 Ready Queue + 加权轮转公平调度，Worker 主动拉取任务
- **状态机**：9 态严格状态转换（CREATED → PENDING → ENQUEUED → ASSIGNED → RUNNING → COMPLETED / FAILED），幂等完成守卫
- **可靠性**：Append-only Journal 崩溃恢复、Lease 超时僵尸任务保护、自适应背压控制
- **Worker 健康**：Per-duck 健康评分 + 自动隔离，慢 DAG 检测
- **分布式**：Remote Pull Protocol（HTTP + Bearer Token），支持远程 Worker 水平扩展
- **可观测性**：就绪等级（OK/DEGRADED/CRITICAL）、Task Explain、Queue State、Worker 诊断、Stuck 检测

> 详细文档：[docs/DAG_RUNTIME.md](docs/DAG_RUNTIME.md)

### Open Agent API (ACP)
- **Agent Card**（`GET /agent`）：对外发布 Agent 能力描述、支持的技能列表
- **能力协商**（`POST /agent/negotiate`）：与其他 Agent 动态协商交互协议和能力
- **任务调用**（`POST /agent/invoke`）：接收外部任务请求并交由内部 Agent 执行
- **异步任务**（`GET /agent/tasks/{id}`）：查询异步任务状态和结果
- **流式执行**（`POST /agent/stream`）：SSE 实时流式返回执行进度
- **认证**（`POST /agent/auth`）：Token 签发与验证，保护所有 ACP 端点

---

## 系统要求

- **macOS 14.0+**
- **Python 3.10+**
- **Node.js 18+**（MCP 需要）
- **Xcode 15.0+**（编译 Mac 应用）

---

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置 LLM

**方式一：环境变量**
```bash
export DEEPSEEK_API_KEY="your-api-key-here"
```

**方式二：Mac 应用设置**  
启动应用后，在设置中选择 Provider（DeepSeek / New API / Ollama / LM Studio）并填写 API Key、Base URL、模型名。

### 3. 启动

```bash
cd backend
python main.py
```

服务地址：`http://127.0.0.1:8765`，WebSocket：`ws://127.0.0.1:8765/ws`。

### 4. 启动 Mac 应用

```bash
open MacAgentApp/MacAgentApp.xcworkspace   # 若使用 CocoaPods
# 或
open MacAgentApp/MacAgentApp.xcodeproj
```

在 Xcode 中运行。应用内可控制后端启停、打开监控仪表板、配置服务与权限。

---

## 配置说明

### LLM 配置

| 配置项 | 说明 |
|--------|------|
| Provider | DeepSeek / New API / Ollama / LM Studio |
| API Key | 云端模型必填 |
| Base URL | 自定义 API 地址（如 LM Studio 默认 `http://127.0.0.1:1234/v1`）|
| Model | 模型名称 |

### 环境变量（可选）

| 变量 | 默认 | 说明 |
|------|------|------|
| ENABLE_VECTOR_SEARCH | true | 是否启用 BGE 向量检索 |
| ENABLE_EVOMAP | false | 是否启用 EvoMap |
| AUTH_ENABLED, AUTH_TOKEN | - | 隧道/iOS 认证 |
| HF_ENDPOINT | - | 国内可设 `https://hf-mirror.com` 加速 BGE 下载 |
| WEB_SEARCH_BACKEND | auto | `auto` 默认免费优先；可选 `hybrid/jina/searxng/ddg/ddg_html` |
| WEB_READ_BACKEND | auto | `auto` 默认内置免费提取；可选 `hybrid/jina/builtin` |
| JINA_API_KEY | - | 启用 Jina Search / Reader，适合给 Agent 提供更干净的网页正文 |
| SEARXNG_URL | - | 自托管 SearXNG 实例，例如 `http://localhost:8080` |
| WEB_SEARCH_TIMEOUT | 15 | 搜索和抓取请求超时时间（秒） |
| JINA_TOKEN_BUDGET | 8000 | Jina Reader 返回正文的预算上限 |
| WEB_RESEARCH_MAX_PAGES | 5 | `web_search(action=research)` 最多抓取的来源页数 |
| WEB_RESEARCH_EXCERPT_CHARS | 1600 | research 模式保留的单页正文摘要长度 |
| CRAWL4AI_HEADLESS | true | Crawl4AI 抓取时是否启用无头浏览器 |

### MCP 服务器

| MCP 服务 | 包名 | 前置条件 |
|----------|------|---------|
| GitHub | `@modelcontextprotocol/server-github` | `GITHUB_TOKEN` |
| Brave Search | `@modelcontextprotocol/server-brave-search` | `BRAVE_API_KEY` |
| Sequential Thinking | `@modelcontextprotocol/server-sequential-thinking` | Node.js 18+ |
| Puppeteer | `@modelcontextprotocol/server-puppeteer` | Node.js 18+ |
| Filesystem | `@modelcontextprotocol/server-filesystem` | Node.js 18+ |
| Memory | `@modelcontextprotocol/server-memory` | Node.js 18+ |

### 推荐的联网搜索增强

如果你希望 `web_search` 从“能用”升级到“更稳更适合 Agent”，推荐至少启用下面其中一种：

```bash
# 方案 1：免费优先（推荐默认）
export WEB_SEARCH_BACKEND="auto"
export WEB_READ_BACKEND="auto"
export SEARXNG_URL="http://127.0.0.1:8080"

# 方案 2：Jina Search / Reader（按量计费，显式启用）
export JINA_API_KEY="your-jina-key"
export WEB_SEARCH_BACKEND="hybrid"
export WEB_READ_BACKEND="hybrid"

# 也可以强制指定某个后端
export WEB_SEARCH_BACKEND="searxng"
export WEB_READ_BACKEND="jina"
```

当前后端优先级：
- 免费默认 `auto`：
- `search` / `news`：`SearXNG -> DuckDuckGo -> DuckDuckGo HTML fallback`
- `extract_text`：`builtin HTML extraction`
- `research`：`Search backend -> Crawl4AI -> builtin extraction`
- 显式付费增强 `hybrid`：
- `search` / `news`：`Jina -> SearXNG -> DuckDuckGo -> DuckDuckGo HTML fallback`
- `extract_text`：`Jina Reader -> builtin HTML extraction`
- `research`：`Search backend -> Crawl4AI -> Jina Reader -> builtin extraction`

---

## 部署说明

**后台已内置到 Mac App**：构建时通过 Build Phase 将 `backend/` 复制到 App Bundle，用户无需单独部署后端。

- **启动/关闭**：应用内工具栏的「后端」开关控制启停
- **可写数据**：配置持久化到 `~/Library/Application Support/com.macagent.app/backend_data/`
- **RAG/向量搜索**：用户首次启用时自动安装到 Application Support

---

## 权限管理

在 **设置 → 权限** 中完成：

| 权限 | 用途 |
|------|------|
| App 辅助功能 | MacAgentApp 自身控制键鼠 |
| Python 辅助功能 | 后端模拟键鼠（Agent 核心）|
| 屏幕录制 | 截图、视觉感知 |
| 自动化 (System Events) | AppleScript 控制其他应用 |

---

## 许可证

MIT License
