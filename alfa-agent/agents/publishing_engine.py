"""
Humanization & Publishing Engine.
Manages publishing schedules with random delays and posts comments to Reddit.
"""
import asyncio
import random
from typing import List, Dict, Any, Optional
from datetime import datetime

import praw
from praw.models import Submission

from config.settings import REDDIT_CONFIG, PUBLISHING_CONFIG
from utils.logger import logger
from utils.state import state_manager


class PublishingEngine:
    """
    Engine responsible for publishing comments with human-like delays.
    """
    
    def __init__(self, mock_mode: bool = False):
        """Initialize the publishing engine."""
        self.reddit = None
        self.mock_mode = mock_mode
        self._initialize_reddit()
        self._pending_comments: List[Dict[str, Any]] = []
    
    def _initialize_reddit(self) -> None:
        """Initialize the Reddit API connection."""
        if self.mock_mode:
            logger.info("Publishing engine running in MOCK mode")
            return
            
        # Check if credentials are configured
        if not REDDIT_CONFIG["client_id"] or REDDIT_CONFIG["client_id"].startswith("your_"):
            logger.warning("Reddit credentials not configured. Publishing in MOCK mode.")
            self.mock_mode = True
            return
            
        try:
            self.reddit = praw.Reddit(
                client_id=REDDIT_CONFIG["client_id"],
                client_secret=REDDIT_CONFIG["client_secret"],
                user_agent=REDDIT_CONFIG["user_agent"],
                username=REDDIT_CONFIG["username"],
                password=REDDIT_CONFIG["password"],
            )
            logger.info("Publishing engine initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Reddit connection: {e}. Running in MOCK mode.")
            self.mock_mode = True
    
    def _calculate_delay(self) -> int:
        """
        Calculate a random delay in seconds.
        
        Returns:
            Delay in seconds between configured min and max values
        """
        min_delay = PUBLISHING_CONFIG["min_delay_minutes"] * 60
        max_delay = PUBLISHING_CONFIG["max_delay_minutes"] * 60
        delay = random.randint(min_delay, max_delay)
        return delay
    
    async def _human_delay(self) -> None:
        """
        Perform a human-like delay before posting.
        Adds jitter to make timing more natural.
        """
        base_delay = self._calculate_delay()
        # Add some randomness (±10%)
        jitter = int(base_delay * random.uniform(-0.1, 0.1))
        actual_delay = base_delay + jitter
        
        delay_minutes = actual_delay / 60
        logger.info(f"Human-like delay: {delay_minutes:.1f} minutes")
        
        await asyncio.sleep(actual_delay)
    
    def _simulate_human_typing(self) -> None:
        """
        Simulate human typing patterns (adds small random delays).
        This is a placeholder for more sophisticated humanization.
        """
        # Small pause to simulate thinking/typing
        typing_delay = random.uniform(0.5, 2.0)
        logger.debug(f"Simulating typing delay: {typing_delay:.1f}s")
        import time
        time.sleep(typing_delay)
    
    async def post_comment(
        self,
        submission_id: str,
        comment_text: str,
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Post a comment to a Reddit submission.
        
        Args:
            submission_id: Reddit submission ID
            comment_text: Comment text to post
            parent_id: Optional parent comment ID for replies
            
        Returns:
            Result dictionary with status and details
        """
        # Check if in dry run mode
        if PUBLISHING_CONFIG["dry_run"]:
            logger.info(f"[DRY RUN] Would post comment to {submission_id}")
            logger.info(f"[DRY RUN] Comment preview: {comment_text[:100]}...")
            return {
                "status": "dry_run",
                "submission_id": submission_id,
                "comment_preview": comment_text[:200],
                "timestamp": datetime.now().isoformat(),
            }
        
        try:
            # Get the submission
            submission = self.reddit.submission(id=submission_id)
            
            # Human-like delay before posting
            await self._human_delay()
            self._simulate_human_typing()
            
            # Post the comment
            if parent_id:
                parent = self.reddit.comment(id=parent_id)
                comment = parent.reply(comment_text)
            else:
                comment = submission.reply(comment_text)
            
            logger.info(f"Successfully posted comment {comment.id} to {submission_id}")
            
            # Mark post as processed
            state_manager.mark_post_processed(submission_id)
            
            return {
                "status": "success",
                "submission_id": submission_id,
                "comment_id": comment.id,
                "permalink": f"https://reddit.com{comment.permalink}",
                "timestamp": datetime.now().isoformat(),
            }
            
        except praw.exceptions.PRAWException as e:
            logger.error(f"PRAW error posting comment: {e}")
            return {
                "status": "error",
                "submission_id": submission_id,
                "error": str(e),
                "error_type": "praw",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error posting comment: {e}")
            return {
                "status": "error",
                "submission_id": submission_id,
                "error": str(e),
                "error_type": "unknown",
                "timestamp": datetime.now().isoformat(),
            }
    
    async def publish_queue(
        self,
        comments: List[Dict[str, Any]],
        max_posts: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Publish a queue of comments with random delays between each.
        
        Args:
            comments: List of comment dictionaries with post_id and comment text
            max_posts: Maximum number of posts to publish (None for all)
            
        Returns:
            List of result dictionaries
        """
        if max_posts is None:
            max_posts = PUBLISHING_CONFIG["max_posts_per_run"]
        
        results = []
        to_publish = comments[:max_posts]
        
        logger.info(f"Starting to publish {len(to_publish)} comments")
        
        for i, item in enumerate(to_publish, 1):
            logger.info(f"Publishing comment {i}/{len(to_publish)}")
            
            result = await self.post_comment(
                submission_id=item["post_id"],
                comment_text=item["comment"],
            )
            
            results.append(result)
            
            # Add delay between posts (except for the last one)
            if i < len(to_publish):
                await self._human_delay()
        
        success_count = sum(1 for r in results if r["status"] in ["success", "dry_run"])
        logger.info(f"Published {success_count}/{len(results)} comments successfully")
        
        return results
    
    def add_to_queue(self, submission_id: str, comment_text: str) -> None:
        """
        Add a comment to the pending queue.
        
        Args:
            submission_id: Reddit submission ID
            comment_text: Comment text to post
        """
        self._pending_comments.append({
            "post_id": submission_id,
            "comment": comment_text,
            "queued_at": datetime.now().isoformat(),
        })
        logger.info(f"Added comment to queue. Queue size: {len(self._pending_comments)}")
    
    def get_queue_size(self) -> int:
        """Get the current queue size."""
        return len(self._pending_comments)
    
    def clear_queue(self) -> None:
        """Clear all pending comments from the queue."""
        self._pending_comments.clear()
        logger.info("Publishing queue cleared")
    
    async def process_queue(self, max_posts: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Process all pending comments in the queue.
        
        Args:
            max_posts: Maximum posts to publish
            
        Returns:
            List of result dictionaries
        """
        if not self._pending_comments:
            logger.info("No comments in queue to process")
            return []
        
        results = await self.publish_queue(self._pending_comments, max_posts)
        self.clear_queue()
        return results
    
    def preview_comment(self, submission_id: str, comment_text: str) -> Dict[str, Any]:
        """
        Preview what a comment would look like without posting.
        
        Args:
            submission_id: Reddit submission ID
            comment_text: Comment text
            
        Returns:
            Preview dictionary
        """
        return {
            "preview": True,
            "submission_id": submission_id,
            "comment_text": comment_text,
            "character_count": len(comment_text),
            "timestamp": datetime.now().isoformat(),
        }
