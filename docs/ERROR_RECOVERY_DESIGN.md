# 智能错误诊断与自救流程 (Intelligent Error Recovery)

## 核心设计原理

当 Agent 执行任务失败时，不是立即返回错误，而是启动「**智能诊断-补救-重试**」循环，最多尝试 3 次不同的方案。

```
Execute Task
    ↓
Success? ──YES──> Return Result ✅
    ↓ NO
Analyze Error Type
    ↓
Try Recovery Plan 1
    ↓
Success? ──YES──> Return Result ✅
    ↓ NO
Try Recovery Plan 2
    ↓
Success? ──YES──> Return Result ✅
    ↓ NO
Try Recovery Plan 3
    ↓
Success? ──YES──> Return Result ✅
    ↓ NO
Return Error Explanation + Suggested Fixes ❌
```

---

## 错误类型分类与诊断

### **1. Permission Denied (权限错误)**

```
Error Pattern: "Permission denied", "access denied", "权限不足"

Root Causes:
├─ 目标文件/目录权限不足
├─ 当前用户无权限执行命令
├─ 需要 root/sudo 权限
└─ 文件被锁定或在使用中

Recovery Plans (优先级顺序):
├─ Plan A: 用 `sudo` 重试
│   Command: sudo <original_command>
│   Condition: 检查是否需要输入密码（若需要则跳过）
│
├─ Plan B: 改用当前用户有权限的目录
│   检查 ~/Documents, ~/Desktop 等
│
├─ Plan C: 使用 `chmod` 改变权限
│   前提：必须与用户确认，否则有安全风险
│
└─ Plan D: 提示用户需要 IT 支持或管理员权限
```

**实现代码框架：**
```python
async def handle_permission_error(self, error: str, action: AgentAction, context: TaskContext) -> ActionResult:
    """处理权限错误"""
    
    # Plan A: 尝试 sudo
    if "sudo" not in action.params.get("command", ""):
        recovery_cmd = f"sudo {action.params['command']}"
        result = await self.terminal_tool.execute(recovery_cmd)
        if result["exit_code"] == 0:
            logger.info("[Recovery] Plan A succeeded (sudo)")
            return result
        else:
            logger.info("[Recovery] Plan A failed (sudo requires password or failed)")
    
    # Plan B: 改用其他目录
    path = action.params.get("path", "")
    alt_dirs = ["~/Documents", "~/Desktop", f"/tmp/macagent_{uuid4()[:8]}"]
    for alt_dir in alt_dirs:
        alt_path = path.replace(os.path.dirname(path), alt_dir)
        action.params["path"] = alt_path
        result = await execute_action(action, context)
        if result["success"]:
            logger.info(f"[Recovery] Plan B succeeded (alt dir: {alt_dir})")
            return result
    
    # Plan C: 提示用户
    return ActionResult(
        success=False,
        output=f"Permission denied. Please check file permissions or run with sudo.",
        error_type="permission_error"
    )
```

---

### **2. File/Path Not Found (文件不存在)**

```
Error Pattern: "No such file or directory", "文件不存在", "Cannot find path"

Root Causes:
├─ 文件实际上不存在
├─ 路径拼写错误
├─ 相对路径与当前工作目录不匹配
├─ 文件已被删除
└─ 大小写错误（macOS 默认不区分大小写，但 Terminal 区分）

Recovery Plans:
├─ Plan A: 用 `find` 命令搜索该文件
│   Command: find ~ -name "<filename>" -type f 2>/dev/null | head -5
│
├─ Plan B: 验证当前工作目录（pwd）
│   检查 TaskContext.current_workdir 是否与实际一致
│   如果不一致，自动纠正
│
├─ Plan C: 改用绝对路径而不是相对路径
│   从 "~/folder/file" 改为 "/Users/username/folder/file"
│
├─ Plan D: 检查路径大小写
│   macOS 文件系统不区分大小写，但命令行工具可能敏感
│
└─ Plan E: 提示用户文件可能不存在，建议创建或选择其他文件
```

**实现代码框架：**
```python
async def handle_file_not_found(self, error: str, action: AgentAction, context: TaskContext) -> ActionResult:
    """处理文件不存在错误"""
    
    path = action.params.get("path", "")
    filename = os.path.basename(path)
    
    # Plan A: 搜索文件
    find_cmd = f'find ~ -name "{filename}" -type f 2>/dev/null | head -5'
    find_result = await self.terminal_tool.execute(find_cmd)
    if find_result["exit_code"] == 0 and find_result["stdout"].strip():
        found_files = find_result["stdout"].strip().split("\n")
        logger.info(f"[Recovery] Plan A found files: {found_files}")
        # 让用户选择，或自动选择第一个
        action.params["path"] = found_files[0]
        return await execute_action(action, context)
    
    # Plan B: 检查工作目录是否与 TaskContext 一致
    pwd_result = await self.terminal_tool.execute("pwd")
    actual_pwd = pwd_result["stdout"].strip()
    context.diagnose_workdir_mismatch(actual_pwd)
    
    # Plan C: 改用绝对路径
    if path.startswith("~/"):
        abs_path = os.path.expanduser(path)
    else:
        abs_path = os.path.join(context.current_workdir, path)
    
    action.params["path"] = abs_path
    result = await execute_action(action, context)
    if result["success"]:
        logger.info("[Recovery] Plan C succeeded (absolute path)")
        return result
    
    # Plan D: 提示用户
    return ActionResult(
        success=False,
        output=f"File not found: {path}. Use `find ~` to search for it.",
        error_type="file_not_found"
    )
```

---

### **3. Command Not Found (命令找不到)**

```
Error Pattern: "command not found", "未找到命令", "No such file or directory"

Root Causes:
├─ 命令未安装
├─ 命令路径不在 $PATH 中
├─ 拼写错误
├─ shell 环境不对（bash vs zsh）
└─ 依赖库未加载

Recovery Plans:
├─ Plan A: 检查命令是否安装
│   Command: which <command> 或 command -v <command>
│   若返回空，说明未安装
│
├─ Plan B: 建议安装（brew、pip、npm 等）
│   根据命令类型推荐安装方式
│
├─ Plan C: 用完整路径调用
│   如果知道命令的完整路径
│
├─ Plan D: 尝试替代命令
│   如 python vs python3, ls vs /bin/ls
│
└─ Plan E: 检查 shell 环境
    某些命令仅在特定 shell 中可用
```

**实现代码框架：**
```python
async def handle_command_not_found(self, error: str, action: AgentAction, context: TaskContext) -> ActionResult:
    """处理命令不存在错误"""
    
    cmd = action.params.get("command", "")
    cmd_name = cmd.split()[0]  # 获取命令名
    
    # Plan A: 检查是否安装
    check_cmd = f"which {cmd_name} || command -v {cmd_name}"
    check_result = await self.terminal_tool.execute(check_cmd)
    
    if check_result["exit_code"] != 0:
        logger.info(f"[Recovery] Command not installed: {cmd_name}")
        
        # Plan B: 推荐安装
        install_suggestions = {
            "python3": "brew install python3",
            "node": "brew install node",
            "git": "brew install git",
            "docker": "brew install docker",
            # ... 更多映射
        }
        
        if cmd_name in install_suggestions:
            suggestion = install_suggestions[cmd_name]
            return ActionResult(
                success=False,
                output=f"Command '{cmd_name}' not found. Try: {suggestion}",
                error_type="command_not_found"
            )
    
    # Plan C: 用完整路径重试
    full_path = check_result["stdout"].strip()
    if full_path:
        new_cmd = cmd.replace(cmd_name, full_path, 1)
        action.params["command"] = new_cmd
        return await execute_action(action, context)
    
    # Plan D: 尝试替代命令
    alternatives = {
        "python": "python3",
        "pip": "pip3",
        "node": "nodejs"
    }
    
    if cmd_name in alternatives:
        new_cmd = cmd.replace(cmd_name, alternatives[cmd_name], 1)
        action.params["command"] = new_cmd
        result = await execute_action(action, context)
        if result["success"]:
            logger.info(f"[Recovery] Plan D succeeded (alternative: {alternatives[cmd_name]})")
            return result
```

---

### **4. Network Error (网络错误)**

```
Error Pattern: "Connection refused", "Network is unreachable", "Timeout", "连接超时"

Root Causes:
├─ 网络连接断开
├─ 目标服务器不可达
├─ 防火墙阻止
├─ DNS 解析失败
└─ 超时

Recovery Plans:
├─ Plan A: 检查网络连接
│   Command: ping 8.8.8.8 或 networksetup -getairportnetwork en0
│
├─ Plan B: 重试（指数退避）
│   第一次等待 2s，第二次 4s，第三次 8s
│
├─ Plan C: 改用备用 DNS
│   如果是 DNS 问题，改用 8.8.8.8 或 1.1.1.1
│
└─ Plan D: 提示用户检查网络
```

**实现代码框架：**
```python
async def handle_network_error(self, error: str, action: AgentAction, context: TaskContext) -> ActionResult:
    """处理网络错误"""
    
    # Plan A: 检查网络连接
    ping_result = await self.terminal_tool.execute("ping -c 1 8.8.8.8")
    if ping_result["exit_code"] != 0:
        logger.info("[Recovery] Network is down")
        return ActionResult(
            success=False,
            output="No network connection detected. Please check your internet.",
            error_type="network_error"
        )
    
    # Plan B: 重试（指数退避）
    import time
    for attempt in range(1, 4):
        wait_time = 2 ** attempt  # 2s, 4s, 8s
        logger.info(f"[Recovery] Retry attempt {attempt}, waiting {wait_time}s...")
        time.sleep(wait_time)
        
        result = await execute_action(action, context)
        if result["success"]:
            logger.info("[Recovery] Retry succeeded")
            return result
    
    # Plan C: 提示用户
    return ActionResult(
        success=False,
        output=f"Network error: {error}. Retried 3 times but still failed.",
        error_type="network_error"
    )
```

---

### **5. Syntax Error (语法错误)**

```
Error Pattern: "SyntaxError", "unexpected token", "语法错误"

Root Causes:
├─ 脚本语言语法错误
├─ Shell 命令语法错误
├─ 引号不匹配
└─ 缩进错误

Recovery Plans:
├─ Plan A: 显示错误行，让 LLM 修正
├─ Plan B: 尝试自动修复（引号、缩进等）
└─ Plan C: 提示用户检查代码
```

---

### **6. State Conflict (状态冲突)**

```
Error Pattern: "File already exists", "Port already in use", "资源已被占用"

Root Causes:
├─ 文件/目录已存在
├─ 端口已被占用
├─ 进程已在运行
└─ 资源锁定

Recovery Plans:
├─ Plan A: 删除/覆盖旧资源
├─ Plan B: 改用不同的端口/路径
├─ Plan C: 杀死占用的进程
└─ Plan D: 清理临时文件
```

**实现代码框架：**
```python
async def handle_state_conflict(self, error: str, action: AgentAction, context: TaskContext) -> ActionResult:
    """处理状态冲突"""
    
    # Plan A: 检查文件是否已存在
    if "File exists" in error or "already exists" in error:
        path = action.params.get("path")
        file_info = await self.file_tool.execute("info", path=path)
        if file_info["success"]:
            logger.info(f"[Recovery] File already exists: {path}")
            
            # 询问用户是否覆盖（在实际实现中应该由用户确认）
            # 这里假设无需覆盖
            return ActionResult(
                success=False,
                output=f"File already exists: {path}. Use action=delete to remove it first.",
                error_type="state_conflict"
            )
    
    # Plan B: 检查端口是否被占用
    if "port" in error.lower() or "already in use" in error:
        # 尝试改用不同的端口
        port = action.params.get("port", 8000)
        alt_port = port + 1000
        action.params["port"] = alt_port
        logger.info(f"[Recovery] Port {port} in use, trying {alt_port}")
        return await execute_action(action, context)
    
    # Plan C: 清理临时文件/进程
    cleanup_result = await cleanup_resources(context)
    if cleanup_result["success"]:
        logger.info("[Recovery] Resources cleaned up, retrying...")
        return await execute_action(action, context)
```

---

## 集成到 autonomous_agent.py

在主循环中添加「智能诊断」阶段：

```python
async def execute_action_with_recovery(self, action: AgentAction, context: TaskContext) -> ActionResult:
    """
    执行 action，失败时自动进行诊断和恢复
    """
    
    # 第一次尝试
    result = await self.execute_action(action, context)
    
    if result["success"]:
        return result
    
    # 分析错误类型
    error_type = self.diagnose_error(result["error"])
    logger.info(f"[Diagnosis] Error type: {error_type}")
    logger.info(f"[Diagnosis] Error message: {result['error']}")
    
    # 根据错误类型调用对应的处理器
    handlers = {
        "permission_error": self.handle_permission_error,
        "file_not_found": self.handle_file_not_found,
        "command_not_found": self.handle_command_not_found,
        "network_error": self.handle_network_error,
        "syntax_error": self.handle_syntax_error,
        "state_conflict": self.handle_state_conflict,
    }
    
    handler = handlers.get(error_type)
    if handler:
        recovery_result = await handler(result["error"], action, context)
        if recovery_result["success"]:
            return recovery_result
    
    # 所有恢复都失败，返回诊断信息
    return ActionResult(
        success=False,
        output=result["error"],
        error_type=error_type,
        suggested_fixes=self.get_suggested_fixes(error_type)
    )

def diagnose_error(self, error_message: str) -> str:
    """
    分析错误信息，判断错误类型
    """
    error_lower = error_message.lower()
    
    if "permission" in error_lower or "denied" in error_lower or "access" in error_lower:
        return "permission_error"
    elif "no such file" in error_lower or "not found" in error_lower:
        if "command" in error_lower:
            return "command_not_found"
        else:
            return "file_not_found"
    elif "connection" in error_lower or "timeout" in error_lower or "network" in error_lower:
        return "network_error"
    elif "syntax" in error_lower or "unexpected" in error_lower:
        return "syntax_error"
    elif "exists" in error_lower or "already in use" in error_lower:
        return "state_conflict"
    else:
        return "unknown_error"

def get_suggested_fixes(self, error_type: str) -> List[str]:
    """
    为错误类型提供建议修复方案
    """
    suggestions = {
        "permission_error": [
            "尝试用 sudo 运行命令",
            "检查文件权限 (ls -la)",
            "改用其他目录试试",
        ],
        "file_not_found": [
            "检查文件是否存在",
            "用 find 命令搜索文件",
            "检查当前工作目录 (pwd)",
        ],
        "command_not_found": [
            "检查命令是否安装 (which cmd)",
            "用 brew 或其他包管理器安装",
            "尝试使用完整路径",
        ],
        "network_error": [
            "检查网络连接",
            "稍后重试",
            "检查防火墙设置",
        ],
        "syntax_error": [
            "检查代码语法",
            "查看错误行号",
            "验证引号和括号",
        ],
        "state_conflict": [
            "删除已存在的文件",
            "改用不同的端口/路径",
            "杀死占用的进程",
        ],
    }
    
    return suggestions.get(error_type, ["请检查错误信息并手动处理"])
```

---

## 优势总结

✅ **自动诊断** - 不需要用户重复指令，Agent 自动判断错误类型  
✅ **多层级恢复** - 每个错误有 3-5 种恢复方案，按优先级尝试  
✅ **透明化** - 每一步都记录日志，用户可以看到 Agent 的诊断过程  
✅ **减少循环** - 大大降低用户需要重复指令的次数  
✅ **持续学习** - 可以定期审视失败案例，优化诊断规则  

---

## 下一步

1. 在 `autonomous_agent.py` 中实现上述各个 `handle_*` 方法
2. 在主执行循环中集成 `execute_action_with_recovery`
3. 添加日志记录和可视化
4. 测试各种错误场景
5. 定期审视失败日志，优化诊断规则
