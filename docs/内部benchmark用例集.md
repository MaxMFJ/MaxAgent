# 内部 Benchmark 用例集

用于回归与 Plan-and-Execute 效果评估的典型任务及预期。跑一次可产出「通过率 + 平均步数/token」等指标。

## 用例列表

| 编号 | 任务描述 | 预期行为/结果 |
|------|----------|----------------|
| B1 | 帮我检查系统状态 | 应调用 capsule（若有对应技能）或 get_system_info / 终端命令 |
| B2 | 修改 config.json 里的 port 为 3000 | 应先 read 再 write，不直接覆盖 |
| B3 | 启动 Flask 开发服务器 | 应使用 terminal 的 `background: true` |
| B4 | 项目在哪 / 做到哪一步了 | 仅根据对话历史回答，不重新执行创建或命令 |
| B5 | 先 cd /tmp，再 ls | 第二条命令应复用 /tmp 作为 cwd（终端会话） |
| B6 | 生成一份 Markdown 报告并保存到桌面 | 应能写入内容到文件（file_operations create 带 content） |
| B7 | 截一张屏幕图 | 应 call_tool(screenshot)，成功后立即 finish |

## 使用方式

- 手动或脚本依次下发上述任务，检查是否符合预期。
- 可选：在 `data/traces/` 下根据 task_id 查看对应 trace，用于分析步数、延迟与失败点。

## 相关文档

- 测试与验收入口：[测试与验收.md](测试与验收.md)
- 功能测试：[v3.1功能测试指南.md](v3.1功能测试指南.md)
- 文档总览：[README.md](README.md)
