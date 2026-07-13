"""
Delay and scheduling utilities for randomized publishing.
"""
import asyncio
import random
from typing import Optional

from config.settings import PUBLISHING_CONFIG
from utils.logger import logger


def get_random_delay_seconds() -> int:
    """
    Get a random delay between min and max configured values.
    
    Returns:
        Delay in seconds
    """
    min_delay = PUBLISHING_CONFIG["min_delay_minutes"] * 60
    max_delay = PUBLISHING_CONFIG["max_delay_minutes"] * 60
    delay = random.randint(min_delay, max_delay)
    logger.debug(f"Random delay selected: {delay} seconds ({delay/60:.1f} minutes)")
    return delay


async def async_random_delay() -> None:
    """
    Async version of random delay for use with asyncio.
    """
    delay = get_random_delay_seconds()
    logger.info(f"Waiting {delay} seconds ({delay/60:.1f} minutes) before next action...")
    await asyncio.sleep(delay)


def sync_random_delay() -> None:
    """
    Synchronous version of random delay using time.sleep.
    """
    import time
    delay = get_random_delay_seconds()
    logger.info(f"Waiting {delay} seconds ({delay/60:.1f} minutes) before next action...")
    time.sleep(delay)


class PublishingQueue:
    """
    Queue for managing delayed publishing of comments.
    """
    
    def __init__(self):
        """Initialize the publishing queue."""
        self._queue: list = []
        self._is_running = False
    
    def add_to_queue(self, item: dict) -> None:
        """
        Add an item to the publishing queue.
        
        Args:
            item: Dictionary containing post_id, comment, and metadata
        """
        self._queue.append(item)
        logger.info(f"Added item to publishing queue. Queue size: {len(self._queue)}")
    
    def get_queue_size(self) -> int:
        """Get the current queue size."""
        return len(self._queue)
    
    def clear_queue(self) -> None:
        """Clear all items from the queue."""
        self._queue.clear()
        logger.info("Publishing queue cleared")
    
    async def process_queue(self, reddit_agent) -> list:
        """
        Process the queue with random delays between items.
        
        Args:
            reddit_agent: Reddit API agent for posting comments
            
        Returns:
            List of results from posting
        """
        results = []
        self._is_running = True
        
        while self._queue and self._is_running:
            item = self._queue.pop(0)
            
            try:
                if PUBLISHING_CONFIG["dry_run"]:
                    logger.info(f"[DRY RUN] Would post comment to post {item['post_id']}")
                    logger.info(f"[DRY RUN] Comment: {item['comment'][:100]}...")
                    results.append({
                        "post_id": item["post_id"],
                        "status": "dry_run_success",
                        "comment": item["comment"],
                    })
                else:
                    result = await reddit_agent.post_comment(
                        submission_id=item["post_id"],
                        comment_text=item["comment"]
                    )
                    results.append(result)
                    logger.info(f"Successfully posted to {item['post_id']}")
                
                # Add random delay between posts (except for the last one)
                if self._queue:
                    await async_random_delay()
                    
            except Exception as e:
                logger.error(f"Error processing queue item: {e}")
                results.append({
                    "post_id": item["post_id"],
                    "status": "error",
                    "error": str(e)
                })
        
        self._is_running = False
        return results
    
    def stop(self) -> None:
        """Stop queue processing."""
        self._is_running = False
        logger.info("Publishing queue stopped")


# Global queue instance
publishing_queue = PublishingQueue()
