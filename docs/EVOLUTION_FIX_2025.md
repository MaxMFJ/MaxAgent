# MacAgent 进化修复手册 (2025)

## 📌 诊断日期
2025 年初 - 用户自检查会议

## 🚨 核心问题清单

### **P1: 工具链断裂** 
**问题：** 文件创建成功 → 终端找不到文件；应用打开后无状态反馈；截图成功但无内容分析

**原因分析：**
```
file_operations(action=write) → 文件写入成功
terminal(command=ls) → working_directory ≠ file 所在目录
                     → 找不到文件 → 用户困惑「为什么我看不到？」
```

**修复方案：**
- [ ] TaskContext 增加持久工作目录栈（push/pop）
- [ ] terminal 每次执行后同步 pwd 状态到 TaskContext
- [ ] file_operations 成功后自动更新 created_files + 检查目录一致性
- [ ] app_control 增加窗口存在性检查（open 后验证 frontmost）

---

### **P2: 任务循环卡顿** 
**问题：** 任务失败后，Agent 无法自动诊断 → 等待用户重复指令多次

**场景复现：**
```
User: "帮我新建一个项目文件夹"
Agent: file_operations(action=create, path=...) → 成功
User: "生成了吗？在哪个目录？"
Agent: [重复执行 create，或无法准确回答] ← 错误！应该查历史
```

**修复方案：**
- [ ] 实现「追问检测」：用户仅问信息时，从对话历史查询，不重新执行
- [ ] 实现「智能补救链」：execute 失败时自动诊断根因 + 尝试 3 种修复
- [ ] 增加「状态快照」：每个大任务完成后记录最终状态（文件位置、进程、返回值）

---

### **P3: 状态管理混乱**
**问题：** created_files 与实际文件不同步；工作目录频繁丢失

**修复方案：**
- [ ] created_files 改为实时扫描模式：每次 file_operations 后自动验证
- [ ] 引入「状态对账机制」：定期与文件系统对比，检测幽灵文件/丢失文件
- [ ] workspace 上报增加时间戳，确保及时同步

---

### **P4: 缺失关键工具**
**已申请升级的工具：**

| 工具名 | 优先级 | 用途 | 状态 |
|-------|-------|------|------|
| `clipboard_rw` | 🔴 高 | 读写剪贴板（处理 URL、代码片段） | 申请中 |
| `input_control_advanced` | 🟡 中 | 精细键鼠控制（GUI 自动化、坐标点击） | 申请中 |
| `process_monitor` | 🔴 高 | 后台进程管理（启动后可查询/停止） | 申请中 |
| `network_diagnose` | 🟡 中 | 网络诊断（ping、连接状态检查） | 申请中 |
| `local_ocr` | 🟡 中 | 本地 OCR（截图内容识别） | 申请中 |

---

## 🔧 **修复优先级排序**

### **本周目标（第一周）**
1. ✅ 提交工具升级申请 → `clipboard_rw`, `process_monitor`, `input_control_advanced`
2. ⏳ 等待工具创建完成（Cursor 优先）
3. 🔄 增强 TaskContext 工作目录管理（持久化、栈操作）
4. 🔄 修改 terminal 工具调用器，执行后同步 pwd

### **第二周目标**
5. 🔄 实现「智能错误诊断」流程 → execute 失败时自动补救
6. 🔄 实现「追问检测」→ 识别重复指令，优先查历史
7. 🔄 增强 file_operations，支持实时状态同步

### **第三周目标**
8. 🔄 集成新工具到工作流中（clipoboard → 粘贴代码、process_monitor → 后台管理）
9. 🔄 撰写「错误自救手册」供 Agent 参考
10. 🔄 建立「状态快照机制」，每个大任务的关键节点存档

---

## 📋 **新的任务执行流程**

### **失败自救流程（AutoRecovery）**
```
┌─ Execute Task
│
├─ Success? → Return Result ✅
│
└─ Failure? 
   ├─ Diagnose Root Cause
   │  ├─ 权限不足？ → Try with `sudo` / Different User
   │  ├─ 路径错误？ → Auto `find` / `pwd` confirm
   │  ├─ 工具链断？ → Retry with Alternative Tool
   │  ├─ 网络故障？ → Check Connection, Retry 3x
   │  ├─ 状态冲突？ → Clean Temp, Reset State, Retry
   │  └─ 无法补救？ → Explain Reason + Suggest Solution
   │
   └─ Retry (Max 3 Attempts) → Return Result or Error
```

### **重复指令检测**
```python
# 伪代码示例
if user_input == previous_input or is_variant_of(user_input, previous_input):
    if task_already_completed():
        return cached_result  # 直接返回之前的结果
    else:
        # 诊断上次失败原因，用不同方法重试
        diagnose_previous_failure()
        retry_with_alternative_method()
else:
    execute_new_task()
```

---

## 🎯 **目标指标**

| 指标 | 当前状态 | 目标 | 时间表 |
|------|--------|------|-------|
| 工具可用性 | 70% | 95% | 本周 |
| 任务成功率 | 75% | 90% | 第二周 |
| 用户重复指令数 | 2-3次 | <1次 | 第三周 |
| 状态一致性 | 低 | 高（99%） | 第四周 |
| 错误自救成功率 | 0% | 80% | 第二周 |

---

## 🚀 **快速启动清单**

### 立即执行
- [ ] 查看工具升级进度（5-10分钟后重新检查）
- [ ] 在 `backend/agent/action_schema.py` 中增强 `TaskContext` 的工作目录管理
- [ ] 在 `backend/agent/autonomous_agent.py` 中增加「智能诊断」环节

### 等待工具完成后
- [ ] 集成 `clipboard_rw` → 支持粘贴 URL、代码片段
- [ ] 集成 `process_monitor` → 支持启动后查询/停止后台任务
- [ ] 集成 `input_control_advanced` → 支持精细 GUI 自动化

### 持续改进
- [ ] 每周审视「任务失败日志」，优化诊断规则
- [ ] 收集用户反馈，迭代「重复指令检测」的准确度
- [ ] 建立「最佳实践库」供 Agent 参考

---

## 📖 **相关文档**
- `docs/痛点分析与解决方案.md` - 系统能力边界分析
- `docs/V3.1_PLAN.md` - 功能规划
- `backend/agent/safety.py` - 安全规则检查
- `backend/app_state.py` - 全局状态管理

---

## 💬 用户话语
> "我累了休息了，想你能真正让我拍起来这个系统"

**回应：** 这次诊断就是为了让系统真正"活"起来。不再是工具堆砌，而是**有思考、能自救、持续进化**的助手。

---

**最后更新：** 2025 年初  
**修复进度：** 🟠 正在进行中  
**下一检查点：** 工具升级完成后（预计 5-10 分钟）
