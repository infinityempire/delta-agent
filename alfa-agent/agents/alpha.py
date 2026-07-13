"""
Zeta - Reddit Marketing & Distribution Agent
A multi-agent system for automated Reddit engagement.

Named "Zeta" - a next-generation intelligent Reddit agent.
"""
import asyncio
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from config.settings import (
    TARGET_SUBREDDITS,
    PUBLISHING_CONFIG,
    GENERATED_COMMENTS_FILE,
)
from utils.logger import logger
from utils.state import state_manager
from utils.delay import get_random_delay_seconds

from agents.reddit_scraper import RedditScraperAgent
from agents.gemini_writer import GeminiWriterAgent
from agents.publishing_engine import PublishingEngine


class Zeta:
    """
    Zeta - The Reddit Distribution Agent
    
    A multi-agent system that:
    1. Scrapes Reddit posts from target subreddits
    2. Generates human-like comments using Gemini AI
    3. Publishes with randomized delays to avoid detection
    """
    
    def __init__(self, dry_run: bool = True):
        """
        Initialize Zeta.
        
        Args:
            dry_run: If True, don't actually post to Reddit
        """
        self.name = "Zeta"
        self.version = "1.0.0"
        self.dry_run = dry_run
        self.reddit_scraper = None
        self.gemini_writer = None
        self.publishing_engine = None
        self._initialized = False
        
        logger.info(f"🤖 {self} initialized")
    
    def __str__(self) -> str:
        return f"{self.name} v{self.version}"
    
    async def initialize(self) -> None:
        """Initialize all agent components."""
        if self._initialized:
            return
        
        logger.info(f"Initializing {self}...")
        
        try:
            self.reddit_scraper = RedditScraperAgent(mock_mode=self.dry_run)
            self.gemini_writer = GeminiWriterAgent(mock_mode=self.dry_run)
            self.publishing_engine = PublishingEngine(mock_mode=self.dry_run)
            
            self._initialized = True
            logger.info(f"{self} ready for operation")
            
        except Exception as e:
            logger.error(f"Failed to initialize {self}: {e}")
            raise
    
    async def scout(self, subreddits: Optional[List[str]] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Scout/Scraping phase - Find relevant posts.
        
        Args:
            subreddits: Target subreddits
            limit: Posts per subreddit
            
        Returns:
            List of discovered posts
        """
        logger.info("🔍 ZETA SCOUTING REDDIT...")
        posts = await self.reddit_scraper.fetch_posts(subreddits=subreddits, limit=limit)
        logger.info(f"📊 Found {len(posts)} relevant posts")
        return posts
    
    async def think(self, posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Think/Generation phase - Generate responses.
        
        Args:
            posts: Posts to generate comments for
            
        Returns:
            Generated comment results
        """
        logger.info("💭 ZETA THINKING...")
        
        comments_map = {}
        
        # Only fetch comments if not in mock mode
        if not self.reddit_scraper.mock_mode:
            for post in posts[:5]:
                try:
                    comments = self.reddit_scraper.get_post_comments(post["id"], limit=5)
                    if comments:
                        comments_map[post["id"]] = comments
                except Exception as e:
                    logger.warning(f"Could not fetch comments: {e}")
        
        results = await self.gemini_writer.generate_comments_batch(posts, comments_map)
        self.gemini_writer.save_generated_comments(results)
        
        successful = sum(1 for r in results if r["success"])
        logger.info(f"✨ Generated {successful} responses")
        return results
    
    async def act(self, results: List[Dict[str, Any]], max_posts: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Act/Publishing phase - Post to Reddit.
        
        Args:
            results: Generated comment results
            max_posts: Maximum posts to publish
            
        Returns:
            Publishing results
        """
        if self.dry_run:
            logger.info("🎭 ZETA DRY RUN - No posts made")
            successful = [r for r in results if r["success"] and r.get("generated_comment")]
            for r in successful[:5]:
                logger.info(f"   → {r['post_title'][:50]}...")
            return []
        
        logger.info("🎯 ZETA PUBLISHING...")
        
        successful = [
            {"post_id": r["post_id"], "comment": r["generated_comment"]}
            for r in results
            if r["success"] and r.get("generated_comment")
        ]
        
        publishing_results = await self.publishing_engine.publish_queue(successful, max_posts)
        logger.info(f"📤 Published {len(publishing_results)} comments")
        return publishing_results
    
    async def run(
        self,
        subreddits: Optional[List[str]] = None,
        max_posts: Optional[int] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Execute the full Zeta pipeline: Scout → Think → Act
        
        Args:
            subreddits: Target subreddits
            max_posts: Max posts to process
            limit: Posts per subreddit
            
        Returns:
            Pipeline results summary
        """
        start_time = datetime.now()
        mode = "🧪 DRY RUN" if self.dry_run else "🚀 LIVE"
        
        logger.info("=" * 60)
        logger.info(f"{self} - {mode}")
        logger.info(f"Target: {subreddits or TARGET_SUBREDDITS}")
        logger.info("=" * 60)
        
        try:
            await self.initialize()
            
            posts = await self.scout(subreddits, limit)
            if max_posts:
                posts = posts[:max_posts]
            
            if not posts:
                return {"status": "no_posts", "scouted": 0, "generated": 0, "published": 0}
            
            results = await self.think(posts)
            await self.act(results, max_posts)
            
            state_manager.update_last_run()
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return {
                "agent": str(self),
                "status": "complete",
                "mode": "dry_run" if self.dry_run else "live",
                "duration": f"{duration:.1f}s",
                "scouted": len(posts),
                "generated": sum(1 for r in results if r["success"]),
            }
            
        except Exception as e:
            logger.error(f"Zeta error: {e}")
            raise
    
    async def status(self) -> Dict[str, Any]:
        """Get Zeta's current status."""
        return {
            "name": self.name,
            "version": self.version,
            "initialized": self._initialized,
            "mode": "dry_run" if self.dry_run else "live",
            "stats": state_manager.get_stats(),
        }


async def main():
    """Zeta entry point."""
    parser = argparse.ArgumentParser(description="Zeta - Reddit Distribution Agent")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--live", action="store_false", dest="dry_run")
    parser.add_argument("--subreddits", nargs="+")
    parser.add_argument("--max-posts", type=int)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--status", action="store_true")
    
    args = parser.parse_args()
    
    zeta = Zeta(dry_run=args.dry_run)
    
    if args.status:
        print(json.dumps(await zeta.status(), indent=2))
        return
    
    await zeta.initialize()
    results = await zeta.run(
        subreddits=args.subreddits,
        max_posts=args.max_posts,
        limit=args.limit,
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
