# Chow Duck Prompt Bootstrap

参考 OpenClaw 等开源 Agent 的模块化 prompt 设计。各文件在每次请求时按顺序加载并合并到 System Prompt。

## 文件说明

| 文件 | 用途 | 可编辑 |
|------|------|--------|
| identity.md | 身份、核心能力、输出风格 | ✓ |
| behavior.md | 行为准则、工具失败处理、追问规则 | ✓ |
| tools.md | 各工具使用规则（terminal/mail/升级等） | ✓ |
| capsule.md | 技能 Capsule 规则 | ✓ |
| agent_evolved_rules.md | 自升级追加规则（位于 data/） | 自升级可写 |

## 配置

- `prompt_loader.py` 中 `BOOTSTRAP_MAX_CHARS`：单文件最大字符数（默认 8000）
- `BOOTSTRAP_TOTAL_MAX_CHARS`：总注入上限（默认 20000）
- 缺失文件会跳过，不影响其他文件加载

## 扩展

新增规则时：
1. 在对应 .md 文件追加内容，或新建 .md 文件
2. 在 `prompt_loader.py` 的 `BOOTSTRAP_FILES` 中加入（若新建）
3. 无需改代码逻辑，仅维护 markdown 即可
