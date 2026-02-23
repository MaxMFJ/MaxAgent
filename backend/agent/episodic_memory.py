"""
Episodic Memory System for Autonomous Agent
Stores and retrieves task execution experiences for learning
"""

import os
import json
import logging
import hashlib
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Episode:
    """
    A complete episode of task execution
    Stores the full history for learning and retrieval
    """
    episode_id: str
    task_description: str
    task_embedding: Optional[List[float]] = None
    action_log: List[Dict[str, Any]] = field(default_factory=list)
    result: str = "unknown"
    success: bool = False
    total_actions: int = 0
    total_iterations: int = 0
    execution_time_ms: int = 0
    user_feedback: Optional[str] = None
    strategies_used: List[str] = field(default_factory=list)
    reflection: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.now)
    # Token 使用量跟踪
    token_usage: Dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "task_description": self.task_description,
            "action_log": self.action_log,
            "result": self.result,
            "success": self.success,
            "total_actions": self.total_actions,
            "total_iterations": self.total_iterations,
            "execution_time_ms": self.execution_time_ms,
            "user_feedback": self.user_feedback,
            "strategies_used": self.strategies_used,
            "reflection": self.reflection,
            "created_at": self.created_at.isoformat(),
            "token_usage": self.token_usage
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Episode":
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()
        
        return cls(
            episode_id=data.get("episode_id", ""),
            task_description=data.get("task_description", ""),
            action_log=data.get("action_log", []),
            result=data.get("result", "unknown"),
            success=data.get("success", False),
            total_actions=data.get("total_actions", 0),
            total_iterations=data.get("total_iterations", 0),
            execution_time_ms=data.get("execution_time_ms", 0),
            user_feedback=data.get("user_feedback"),
            strategies_used=data.get("strategies_used", []),
            reflection=data.get("reflection"),
            created_at=created_at,
            token_usage=data.get("token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        )
    
    def get_summary(self) -> str:
        """Get a brief summary of the episode"""
        status = "成功" if self.success else "失败"
        return f"[{status}] {self.task_description[:50]}... ({self.total_actions} actions)"


class EpisodicMemory:
    """
    Episodic memory system for storing and retrieving task experiences
    Uses both file storage and optional vector search for retrieval
    """
    
    def __init__(
        self,
        storage_dir: Optional[str] = None,
        max_episodes: int = 1000,
        enable_vector_search: bool = True
    ):
        if storage_dir is None:
            storage_dir = os.path.join(
                os.path.dirname(__file__),
                "..", "data", "episodes"
            )
        
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_episodes = max_episodes
        self.enable_vector_search = enable_vector_search
        
        self._episodes_cache: Dict[str, Episode] = {}
        self._index_file = self.storage_dir / "index.json"
        self._load_index()
    
    def _load_index(self):
        """Load episode index from disk"""
        if self._index_file.exists():
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    index = json.load(f)
                    logger.info(f"Loaded {len(index)} episodes from index")
            except Exception as e:
                logger.error(f"Failed to load index: {e}")
    
    def _save_index(self, episodes: List[str]):
        """Save episode index to disk"""
        try:
            with open(self._index_file, "w", encoding="utf-8") as f:
                json.dump(episodes, f)
        except Exception as e:
            logger.error(f"Failed to save index: {e}")
    
    def _generate_episode_id(self, task: str) -> str:
        """Generate unique episode ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_hash = hashlib.md5(task.encode()).hexdigest()[:6]
        return f"ep_{timestamp}_{task_hash}"
    
    def add_episode(self, episode: Episode) -> str:
        """Add a new episode to memory"""
        episode_file = self.storage_dir / f"{episode.episode_id}.json"
        
        try:
            with open(episode_file, "w", encoding="utf-8") as f:
                json.dump(episode.to_dict(), f, ensure_ascii=False, indent=2)
            
            self._episodes_cache[episode.episode_id] = episode
            
            self._cleanup_old_episodes()
            
            logger.info(f"Saved episode: {episode.episode_id}")
            return episode.episode_id
            
        except Exception as e:
            logger.error(f"Failed to save episode: {e}")
            raise
    
    def get_episode(self, episode_id: str) -> Optional[Episode]:
        """Get an episode by ID"""
        if episode_id in self._episodes_cache:
            return self._episodes_cache[episode_id]
        
        episode_file = self.storage_dir / f"{episode_id}.json"
        if not episode_file.exists():
            return None
        
        try:
            with open(episode_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            episode = Episode.from_dict(data)
            self._episodes_cache[episode_id] = episode
            return episode
            
        except Exception as e:
            logger.error(f"Failed to load episode {episode_id}: {e}")
            return None
    
    def search_similar(
        self,
        task_description: str,
        top_k: int = 5,
        success_only: bool = False
    ) -> List[Episode]:
        """
        Search for similar past episodes
        Uses simple keyword matching if vector search is disabled
        """
        all_episodes = self._get_all_episodes()
        
        if success_only:
            all_episodes = [ep for ep in all_episodes if ep.success]
        
        scored_episodes = []
        task_words = set(task_description.lower().split())
        
        for episode in all_episodes:
            ep_words = set(episode.task_description.lower().split())
            
            if task_words and ep_words:
                intersection = len(task_words & ep_words)
                union = len(task_words | ep_words)
                score = intersection / union if union > 0 else 0
            else:
                score = 0
            
            scored_episodes.append((score, episode))
        
        scored_episodes.sort(key=lambda x: x[0], reverse=True)
        
        return [ep for _, ep in scored_episodes[:top_k]]
    
    def get_recent(self, count: int = 10) -> List[Episode]:
        """Get most recent episodes"""
        all_episodes = self._get_all_episodes()
        
        all_episodes.sort(key=lambda x: x.created_at, reverse=True)
        
        return all_episodes[:count]
    
    def get_successful_strategies(self) -> List[str]:
        """Get strategies from successful episodes"""
        all_episodes = self._get_all_episodes()
        
        strategies = []
        for episode in all_episodes:
            if episode.success and episode.strategies_used:
                strategies.extend(episode.strategies_used)
        
        from collections import Counter
        strategy_counts = Counter(strategies)
        
        return [s for s, _ in strategy_counts.most_common(10)]
    
    def add_feedback(self, episode_id: str, feedback: str):
        """Add user feedback to an episode"""
        episode = self.get_episode(episode_id)
        if episode:
            episode.user_feedback = feedback
            episode_file = self.storage_dir / f"{episode_id}.json"
            
            try:
                with open(episode_file, "w", encoding="utf-8") as f:
                    json.dump(episode.to_dict(), f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Failed to save feedback: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about stored episodes"""
        all_episodes = self._get_all_episodes()
        
        if not all_episodes:
            return {
                "total_episodes": 0,
                "success_rate": 0,
                "avg_actions": 0,
                "total_actions": 0,
                "total_tokens": 0,
                "avg_tokens_per_episode": 0
            }
        
        successful = sum(1 for ep in all_episodes if ep.success)
        total_actions = sum(ep.total_actions for ep in all_episodes)
        
        # Token 使用量统计
        total_prompt_tokens = sum(ep.token_usage.get("prompt_tokens", 0) for ep in all_episodes)
        total_completion_tokens = sum(ep.token_usage.get("completion_tokens", 0) for ep in all_episodes)
        total_tokens = sum(ep.token_usage.get("total_tokens", 0) for ep in all_episodes)
        
        return {
            "total_episodes": len(all_episodes),
            "success_rate": round(successful / len(all_episodes) * 100, 1),
            "successful_episodes": successful,
            "failed_episodes": len(all_episodes) - successful,
            "avg_actions": round(total_actions / len(all_episodes), 1),
            "total_actions": total_actions,
            "total_tokens": total_tokens,
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "avg_tokens_per_episode": round(total_tokens / len(all_episodes), 1) if all_episodes else 0
        }
    
    def _get_all_episodes(self) -> List[Episode]:
        """Get all episodes from storage"""
        episodes = []
        
        for file_path in self.storage_dir.glob("ep_*.json"):
            episode_id = file_path.stem
            
            if episode_id in self._episodes_cache:
                episodes.append(self._episodes_cache[episode_id])
                continue
            
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                episode = Episode.from_dict(data)
                self._episodes_cache[episode_id] = episode
                episodes.append(episode)
            except Exception as e:
                logger.error(f"Failed to load {file_path}: {e}")
        
        return episodes
    
    def _cleanup_old_episodes(self):
        """Remove old episodes if over capacity"""
        all_files = list(self.storage_dir.glob("ep_*.json"))
        
        if len(all_files) <= self.max_episodes:
            return
        
        all_files.sort(key=lambda x: x.stat().st_mtime)
        
        remove_count = len(all_files) - self.max_episodes
        for file_path in all_files[:remove_count]:
            try:
                episode_id = file_path.stem
                file_path.unlink()
                if episode_id in self._episodes_cache:
                    del self._episodes_cache[episode_id]
                logger.info(f"Removed old episode: {episode_id}")
            except Exception as e:
                logger.error(f"Failed to remove {file_path}: {e}")
    
    def clear(self):
        """Clear all episodes"""
        for file_path in self.storage_dir.glob("ep_*.json"):
            try:
                file_path.unlink()
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}")
        
        self._episodes_cache.clear()
        logger.info("Cleared all episodes")


# Strategy database for learned strategies
class StrategyDB:
    """Database for storing learned strategies"""
    
    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            storage_path = os.path.join(
                os.path.dirname(__file__),
                "..", "data", "strategies.json"
            )
        
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.strategies: Dict[str, Dict[str, Any]] = {}
        self._load()
    
    def _load(self):
        """Load strategies from disk"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self.strategies = json.load(f)
                logger.info(f"Loaded {len(self.strategies)} strategies")
            except Exception as e:
                logger.error(f"Failed to load strategies: {e}")
    
    def _save(self):
        """Save strategies to disk"""
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.strategies, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save strategies: {e}")
    
    def add_strategy(
        self,
        name: str,
        description: str,
        applicable_tasks: List[str]
    ) -> str:
        """Add a new strategy"""
        strategy_id = hashlib.md5(name.encode()).hexdigest()[:8]
        
        if strategy_id in self.strategies:
            self.strategies[strategy_id]["usage_count"] += 1
        else:
            self.strategies[strategy_id] = {
                "name": name,
                "description": description,
                "applicable_tasks": applicable_tasks,
                "success_count": 0,
                "usage_count": 1,
                "created_at": datetime.now().isoformat()
            }
        
        self._save()
        return strategy_id
    
    def update_success(self, strategy_id: str, success: bool):
        """Update strategy success rate"""
        if strategy_id in self.strategies:
            self.strategies[strategy_id]["usage_count"] += 1
            if success:
                self.strategies[strategy_id]["success_count"] += 1
            self._save()
    
    def get_strategies_for_task(self, task_description: str) -> List[Dict[str, Any]]:
        """Get applicable strategies for a task"""
        task_words = set(task_description.lower().split())
        
        applicable = []
        for strat_id, strat in self.strategies.items():
            for task_type in strat.get("applicable_tasks", []):
                task_type_words = set(task_type.lower().split())
                if task_words & task_type_words:
                    applicable.append({
                        "id": strat_id,
                        **strat
                    })
                    break
        
        applicable.sort(
            key=lambda x: x.get("success_count", 0) / max(x.get("usage_count", 1), 1),
            reverse=True
        )
        
        return applicable[:5]
    
    def get_top_strategies(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get top performing strategies"""
        all_strategies = [
            {"id": sid, **data}
            for sid, data in self.strategies.items()
        ]
        
        all_strategies.sort(
            key=lambda x: x.get("success_count", 0) / max(x.get("usage_count", 1), 1),
            reverse=True
        )
        
        return all_strategies[:count]


# Global instances
_episodic_memory: Optional[EpisodicMemory] = None
_strategy_db: Optional[StrategyDB] = None


def get_episodic_memory() -> EpisodicMemory:
    """Get or create global episodic memory"""
    global _episodic_memory
    if _episodic_memory is None:
        _episodic_memory = EpisodicMemory()
    return _episodic_memory


def get_strategy_db() -> StrategyDB:
    """Get or create global strategy database"""
    global _strategy_db
    if _strategy_db is None:
        _strategy_db = StrategyDB()
    return _strategy_db
