# 本地 EvoMap Capsule 使用说明

无需 EvoMap 官方网络或邀请码，Agent 可直接从本地目录或公开 GitHub 仓库加载并执行 EvoMap 技能（Capsule）。

## 模块概览

| 模块 | 说明 |
|------|------|
| **Capsule Loader** | 从 `./capsules/`、`./capsules_cache/` 或 GitHub raw URL 加载 JSON/YAML |
| **Capsule Validator** | 校验 id、description、inputs、outputs、procedure/steps，标记 trusted=local_source |
| **Capsule Registry** | 本地库：按 capability / task_type / tags 索引，支持 find/list/get |
| **Capsule Executor** | 将 procedure 转为工具调用与子任务，支持 `{{input.xxx}}` 参数映射 |
| **Capsule Sync** | 可选：从配置的 GitHub 仓库拉取并缓存到 `./capsules_cache/` |

## Capsule 格式（EvoMap Skill 规范）

必需字段：

- `id`：唯一标识
- `description`：描述
- `inputs`：对象，键为参数名，值为 `{ type, description }`
- `outputs`：对象，描述输出结构
- `procedure` 或 `steps`：步骤数组

可选：`task_type`、`tags`、`capability`、`gene`、`metadata`、`signature`（兼容 EvoMap 规范）。

### 步骤类型

- **tool**：调用 Agent 已注册工具  
  - `tool`：工具名（如 `terminal`、`screenshot`）  
  - `args`：参数对象，支持占位符 `{{input.xxx}}`、`{{output.0.xxx}}`（上一步输出）
- **subtask**：子任务占位，可写 `description` 供上层使用

示例：

```json
{
  "id": "capsule_screenshot_desktop",
  "description": "截取当前桌面截图",
  "inputs": { "target": { "type": "string", "description": "full_screen 或 window" } },
  "outputs": { "result": { "type": "object" } },
  "procedure": [
    { "id": "step_0", "type": "tool", "tool": "screenshot", "args": { "target": "{{input.target}}" } }
  ],
  "task_type": "screenshot",
  "tags": ["screenshot", "截图"]
}
```

## 放置 Capsule

- **本地**：将 JSON/YAML 放入 `backend/capsules/`（或项目内 `./capsules/`）。
- **GitHub**：在 `.env` 或配置中设置 `CAPSULE_SOURCES`（逗号分隔的 raw URL），启动时会拉取到 `backend/capsules_cache/`。

环境变量示例：

```bash
CAPSULE_SOURCES=https://raw.githubusercontent.com/your-org/capsules/main/index.json
```

配置文件（可选）：`backend/config/capsule_sources.json`：

```json
{
  "capsule_sources": [
    "https://raw.githubusercontent.com/your-org/capsules/main/"
  ]
}
```

## Agent 如何调用 Capsule

1. **工具 `capsule`**（推荐）  
   - `capsule(action=list)`：列出所有已加载 Capsule  
   - `capsule(action=find, task="截图")`：按任务关键词查找  
   - `capsule(action=get, capsule_id="capsule_screenshot_desktop")`：获取详情  
   - `capsule(action=execute, capsule_id="capsule_screenshot_desktop", inputs={"target": "full_screen"})`：执行

2. **上下文增强**  
   每次对话解析任务时，会先查本地 Registry；若找到匹配 Capsule，会在系统提示中注入「本地 EvoMap Capsule」说明，引导模型调用 `capsule(action=execute, ...)`。

3. **HTTP API**  
   - `GET /capsules`：列表  
   - `GET /capsules/find?task=截图`：按任务查找  
   - `GET /capsules/{id}`：详情  
   - `POST /capsules/{id}/execute`：执行，body `{"inputs": {...}}`

## 使用示例（对话中）

用户：「帮我截一张屏幕图。」

1. Agent 收到任务，`evomap_enhance_context` 会从本地 Registry 找到 `capsule_screenshot_desktop`，并在上下文中提示可执行该 Capsule。  
2. Agent 调用：`capsule(action=execute, capsule_id="capsule_screenshot_desktop", inputs={"target": "full_screen"})`。  
3. Capsule Executor 执行 procedure：调用工具 `screenshot`，参数 `target=full_screen`。  
4. 将执行结果返回给用户。

## 与现有 EvoMap 的兼容

- 不依赖 EvoMap 网络 API，不需要注册节点或邀请码。  
- Capsule 结构保持 EvoMap 规范（含 gene、metadata、signature 等可选字段）。  
- 若已配置 EvoMap 网络，resolve 时仍会先查本地 Registry，再查网络；tool_not_found 时也会先查本地 Capsule，再走网络继承。

## 示例 Capsule 文件

- `backend/capsules/example_screenshot.json`：截图  
- `backend/capsules/example_terminal.json`：执行终端命令  

可直接在此基础上复制、修改 id 与 procedure 以扩展更多技能。
