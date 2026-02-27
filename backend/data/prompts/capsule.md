# 技能 Capsule

## 何时使用
- 用户任务涉及「技能」「自动化」「批量处理」「特定场景」时，先 capsule find 再执行
- 系统推荐匹配 Capsule 时，直接调用 capsule execute

## 调用流程
1. capsule find(task="用户任务关键词") → 获取匹配列表
2. 若有匹配，capsule execute(capsule_id="...", inputs={...})
3. 指令型(instruction_mode=true)：按返回的步骤，用 file_operations/terminal 等逐步完成

## 禁止
- 不要跳过 find 直接猜测 capsule_id
- 不要用 terminal 执行本应由 capsule 封装的操作
