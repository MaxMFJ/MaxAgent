# TaskContext 增强补丁
# 添加工作目录栈管理，实现持久化 pwd 状态跟踪

"""
使用说明：
将以下方法添加到 action_schema.py 中的 TaskContext 类

优势：
1. 持久化工作目录状态 → terminal 和 file_operations 状态同步
2. 支持 push/pop 栈操作 → 复杂目录导航场景
3. 自动检测工作目录变化 → 如果 pwd 与 TaskContext 不同，自动更新
4. 方便回溯 → 调试时知道每个步骤的工作目录是什么
"""

# ============ 在 TaskContext.__init__ 中添加以下字段 ============

# 工作目录管理
current_workdir: str = field(default="~")  # 当前工作目录
workdir_stack: List[str] = field(default_factory=list)  # 工作目录栈（用于 push/pop）
workdir_changes: List[Dict[str, str]] = field(default_factory=list)  # 记录目录变化历史

# ============ 在 TaskContext 类中添加以下方法 ============

def push_workdir(self, new_dir: str):
    """
    推入新工作目录到栈中
    用于需要临时改变目录的操作
    """
    self.workdir_stack.append(self.current_workdir)
    self.set_workdir(new_dir)
    logger.info(f"[WorkDir] Push: {self.current_workdir} (stack depth: {len(self.workdir_stack)})")

def pop_workdir(self):
    """
    从栈中弹出上一个工作目录
    """
    if self.workdir_stack:
        prev_dir = self.workdir_stack.pop()
        self.set_workdir(prev_dir)
        logger.info(f"[WorkDir] Pop: {self.current_workdir} (stack depth: {len(self.workdir_stack)})")
        return prev_dir
    else:
        logger.warning("[WorkDir] Stack is empty, cannot pop")
        return None

def set_workdir(self, new_dir: str):
    """
    设置当前工作目录，并记录变化历史
    """
    if new_dir != self.current_workdir:
        old_dir = self.current_workdir
        self.current_workdir = new_dir
        self.workdir_changes.append({
            "from": old_dir,
            "to": new_dir,
            "timestamp": datetime.now().isoformat(),
            "iteration": self.current_iteration
        })
        logger.info(f"[WorkDir] Changed: {old_dir} → {new_dir}")

def get_workdir(self) -> str:
    """获取当前工作目录"""
    return self.current_workdir

def get_workdir_history(self, count: int = 5) -> List[Dict[str, str]]:
    """获取最近的工作目录变化历史"""
    return self.workdir_changes[-count:]

# ============ 修改后的 terminal 调用流程 ============

# 在 autonomous_agent.py 的 execute_terminal 方法中：

async def execute_terminal(self, params: Dict[str, Any], context: TaskContext) -> ActionResult:
    """
    执行 terminal 命令
    关键改动：执行后自动同步 pwd 到 TaskContext
    """
    # ... 执行原有逻辑 ...
    
    # 执行命令
    result = await self.terminal_tool.execute(
        command=params.get("command"),
        working_directory=context.get_workdir()  # ← 使用 TaskContext 的工作目录
    )
    
    # 新增：执行后自动检查并更新 pwd
    if result["exit_code"] == 0:
        pwd_cmd = await self.terminal_tool.execute(
            command="pwd",
            working_directory=context.get_workdir()
        )
        if pwd_cmd["exit_code"] == 0:
            actual_pwd = pwd_cmd["stdout"].strip()
            context.set_workdir(actual_pwd)  # ← 同步到 TaskContext
    
    return result

# ============ 修改后的 file_operations 调用流程 ============

async def execute_file_operation(self, params: Dict[str, Any], context: TaskContext) -> ActionResult:
    """
    执行文件操作
    关键改动：确保文件操作与工作目录同步
    """
    action = params.get("action")
    path = params.get("path")
    
    # 如果路径是相对路径，转换为绝对路径（基于 TaskContext.current_workdir）
    if not path.startswith("/"):
        path = f"{context.get_workdir()}/{path}"
    
    params["path"] = path
    
    # 执行原有逻辑
    result = await self.file_tool.execute(action=action, **params)
    
    # 如果是 create 操作成功，记录到 created_files
    if action == "create" and result["success"]:
        # ... 更新 created_files ...
        logger.info(f"[FileOp] Created: {path} (workdir: {context.get_workdir()})")
    
    return result

# ============ 诊断方法 ============

def diagnose_workdir_mismatch(self, actual_pwd: str) -> bool:
    """
    检测工作目录不一致
    返回是否需要修正
    """
    if self.current_workdir != actual_pwd:
        logger.warning(
            f"[WorkDir] Mismatch detected!\n"
            f"  Expected: {self.current_workdir}\n"
            f"  Actual:   {actual_pwd}\n"
            f"  Auto-correcting..."
        )
        self.set_workdir(actual_pwd)
        return True
    return False

def get_workdir_debug_info(self) -> Dict[str, Any]:
    """
    获取工作目录调试信息
    用于排查问题
    """
    return {
        "current_workdir": self.current_workdir,
        "stack_depth": len(self.workdir_stack),
        "stack_contents": self.workdir_stack,
        "changes_count": len(self.workdir_changes),
        "recent_changes": self.get_workdir_history(3)
    }
