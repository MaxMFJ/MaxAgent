# 追问检测与智能响应机制

## 核心问题

用户在执行任务后常会追问：
- "生成了吗？"
- "文件在哪个目录？"
- "项目做好了吗？"
- "我去看一下"
- "结果怎么样？"

**当前错误行为：** Agent 重新执行创建/写入/运行命令  
**正确行为：** 从对话历史推断答案，直接回答或提供访问路径

---

## 设计原理

```
User Input
    ↓
Check if is_query_about_previous_task()?
    ├─ YES → Search conversation history
    │        └─ Return cached result from previous action
    │
    └─ NO → Execute new task
```

### 追问类型分类

| 类型 | 特征 | 示例 | 响应方式 |
|------|------|------|--------|
| **确认型** | "吗？" "了吗？" | "生成了吗？" | 查历史，返回结果 |
| **位置型** | "在哪？" "哪个目录？" | "文件在哪个目录？" | 返回 path |
| **状态型** | "怎么样？" "成功？" | "结果怎么样？" | 返回 status + output |
| **查看型** | "看一下" "打开" "显示" | "我去看一下" "帮我打开" | 截图或打开应用 |
| **重复型** | 完全相同的命令 | 同上一条指令 | 检查是否已完成 |

---

## 实现详解

### 1. 追问检测函数

```python
from typing import Tuple, Optional, Dict, Any
from datetime import datetime, timedelta

def is_follow_up_query(
    current_input: str,
    conversation_history: List[Dict[str, str]],
    recent_actions: List[ActionLog]
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    检测用户输入是否为追问
    
    Returns:
        (是否追问, 追问类型, 相关的上一个action结果)
    """
    
    if not conversation_history or len(conversation_history) < 2:
        return False, None, None
    
    # 获取上一个用户输入和 Agent 回复
    last_user_msg = conversation_history[-2].get("content", "").strip()
    last_agent_msg = conversation_history[-2].get("content", "").strip()
    
    # 获取最近的 action
    last_action = recent_actions[-1] if recent_actions else None
    
    # ============ 特征1: 确认型追问 ============
    if is_confirmation_query(current_input):
        # "了吗？", "生成了吗？", "成功吗？", "完成了吗？"
        if last_action and last_action.result.success:
            return True, "confirmation", {
                "action": last_action.action.action_type,
                "result": last_action.result
            }
    
    # ============ 特征2: 位置型追问 ============
    if is_location_query(current_input):
        # "在哪个目录？", "文件在哪？", "项目在哪里？"
        if last_action and last_action.action.action_type in ["create", "write_file"]:
            return True, "location", {
                "path": last_action.result.output.get("path"),
                "created_files": extract_created_files(last_agent_msg)
            }
    
    # ============ 特征3: 状态型追问 ============
    if is_status_query(current_input):
        # "结果怎么样？", "有什么问题吗？", "出错了吗？"
        if last_action:
            return True, "status", {
                "action": last_action.action.action_type,
                "success": last_action.result.success,
                "output": last_action.result.output,
                "error": last_action.result.error
            }
    
    # ============ 特征4: 重复型追问 ============
    if current_input.strip() == last_user_msg.strip():
        # 完全相同的指令
        if last_action and last_action.result.success:
            # 上次成功，则直接返回结果
            return True, "duplicate", {
                "already_done": True,
                "result": last_action.result
            }
        elif last_action and not last_action.result.success:
            # 上次失败，则应该用不同方法重试（不是重复）
            return False, None, None
    
    # ============ 特征5: 查看型追问 ============
    if is_view_query(current_input):
        # "打开看看", "我去看一下", "显示一下", "给我截个图"
        # 这类不是追问，而是新的操作请求
        return False, None, None
    
    return False, None, None


def is_confirmation_query(text: str) -> bool:
    """检测确认型追问"""
    patterns = [
        r"了吗",
        r"生成了吗",
        r"成功了吗",
        r"完成了吗",
        r"成功吗",
        r"好了吗",
        r"搞定了吗",
        r"done\?",
        r"finished\?",
        r"success\?",
    ]
    
    text_lower = text.lower()
    return any(re.search(pattern, text_lower) for pattern in patterns)


def is_location_query(text: str) -> bool:
    """检测位置型追问"""
    patterns = [
        r"在哪个?目录",
        r"在哪里",
        r"哪个文件夹",
        r"路径是什么",
        r"file location",
        r"where.*file",
        r"which.*folder",
    ]
    
    text_lower = text.lower()
    return any(re.search(pattern, text_lower) for pattern in patterns)


def is_status_query(text: str) -> bool:
    """检测状态型追问"""
    patterns = [
        r"怎么样",
        r"结果",
        r"有问题吗",
        r"报错吗",
        r"出错了吗",
        r"成功了吗",
        r"what.*result",
        r"how.*status",
        r"any.*error",
    ]
    
    text_lower = text.lower()
    return any(re.search(pattern, text_lower) for pattern in patterns)


def is_view_query(text: str) -> bool:
    """检测查看型追问（不是追问，而是新指令）"""
    patterns = [
        r"打开",
        r"看一下",
        r"显示",
        r"截图",
        r"screenshot",
        r"open",
        r"show",
    ]
    
    text_lower = text.lower()
    return any(re.search(pattern, text_lower) for pattern in patterns)


def extract_created_files(agent_message: str) -> List[str]:
    """
    从 Agent 回复中提取创建的文件列表
    
    示例回复：
    "已创建文件: /Users/xxx/file1.txt, /Users/xxx/file2.txt"
    "新建项目目录: ~/projects/myapp"
    """
    files = []
    
    # 模式1: 路径列表 (以 / 开头)
    paths = re.findall(r"/[^\s,]+", agent_message)
    files.extend(paths)
    
    # 模式2: ~ 开头的路径
    home_paths = re.findall(r"~/[^\s,]+", agent_message)
    files.extend(home_paths)
    
    # 模式3: 文件名称（在括号中）
    filenames = re.findall(r"\`([^`]+)\`", agent_message)
    files.extend(filenames)
    
    return list(set(files))  # 去重


def extract_port_info(agent_message: str) -> Optional[str]:
    """从回复中提取端口号"""
    match = re.search(r"port\s*(?::|=|is)?\s*(\d+)", agent_message, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def extract_url(agent_message: str) -> Optional[str]:
    """从回复中提取 URL"""
    match = re.search(r"https?://[^\s]+", agent_message)
    if match:
        return match.group(0)
    return None
```

### 2. 改进的 Agent 响应器

```python
async def handle_user_input(self, user_input: str, context: TaskContext) -> str:
    """
    处理用户输入，检测追问并智能响应
    """
    
    # 检测追问
    is_followup, query_type, related_data = is_follow_up_query(
        user_input,
        context.conversation_history,
        context.recent_actions
    )
    
    if is_followup:
        logger.info(f"[FollowUp] Detected {query_type} query")
        return handle_follow_up_query(query_type, related_data, context)
    
    # 不是追问，执行新任务
    return await self.execute_task(user_input, context)


def handle_follow_up_query(
    query_type: str,
    related_data: Dict[str, Any],
    context: TaskContext
) -> str:
    """
    根据追问类型返回答案，不重新执行
    """
    
    if query_type == "confirmation":
        # "生成了吗？" → 直接确认成功
        action_type = related_data["action"]
        return f"✅ 已完成！{action_type} 执行成功。"
    
    elif query_type == "location":
        # "文件在哪个目录？" → 返回路径
        path = related_data.get("path")
        created_files = related_data.get("created_files", [])
        
        response = "📍 文件位置：\n"
        if path:
            response += f"主文件: `{path}`\n"
        if created_files:
            response += "创建的文件：\n"
            for f in created_files:
                response += f"  - `{f}`\n"
        
        # 提供快速访问：打开文件夹
        response += f"\n💡 需要我打开这个文件夹吗？"
        return response
    
    elif query_type == "status":
        # "结果怎么样？" → 返回执行状态
        success = related_data.get("success", False)
        output = related_data.get("output", "")
        error = related_data.get("error", "")
        
        if success:
            return f"✅ 执行成功！\n结果：{output}"
        else:
            return f"❌ 执行失败！\n错误：{error}\n\n需要我重新尝试吗？"
    
    elif query_type == "duplicate":
        # 完全重复的指令，上次成功
        already_done = related_data.get("already_done", False)
        result = related_data.get("result")
        
        return f"✅ 刚才已经完成过了！\n结果：{result.output}\n\n需要做其他事吗？"


def get_cached_result(self, last_action: ActionLog) -> Dict[str, Any]:
    """
    从上一个 action 的结果中提取关键信息，用于追问回答
    """
    
    result = last_action.result
    action = last_action.action
    
    cached = {
        "action_type": action.action_type,
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "created_at": last_action.timestamp,
        "executed_at": action.created_at,
    }
    
    # 如果是文件操作，提取路径
    if action.action_type in ["create", "write_file", "move_file"]:
        cached["path"] = action.params.get("path")
    
    # 如果是终端操作，提取命令
    if action.action_type == "run_shell":
        cached["command"] = action.params.get("command")
    
    # 如果是网络操作，提取 URL/端口
    if action.action_type == "call_tool":
        tool_name = action.params.get("tool_name")
        if tool_name in ["http_request", "curl"]:
            cached["url"] = extract_url(result.output)
        if "port" in action.params:
            cached["port"] = action.params["port"]
    
    return cached
```

### 3. 对话历史管理

```python
@dataclass
class ConversationMessage:
    """单条对话记录"""
    role: str  # "user" 或 "assistant"
    content: str
    timestamp: datetime
    related_action_id: Optional[str] = None  # 关联的 action ID
    
    def is_user_message(self) -> bool:
        return self.role == "user"
    
    def is_assistant_message(self) -> bool:
        return self.role == "assistant"


@dataclass
class ConversationHistory:
    """对话历史管理"""
    messages: List[ConversationMessage] = field(default_factory=list)
    
    def add_message(self, role: str, content: str, action_id: Optional[str] = None):
        """添加新的对话记录"""
        self.messages.append(ConversationMessage(
            role=role,
            content=content,
            timestamp=datetime.now(),
            related_action_id=action_id
        ))
    
    def get_last_user_message(self) -> Optional[str]:
        """获取上一条用户消息"""
        for msg in reversed(self.messages):
            if msg.is_user_message():
                return msg.content
        return None
    
    def get_last_assistant_message(self) -> Optional[str]:
        """获取上一条 Agent 回复"""
        for msg in reversed(self.messages):
            if msg.is_assistant_message():
                return msg.content
        return None
    
    def get_conversation_window(self, count: int = 5) -> List[ConversationMessage]:
        """获取最近 N 条对话"""
        return self.messages[-count:]
    
    def find_messages_about(self, keyword: str) -> List[ConversationMessage]:
        """搜索包含特定关键字的对话"""
        return [msg for msg in self.messages if keyword.lower() in msg.content.lower()]
    
    def get_context_for_task(self, task_description: str) -> str:
        """
        为新任务生成上下文
        包含最近相关的对话和操作
        """
        relevant_msgs = self.find_messages_about(task_description)
        if not relevant_msgs:
            relevant_msgs = self.get_conversation_window(3)
        
        context = "最近的对话记录：\n"
        for msg in relevant_msgs[-3:]:
            role_name = "用户" if msg.is_user_message() else "助手"
            context += f"{role_name}: {msg.content}\n"
        
        return context
```

---

## 集成到 TaskContext

```python
@dataclass
class TaskContext:
    # ... 现有字段 ...
    
    # 新增字段
    conversation_history: ConversationHistory = field(default_factory=ConversationHistory)
    recent_actions: List[ActionLog] = field(default_factory=list)  # 最近 10 个 action
    
    def add_to_conversation(self, role: str, content: str, action_id: Optional[str] = None):
        """添加对话记录"""
        self.conversation_history.add_message(role, content, action_id)
    
    def record_action(self, action: ActionLog):
        """记录 action，保留最近 10 个"""
        self.recent_actions.append(action)
        if len(self.recent_actions) > 10:
            self.recent_actions.pop(0)
```

---

## 使用示例

### 场景 1: 用户追问"生成了吗？"

```
User: "帮我新建一个 Python 项目"
Agent: 创建目录、写入文件、初始化 Git...
       回复: "✅ 已创建 Python 项目在 ~/projects/myapp"

User: "生成了吗？"  ← 追问
Agent: [检测到 confirmation 追问]
       [不重新执行]
       回复: "✅ 已完成！create 执行成功。"
```

### 场景 2: 用户追问"文件在哪个目录？"

```
User: "新建一个 config.yaml 文件"
Agent: 写入文件到 ~/config.yaml
       回复: "已创建文件 config.yaml"

User: "文件在哪个目录？"  ← 追问
Agent: [检测到 location 追问]
       [查历史，提取路径]
       回复: "📍 文件位置：`~/config.yaml`
              💡 需要我打开这个文件吗？"
```

### 场景 3: 用户完全重复同一个指令

```
User: "启动 Flask 服务器"
Agent: 执行命令，启动服务
       回复: "✅ Flask 服务运行在 http://localhost:5000"

User: "启动 Flask 服务器"  ← 重复指令
Agent: [检测到 duplicate]
       [发现上次已成功完成]
       [不重新执行]
       回复: "✅ 刚才已经启动过了！
              服务运行在 http://localhost:5000
              需要停止吗？"
```

---

## 优势总结

✅ **减少重复执行** - 避免不必要的重复操作  
✅ **快速应答** - 从历史直接提取答案，毫秒级响应  
✅ **用户体验** - 用户感觉 Agent 真的在"思考"而不是机械执行  
✅ **节省资源** - 减少不必要的工具调用，节省 tokens 和时间  
✅ **可追溯** - 完整的对话和操作历史，便于调试  

---

## 下一步

1. 在 `TaskContext` 中增加 `ConversationHistory` 字段
2. 在主循环中每次接收用户输入时调用 `is_follow_up_query`
3. 实现追问类型的准确分类（可用 ML 或启发式规则）
4. 测试各种追问场景
5. 收集真实用户数据，优化检测规则
