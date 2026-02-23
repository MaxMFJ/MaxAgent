# 工具自我升级功能测试指南

## 一、功能概览

1. **动态加载新工具**：新工具放入 `tools/generated/` 后，调用 `POST /tools/reload` 即可生效，无需重启
2. **重启前通知**：调用 `POST /upgrade/restart` 会先广播 `restarting` 和「即将重启」，延迟后退出

---

## 二、动态加载测试

### 2.1 测试已存在的示例工具

示例工具 `example_generated` 已在 `tools/generated/example_tool.py`。

**步骤 1：启动服务**

```bash
cd MacAgent/backend
source venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8765
```

**步骤 2：确认工具列表（启动时已自动加载）**

```bash
curl -s http://127.0.0.1:8765/tools | python3 -m json.tool | grep -A2 example_generated
```

应能看到 `example_generated` 工具。

**步骤 3：通过 Chat 调用示例工具**

用 MacAgent 客户端发送：

```
使用 example_generated 工具，message 填 "hello"
```

或直接调用 LLM（会选用 example_generated 工具）。

### 2.2 测试动态 reload（无需重启）

**步骤 1：新建工具**

在 `tools/generated/` 下创建 `my_test_tool.py`：

```python
from tools.base import BaseTool, ToolResult, ToolCategory

class MyTestTool(BaseTool):
    name = "my_test"
    description = "我的测试工具"
    category = ToolCategory.CUSTOM
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, data={"msg": "my_test ok"})
```

**步骤 2：调用 reload 接口**

```bash
curl -X POST http://127.0.0.1:8765/tools/reload
```

预期返回：`{"status": "ok", "loaded_tools": ["my_test"]}`

**步骤 3：验证工具已注册**

```bash
curl -s http://127.0.0.1:8765/tools | python3 -m json.tool | grep -A2 my_test
```

然后通过 Chat 使用 `my_test` 工具。

---

## 三、重启前通知测试

### 3.1 使用 curl 触发重启

```bash
curl -X POST "http://127.0.0.1:8765/upgrade/restart?delay=5"
```

预期：返回 `{"status": "triggered", "message": "将在 5 秒后重启"}`

### 3.2 用 WebSocket 观察状态变化

在另一个终端启动 WebSocket 客户端，观察广播消息：

```bash
# 使用 websocat 或 wscat（需先安装）
wscat -c "ws://127.0.0.1:8765/ws"
```

连接后发送 `{"type":"ping"}` 保持连接。  
在另一个终端执行 `curl -X POST "http://127.0.0.1:8765/upgrade/restart?delay=5"`。

预期收到类似：

- `{"type": "status_change", "status": "restarting", "message": "..."}`
- `{"type": "content", "content": "⏳ 系统即将重启，请稍候重连...", "is_system": true}`

约 5 秒后服务退出。

### 3.3 健康检查中的状态

```bash
curl -s http://127.0.0.1:8765/health
```

触发重启后、进程退出前，`server_status` 会变为 `"restarting"`。

---

## 四、完整升级流程测试

模拟「工具不存在 → 触发升级 → 动态加载」流程。

**步骤 1：让 LLM 调用一个不存在的工具**

在 Chat 中发送类似：

```
请使用 not_exist_tool 工具
```

**步骤 2：预期行为**

1. 工具执行失败，返回「未知工具」
2. 若 `MACAGENT_AUTO_TOOL_UPGRADE=true`（默认），会自动触发升级
3. 收到 `tool_upgrade_needed` 类型的 WebSocket 消息
4. 编排器执行升级：广播 `upgrading`、下发系统消息等
5. 若在 `tools/generated/` 中新增了工具文件，编排器会调用 `load_generated_tools()`
6. 升级完成后广播「已动态加载新工具」或「请调用 /tools/reload」

**步骤 3：手动触发升级**

```bash
curl -X POST http://127.0.0.1:8765/upgrade/trigger \
  -H "Content-Type: application/json" \
  -d '{"reason": "未知工具: xxx_tool", "user_message": "需要 xxx 功能"}'
```

---

## 五、环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `MACAGENT_AUTO_TOOL_UPGRADE` | 是否在检测到未知工具时自动触发升级 | `true` |

关闭自动升级：

```bash
export MACAGENT_AUTO_TOOL_UPGRADE=false
uvicorn main:app --host 127.0.0.1 --port 8765
```
