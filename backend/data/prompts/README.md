# Chow Duck Prompt Bootstrap

参考 OpenClaw 等开源 Agent 的模块化 prompt 设计。各文件在每次请求时按顺序加载并合并到 System Prompt。

## 文件说明

| 文件 | 用途 | 可编辑 |
|------|------|--------|
| identity.md | 身份、多领域能力矩阵、输出风格 | ✓ |
| behavior.md | 响应策略（先判断再行动）、工具失败处理、追问规则 | ✓ |
| tools.md | 三层工具体系（知识→内置→扩展）、GUI 操作规范 | ✓ |
| capsule.md | Capsule/MCP/工具三者关系与调用流程 | ✓ |
| constraints.md | 能力边界（能做/局限/不能做）、安全约束 | ✓ |
| MACAGENT.md | 项目上下文注入（类 CLAUDE.md） | ✓ |
| agent_evolved_rules.md | 自升级追加规则（位于 data/） | 自升级可写 |

## 配置

- `prompt_loader.py` 中 `BOOTSTRAP_MAX_CHARS`：单文件最大字符数（默认 8000）
- `BOOTSTRAP_TOTAL_MAX_CHARS`：总注入上限（默认 20000）
- 缺失文件会跳过，不影响其他文件加载

## 查询分层

- **SIMPLE**（LITE prompt）：问候、纯追问 → 仅加载 identity + behavior
- **COMPLEX**（FULL prompt）：操作执行、知识咨询 → 加载全部模块 + 动态注入

## 扩展

新增规则时：
1. 在对应 .md 文件追加内容，或新建 .md 文件
2. 在 `prompt_loader.py` 的 `BOOTSTRAP_FILES` 中加入（若新建）
3. 无需改代码逻辑，仅维护 markdown 即可
