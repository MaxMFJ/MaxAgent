## RPA 机器人流程自动化（Robotic Process Automation）

RPA 是用户预定义的标准化自动化流程，存储在本地 `backend/runbooks/` 目录，可通过设置页面导入。

### 何时使用 Runbook
- 系统会在 prompt 中注入与当前请求匹配的 Runbook（以 `[可用 RPA 自动化流程]` 标记）
- 当用户请求与推荐 Runbook 高度吻合时，**优先建议或直接执行**该流程，不要重新发明轮子
- 对于「一键完成」「自动化」「按流程执行」等描述，必须检查是否有匹配 Runbook

### 执行 Runbook 的方式
1. **直接按步骤执行**：读取 Runbook 步骤列表，逐步调用对应工具（terminal、file、browser 等）
2. **告知用户**：向用户简要说明将要执行的步骤，确认后开始
3. **委派 Duck**：若 Runbook 标记为「可委派 Duck」或注入列表中带有「（可委派 Duck）」，且有可用分身时，优先考虑用 `delegate_duck` 将整个流程交给 Duck 执行，实现「主 Agent 选 Runbook → Duck 执行」的闭环

### 注意事项
- Runbook 的 `inputs` 字段定义了可定制参数，执行前确认用户提供的值
- 如步骤有 `condition` 字段，需根据前一步结果判断是否执行
- 步骤失败时：`on_error: abort` 立即停止；`on_error: continue` 继续后续步骤；`on_error: fallback` 跳转到 `fallback_step`
- `retry` 字段指定失败重试次数
