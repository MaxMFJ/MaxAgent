"""
Local Model Tool Parser
Parses tool calls from local model text output (no native function calling)
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


# 精简版系统提示（减少 token 消耗，适合小型本地模型）
LOCAL_MODEL_SYSTEM_PROMPT_COMPACT = """你是 MacAgent，macOS 智能助手。

## 工具调用格式
{"tool": "工具名", "args": {参数}}

## 常用工具
1. app_control: {"tool": "app_control", "args": {"action": "open", "app_name": "应用名"}}
2. terminal: {"tool": "terminal", "args": {"command": "命令"}}
3. file_operations: {"tool": "file_operations", "args": {"action": "read|write|list", "path": "路径"}}
4. web_search: {"tool": "web_search", "args": {"action": "search|get_weather|translate", "query": "内容"}}
5. screenshot: {"tool": "screenshot", "args": {"action": "capture", "area": "full"}}

## 示例
用户: 打开微信 → {"tool": "app_control", "args": {"action": "open", "app_name": "WeChat"}}
用户: 杭州天气 → {"tool": "web_search", "args": {"action": "get_weather", "query": "杭州"}}
用户: 桌面文件 → {"tool": "terminal", "args": {"command": "ls ~/Desktop"}}

需要操作时输出JSON，否则直接回复。用中文。"""

# 完整版系统提示（适合大型模型或远程模型）
LOCAL_MODEL_SYSTEM_PROMPT_FULL = """你是一个强大的 macOS 智能助手，名叫 MacAgent。

## 可用工具（使用 JSON 格式调用）

### 核心工具
- app_control: {"tool": "app_control", "args": {"action": "open|close|list", "app_name": "应用名"}}
- terminal: {"tool": "terminal", "args": {"command": "命令", "working_directory": "可选目录"}}
- file_operations: {"tool": "file_operations", "args": {"action": "read|write|delete|move|copy|list", "path": "路径"}}
- system_info: {"tool": "system_info", "args": {"info_type": "cpu|memory|disk|all"}}
- clipboard: {"tool": "clipboard", "args": {"action": "read|write", "content": "内容"}}

### 网络工具
- web_search: {"tool": "web_search", "args": {"action": "search|news|get_weather|translate", "query": "搜索词"}}
- wikipedia: {"tool": "wikipedia", "args": {"action": "summary", "query": "关键词"}}
- browser: {"tool": "browser", "args": {"action": "open|search", "url": "网址"}}

### 媒体工具
- screenshot: {"tool": "screenshot", "args": {"action": "capture|ocr", "area": "full|window"}}
- notification: {"tool": "notification", "args": {"action": "send|speak", "message": "内容"}}

### 开发工具
- developer: {"tool": "developer", "args": {"action": "create_web_app|run_code", "project_name": "名称"}}
- script: {"tool": "script", "args": {"language": "python|bash", "code": "代码"}}
- docker: {"tool": "docker", "args": {"action": "ps|start|stop", "container": "容器"}}
- database: {"tool": "database", "args": {"action": "query", "sql": "SQL"}}

### 系统
- input_control: {"tool": "input_control", "args": {"action": "keyboard_type|mouse_click", "text": "输入内容", "x": 0, "y": 0}} — 键盘鼠标控制，可模拟输入
- request_tool_upgrade: {"tool": "request_tool_upgrade", "args": {"reason": "需要升级的原因"}} — 用户要创建新工具/监控/Agent能力时调用；调用后等待升级完成并使用新工具，禁止用 file_operations 在 ~/ 写脚本

### 其他
- mail: {"tool": "mail", "args": {"action": "send|read_inbox"}}
- calendar: {"tool": "calendar", "args": {"action": "today_events|create_event"}}
- network: {"tool": "network", "args": {"action": "status|ping", "host": "主机"}}

## 使用规则
1. 需要操作时输出 JSON 工具调用
2. 简单问答直接回复，不需要 JSON
3. 每次只调用一个工具
4. 邮件未配置时：引导用户去 Mac 设置 → 邮件 Tab 填写，禁止在 Chat 索要密码
5. 用户要创建新工具/监控/Agent 可调用能力时，调用 request_tool_upgrade，等待升级完成后使用新工具；禁止用 file_operations 在 ~/ 写脚本（工具必在 tools/generated/）

## 示例
用户: 打开微信 → {"tool": "app_control", "args": {"action": "open", "app_name": "WeChat"}}
用户: 杭州天气 → {"tool": "web_search", "args": {"action": "get_weather", "query": "杭州"}}
用户: 翻译 Hello → {"tool": "web_search", "args": {"action": "translate", "query": "Hello", "target_lang": "zh-CN"}}

请用中文回复。"""

# 默认使用精简版（可通过环境变量切换）
import os
_use_full_prompt = os.getenv("MACAGENT_FULL_PROMPT", "false").lower() == "true"
LOCAL_MODEL_SYSTEM_PROMPT = LOCAL_MODEL_SYSTEM_PROMPT_FULL if _use_full_prompt else LOCAL_MODEL_SYSTEM_PROMPT_COMPACT


class LocalToolParser:
    """
    Parses tool calls from local model text responses
    """
    
    # JSON 工具调用的正则模式
    TOOL_PATTERN = re.compile(
        r'\{[^{}]*"tool"\s*:\s*"([^"]+)"[^{}]*"args"\s*:\s*(\{[^{}]*\})[^{}]*\}',
        re.DOTALL
    )
    
    # 更宽松的 JSON 块匹配
    JSON_BLOCK_PATTERN = re.compile(
        r'```(?:json)?\s*(\{.*?\})\s*```|(\{[^{}]*"tool"[^{}]*\})',
        re.DOTALL
    )
    
    @classmethod
    def parse_response(cls, text: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Parse model response to extract tool call and remaining text
        
        Returns:
            (tool_call, remaining_text)
            tool_call: {"name": "tool_name", "arguments": {...}} or None
            remaining_text: Text content without tool call
        """
        if not text:
            return None, ""
        
        text = text.strip()
        
        # 尝试从代码块中提取 JSON
        json_blocks = cls.JSON_BLOCK_PATTERN.findall(text)
        for block in json_blocks:
            json_str = block[0] or block[1]
            if json_str:
                tool_call = cls._try_parse_json(json_str)
                if tool_call:
                    # 移除 JSON 部分，保留其他文本
                    remaining = text.replace(json_str, "").strip()
                    remaining = re.sub(r'```(?:json)?```', '', remaining).strip()
                    return tool_call, remaining
        
        # 尝试直接解析整个文本为 JSON
        tool_call = cls._try_parse_json(text)
        if tool_call:
            return tool_call, ""
        
        # 尝试正则匹配
        match = cls.TOOL_PATTERN.search(text)
        if match:
            tool_name = match.group(1)
            args_str = match.group(2)
            try:
                args = json.loads(args_str)
                tool_call = {
                    "id": f"local_{tool_name}_{hash(text) % 10000}",
                    "name": tool_name,
                    "arguments": args
                }
                remaining = text[:match.start()] + text[match.end():]
                return tool_call, remaining.strip()
            except json.JSONDecodeError:
                pass
        
        # 没有找到工具调用
        return None, text
    
    @classmethod
    def _try_parse_json(cls, text: str) -> Optional[Dict[str, Any]]:
        """Try to parse text as a tool call JSON"""
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "tool" in data:
                return {
                    "id": f"local_{data['tool']}_{hash(text) % 10000}",
                    "name": data["tool"],
                    "arguments": data.get("args", {})
                }
        except json.JSONDecodeError:
            pass
        return None
    
    @classmethod
    def format_tool_result(cls, tool_name: str, result: Any) -> str:
        """Format tool result for local model context"""
        if hasattr(result, 'success'):
            if result.success:
                return f"[系统反馈: 工具 {tool_name} 执行成功]\n结果:\n{result.to_string()}\n\n请根据以上结果，用中文向用户提供完整的回答。"
            else:
                return f"[系统反馈: 工具 {tool_name} 执行失败]\n错误: {result.error}\n\n请向用户解释操作失败的原因，并提供替代建议或解决方案。"
        return f"[系统反馈: 工具 {tool_name} 结果]\n{str(result)}\n\n请根据结果回复用户。"


def is_local_model(provider: str) -> bool:
    """Check if the provider is a local model that needs text-based tool parsing"""
    # 这些本地模型使用文本解析模式（不支持或不擅长 function calling）
    return provider.lower() in ("ollama", "lmstudio", "lm-studio", "local")


def supports_function_calling(provider: str, model: str = "") -> bool:
    """
    Check if the provider/model supports OpenAI-style function calling
    
    Returns True for:
    - DeepSeek API
    - OpenAI API
    - Some specific local models that support function calling
    
    Returns False for:
    - Most Ollama models
    - Most LM Studio models (qwen, llama, etc.)
    """
    provider_lower = provider.lower()
    model_lower = model.lower() if model else ""
    
    # 远程 API 通常支持 function calling
    if provider_lower in ("deepseek", "openai"):
        return True
    
    # 大多数本地模型不支持或不擅长 function calling
    if provider_lower in ("ollama", "lmstudio", "lm-studio", "local"):
        # 特例：某些模型可能支持
        # 但目前默认都使用文本解析模式
        return False
    
    return True  # 默认假设支持


def get_system_prompt_for_provider(provider: str, default_prompt: str) -> str:
    """Get appropriate system prompt based on provider"""
    if is_local_model(provider):
        return LOCAL_MODEL_SYSTEM_PROMPT
    return default_prompt
