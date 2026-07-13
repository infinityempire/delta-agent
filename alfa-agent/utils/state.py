"""
State management utilities for persisting agent state between runs.
"""
import json
from pathlib import Path
from typing import Set, Dict, Any, Optional
from datetime import datetime

from config.settings import STATE_FILE, PROCESSED_POSTS_FILE
from utils.logger import logger


class StateManager:
    """Manages persistent state for the agent."""
    
    def __init__(self):
        """Initialize state manager."""
        self.state_file = STATE_FILE
        self.processed_posts_file = PROCESSED_POSTS_FILE
        self._state: Dict[str, Any] = {}
        self._processed_posts: Set[str] = set()
        self._load_state()
    
    def _load_state(self) -> None:
        """Load state from disk."""
        try:
            if self.state_file.exists():
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
                logger.info(f"Loaded state from {self.state_file}")
            
            if self.processed_posts_file.exists():
                with open(self.processed_posts_file, "r", encoding="utf-8") as f:
                    self._processed_posts = set(json.load(f))
                logger.info(f"Loaded {len(self._processed_posts)} processed posts")
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            self._state = {}
            self._processed_posts = set()
    
    def _save_state(self) -> None:
        """Save state to disk."""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, default=str)
            
            with open(self.processed_posts_file, "w", encoding="utf-8") as f:
                json.dump(list(self._processed_posts), f, indent=2)
            
            logger.debug("State saved to disk")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from state."""
        return self._state.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set a value in state."""
        self._state[key] = value
        self._save_state()
    
    def update_last_run(self) -> None:
        """Update the last run timestamp."""
        self._state["last_run"] = datetime.now().isoformat()
        self._save_state()
    
    def is_post_processed(self, post_id: str) -> bool:
        """Check if a post has been processed."""
        return post_id in self._processed_posts
    
    def mark_post_processed(self, post_id: str) -> None:
        """Mark a post as processed."""
        self._processed_posts.add(post_id)
        self._save_state()
    
    def get_last_processed_subreddits(self) -> Dict[str, str]:
        """Get the last processed timestamp for each subreddit."""
        return self._state.get("subreddit_timestamps", {})
    
    def update_subreddit_timestamp(self, subreddit: str) -> None:
        """Update the last processed timestamp for a subreddit."""
        if "subreddit_timestamps" not in self._state:
            self._state["subreddit_timestamps"] = {}
        self._state["subreddit_timestamps"][subreddit] = datetime.now().isoformat()
        self._save_state()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about agent runs."""
        return {
            "total_processed_posts": len(self._processed_posts),
            "last_run": self._state.get("last_run"),
            "subreddits": self.get_last_processed_subreddits(),
        }
    
    def reset(self) -> None:
        """Reset all state (use with caution)."""
        self._state = {}
        self._processed_posts = set()
        self._save_state()
        logger.warning("State has been reset")


# Global state manager instance
state_manager = StateManager()
