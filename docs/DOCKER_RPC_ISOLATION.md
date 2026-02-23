# Docker 与进程隔离 - 结构预留

## 目标

为未来容器化与 RPC 分离预留结构：

- **Core** 可运行在容器中（无 GUI、无本地系统调用）
- **Runtime Adapter** 可独立为本地守护进程
- 通过 RPC 通信（HTTP/gRPC/WebSocket）

## 架构预留

```
                    ┌─────────────────────────────────┐
                    │  Core Agent (可容器化)           │
                    │  - agent/core.py                │
                    │  - tools/* (仅业务逻辑)          │
                    │  - 无平台 import                │
                    └──────────────┬──────────────────┘
                                   │ RPC
                    ┌──────────────▼──────────────────┐
                    │  Runtime Adapter Daemon          │
                    │  - runtime/mac_adapter 等        │
                    │  - 本地进程，有权调用系统 API    │
                    │  - osascript, pbcopy 等         │
                    └─────────────────────────────────┘
```

## 接口预留

```python
# runtime/rpc_client.py (待实现)
class RpcRuntimeAdapter(RuntimeAdapter):
    """通过 RPC 调用远程 Runtime Daemon"""
    async def open_app(self, ...): ...
    async def clipboard_read(self): ...
    # ...

# runtime/rpc_server.py (待实现)
# 将 MacRuntimeAdapter 暴露为 HTTP/gRPC 服务
```

## 实现步骤（未来）

1. 定义 Adapter RPC 协议（JSON-RPC 或 gRPC）
2. 实现 `RpcRuntimeAdapter` 与 Daemon 服务端
3. 通过配置选择：`local` | `rpc`
4. Core 部署到 Docker，Daemon 部署在宿主机
