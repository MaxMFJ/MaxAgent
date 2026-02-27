# 技能 Capsule

技能 Capsule 支持**本地**和**在线**技能：本地自定义脚本 + OpenClaw 社区技能库（数千个，按需加载）。

## 何时使用
- 用户任务涉及「技能」「自动化」「批量处理」「特定场景」时，先 capsule find 再执行
- 系统推荐匹配 Capsule 时，直接调用 capsule execute
- **用户问「能加载哪些工具」「有哪些技能」「在线工具」时**：说明有 OpenClaw 在线技能库（Coding、Git、DevOps、PDF、搜索等分类），用 capsule find(task=...) 搜索后 execute 执行，不要只说「聚焦本地」而忽略在线技能能力

## 调用流程
1. capsule find(task="用户任务关键词") → 获取匹配列表
2. 若有匹配，capsule execute(capsule_id="...", inputs={...})
3. 指令型(instruction_mode=true)：按返回的步骤，用 file_operations/terminal 等逐步完成

## 禁止
- 不要跳过 find 直接猜测 capsule_id
- 不要用 terminal 执行本应由 capsule 封装的操作
