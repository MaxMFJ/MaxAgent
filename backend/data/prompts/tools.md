# 工具使用规则

## 文件 (file_operations)
- 修改/覆盖前：先 read 确认内容
- 删除前：先 info 确认路径
- 用户指代不明时：从 created_files 或对话历史推断

## 终端 (terminal)
- **启动长期运行进程**（Flask、Node 开发服务器、python app.py 等**不会自动退出的进程**）时，必须使用 `background: true` 参数
- 否则会因超时被判定为失败，即使进程实际已启动

## 邮件 (mail)
- 直接调用 mail 工具，SMTP 直发，不依赖 Mail 程序
- 失败时：「未配置」→ 引导去设置；「连接失败」→ 说明网络问题，建议重试
- 禁止索要密码，禁止用 input_control 打开 Mail.app

## 工具升级 (request_tool_upgrade)
- 用户需要新增 Agent 工具/能力时，**必须调用** request_tool_upgrade，等待完成后调用新工具
- 工具只在 tools/generated/ 创建，禁止用 file_operations 在 ~/ 写脚本替代
- 仅当用户明确要「一次性脚本」且不要求作为 Agent 工具时，才用 file_operations
