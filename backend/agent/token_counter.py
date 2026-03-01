"""
本地 Token 计数器

为不返回 usage 信息的 API（如 New API）提供本地 token 计算。
使用 tiktoken 库进行估算。
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# 延迟加载 tiktoken，避免启动时阻塞
_encoding = None

def _get_encoding():
    """获取 tiktoken 编码器（延迟加载）"""
    global _encoding
    if _encoding is None:
        try:
            import tiktoken
            # 使用 cl100k_base，这是 GPT-4/GPT-3.5-turbo/text-embedding-ada-002 使用的编码
            # 对于 DeepSeek 等其他模型，这是一个合理的近似值
            _encoding = tiktoken.get_encoding("cl100k_base")
            logger.info("Token counter initialized with cl100k_base encoding")
        except ImportError:
            logger.warning("tiktoken not installed, token counting will be disabled")
            return None
        except Exception as e:
            logger.warning(f"Failed to initialize tiktoken: {e}")
            return None
    return _encoding


def count_tokens(text: str) -> int:
    """
    计算文本的 token 数
    
    Args:
        text: 要计算的文本
        
    Returns:
        token 数量，如果计算失败返回 0
    """
    if not text:
        return 0
    
    encoding = _get_encoding()
    if encoding is None:
        return 0
    
    try:
        return len(encoding.encode(text))
    except Exception as e:
        logger.debug(f"Token counting error: {e}")
        return 0


def count_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """
    计算消息列表的 token 数
    
    遵循 OpenAI 的消息格式计算规则：
    - 每条消息有固定开销 (约 4 tokens)
    - 加上 role 和 content 的 token 数
    
    Args:
        messages: OpenAI 格式的消息列表
        
    Returns:
        估算的 prompt token 数
    """
    encoding = _get_encoding()
    if encoding is None:
        return 0
    
    total = 0
    # 每条消息的固定开销
    tokens_per_message = 4
    
    try:
        for msg in messages:
            total += tokens_per_message
            
            # 计算 role
            role = msg.get("role", "")
            if role:
                total += len(encoding.encode(role))
            
            # 计算 content
            content = msg.get("content")
            if isinstance(content, str):
                total += len(encoding.encode(content))
            elif isinstance(content, list):
                # 多模态内容
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text = item.get("text", "")
                            if text:
                                total += len(encoding.encode(text))
                        elif item.get("type") == "image_url":
                            # 图像按固定 token 计算（低分辨率约 85，高分辨率 ~170+）
                            total += 170
            
            # 计算 name（如果有）
            name = msg.get("name")
            if name:
                total += len(encoding.encode(name))
                total -= 1  # name 减少一个 token
        
        # 回复的固定开销
        total += 3
        
        return total
        
    except Exception as e:
        logger.debug(f"Message token counting error: {e}")
        return 0


class StreamTokenCounter:
    """
    流式响应的 Token 计数器
    
    在流式响应过程中累加 completion tokens，
    并在完成时返回总计。
    """
    
    def __init__(self, prompt_tokens: int = 0):
        """
        初始化计数器
        
        Args:
            prompt_tokens: 预计算的 prompt token 数
        """
        self.prompt_tokens = prompt_tokens
        self._completion_text = ""
        self._completion_tokens = 0
        self._finalized = False
    
    def add_content(self, text: str):
        """添加流式内容"""
        if text:
            self._completion_text += text
    
    def finalize(self) -> Dict[str, int]:
        """
        完成计数并返回 usage 信息
        
        Returns:
            包含 prompt_tokens, completion_tokens, total_tokens 的字典
        """
        if not self._finalized:
            self._completion_tokens = count_tokens(self._completion_text)
            self._finalized = True
        
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "total_tokens": self.prompt_tokens + self._completion_tokens
        }
    
    @property
    def completion_tokens(self) -> int:
        """获取当前 completion tokens（实时计算）"""
        return count_tokens(self._completion_text)
