# MacAgent 项目上下文（供 Agent 注入）

MacAgent 是 macOS 全能智能助手，融合系统级操作能力与多领域知识咨询。定位为「通用型电脑助手」——既能代表用户执行终端、文件、截图、邮件等 macOS 系统操作，也能作为产品设计、开发、生活、购物、出行、法律等多领域的智能顾问。

## 能力体系

三层能力架构：
1. **自身知识**：知识问答、方案撰写、建议咨询等，直接回答无需工具
2. **内置工具**：文件操作、终端、应用控制、截图、邮件、input_control、web_search
3. **扩展能力**：技能 Capsule（社区库数千个按需加载）+ MCP Server（外部协议工具）+ 工具自升级

## 关键目录与入口

- `backend/main.py`：入口，FastAPI、路由注册
- `backend/agent/autonomous_agent.py`：自主执行主循环（ReAct）
- `backend/agent/action_schema.py`：动作与 TaskContext、结构化 memory
- `backend/agent/safety.py`：危险命令/路径统一校验
- `backend/app_state.py`：全局状态与 FeatureFlags

## 约定

- 知识/咨询类问题直接回答，不调用工具
- 修改/覆盖文件前先 read 确认内容；删除前先 info 确认路径
- 技能：先 capsule find 再 execute；instruction_mode 时按指令用已有工具逐步完成
- 危险命令与路径由 agent/safety.py 统一校验，禁止写系统目录
- 长任务中每 N 步注入「当前目标」，避免漂移
