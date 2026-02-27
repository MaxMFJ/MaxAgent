# 约束与反模式

## 禁止行为
- 禁止在未确认工具执行结果前谎称成功
- 禁止在用户仅追问信息时重新执行创建/写入/运行
- 禁止用 input_control 打开 Mail.app 发邮件（必须用 mail 工具）
- 禁止用 file_operations 在 ~/ 创建替代 Agent 工具的脚本（新工具用 request_tool_upgrade）

## 安全
- 危险命令（rm -rf /、chmod 777 等）会被 terminal 拒绝
- 执行前确认用户意图，批量删除等操作先确认
