# MacAgent 项目上下文（供 Agent 注入）

MacAgent 是 macOS 系统级智能助手，可代表用户执行终端、文件、截图、邮件等操作；定位为「系统级助手」而非代码 IDE。

## 关键目录与入口

- `backend/main.py`：入口，FastAPI、路由注册
- `backend/agent/autonomous_agent.py`：自主执行主循环（ReAct）
- `backend/agent/action_schema.py`：动作与 TaskContext、结构化 memory
- `backend/agent/safety.py`：危险命令/路径统一校验
- `backend/app_state.py`：全局状态与 FeatureFlags（v3.1 开关）

## 能力边界

- 支持：文件操作、终端、应用控制、截图、邮件、技能 Capsule、workspace 上报
- 与 Cursor 差异：无 IDE 内置文件关联，需 workspace 上报；终端单命令执行无持久 shell；安全靠 execution_guard/safety.py。详见 docs/痛点分析与解决方案.md 第四节。

## 约定

- 修改/覆盖文件前先 read 确认内容；删除前先 info 确认路径。
- 技能：先 capsule find 再 execute；instruction_mode 时按指令用已有工具逐步完成。
- 危险命令与路径由 agent/safety.py 统一校验，禁止写系统目录、执行 rm -rf / 等。
- 长任务中每 N 步会注入「当前目标」与（若启用）「当前建议子目标」，避免漂移。

## 文档

- 文档索引与阅读顺序：docs/README.md
- 详细规划：docs/V3.1_PLAN.md、docs/ROADMAP_2026_BENCHMARK_AGENT.md
