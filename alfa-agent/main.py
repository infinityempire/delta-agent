#!/usr/bin/env python3
"""
Main Controller for Reddit Distributor Agent.
Orchestrates the entire pipeline: Scrape → Generate → Publish.
"""
import asyncio
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

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


class RedditDistributorController:
    """
    Central controller that orchestrates the entire Reddit distribution pipeline.
    """
    
    def __init__(self, dry_run: bool = True):
        """
        Initialize the controller.
        
        Args:
            dry_run: If True, don't actually post to Reddit
        """
        self.dry_run = dry_run
        self.reddit_scraper = None
        self.gemini_writer = None
        self.publishing_engine = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize all agents."""
        if self._initialized:
            return
        
        logger.info("Initializing Reddit Distributor Agent...")
        
        try:
            # Initialize Reddit Scraper
            logger.info("Initializing Reddit Scraper Agent...")
            self.reddit_scraper = RedditScraperAgent()
            
            # Initialize Gemini Writer
            logger.info("Initializing Gemini Writer Agent...")
            self.gemini_writer = GeminiWriterAgent()
            
            # Initialize Publishing Engine
            logger.info("Initializing Publishing Engine...")
            self.publishing_engine = PublishingEngine()
            
            self._initialized = True
            logger.info("All agents initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize agents: {e}")
            raise
    
    async def scrape_posts(
        self,
        subreddits: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Scrape posts from target subreddits.
        
        Args:
            subreddits: List of subreddits to scrape
            limit: Maximum posts per subreddit
            
        Returns:
            List of post dictionaries
        """
        logger.info("=" * 50)
        logger.info("PHASE 1: SCRAPING REDDIT POSTS")
        logger.info("=" * 50)
        
        posts = await self.reddit_scraper.fetch_posts(
            subreddits=subreddits,
            limit=limit,
        )
        
        logger.info(f"Scraped {len(posts)} relevant posts")
        return posts
    
    async def generate_comments(self, posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate comments for scraped posts.
        
        Args:
            posts: List of post dictionaries
            
        Returns:
            List of result dictionaries with generated comments
        """
        logger.info("=" * 50)
        logger.info("PHASE 2: GENERATING COMMENTS WITH GEMINI")
        logger.info("=" * 50)
        
        # Fetch existing comments for context
        comments_map = {}
        for post in posts[:5]:  # Limit to avoid too many API calls
            try:
                comments = self.reddit_scraper.get_post_comments(post["id"], limit=5)
                if comments:
                    comments_map[post["id"]] = comments
            except Exception as e:
                logger.warning(f"Could not fetch comments for {post['id']}: {e}")
        
        # Generate comments
        results = await self.gemini_writer.generate_comments_batch(posts, comments_map)
        
        # Save generated comments
        self.gemini_writer.save_generated_comments(results)
        
        # Filter successful generations
        successful = [r for r in results if r["success"]]
        logger.info(f"Generated {len(successful)} comments successfully")
        
        return results
    
    async def publish_comments(
        self,
        generated_results: List[Dict[str, Any]],
        max_posts: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Publish generated comments to Reddit.
        
        Args:
            generated_results: List of results from comment generation
            max_posts: Maximum number of posts to publish
            
        Returns:
            List of publishing results
        """
        logger.info("=" * 50)
        logger.info("PHASE 3: PUBLISHING COMMENTS")
        logger.info("=" * 50)
        
        if self.dry_run:
            logger.info("[DRY RUN MODE] - Comments will NOT be posted to Reddit")
        
        # Filter successful generations
        successful = [
            {"post_id": r["post_id"], "comment": r["generated_comment"]}
            for r in generated_results
            if r["success"] and r.get("generated_comment")
        ]
        
        if not successful:
            logger.warning("No successful comments to publish")
            return []
        
        # Publish using the queue
        results = await self.publishing_engine.publish_queue(
            comments=successful,
            max_posts=max_posts,
        )
        
        return results
    
    async def run_full_pipeline(
        self,
        subreddits: Optional[List[str]] = None,
        max_posts: Optional[int] = None,
        limit_per_subreddit: int = 20,
    ) -> Dict[str, Any]:
        """
        Run the complete pipeline: Scrape → Generate → Publish.
        
        Args:
            subreddits: List of subreddits to target
            max_posts: Maximum posts to process in total
            limit_per_subreddit: Maximum posts per subreddit
            
        Returns:
            Dictionary with pipeline results
        """
        start_time = datetime.now()
        logger.info("=" * 60)
        logger.info("STARTING REDDIT DISTRIBUTOR PIPELINE")
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        logger.info(f"Target subreddits: {subreddits or TARGET_SUBREDDITS}")
        logger.info("=" * 60)
        
        try:
            # Initialize agents
            await self.initialize()
            
            # Phase 1: Scrape
            posts = await self.scrape_posts(
                subreddits=subreddits,
                limit=limit_per_subreddit,
            )
            
            if not posts:
                logger.warning("No posts scraped. Pipeline terminating.")
                return {
                    "status": "no_posts",
                    "posts_scraped": 0,
                    "comments_generated": 0,
                    "comments_published": 0,
                }
            
            # Limit posts if specified
            if max_posts:
                posts = posts[:max_posts]
            
            # Phase 2: Generate
            generated_results = await self.generate_comments(posts)
            
            # Phase 3: Publish
            if not self.dry_run:
                publishing_results = await self.publish_comments(
                    generated_results,
                    max_posts=max_posts,
                )
            else:
                # In dry run, just log what would be published
                successful = [
                    r for r in generated_results
                    if r["success"] and r.get("generated_comment")
                ]
                logger.info(f"[DRY RUN] Would publish {len(successful)} comments:")
                for r in successful[:5]:
                    logger.info(f"  - Post: {r['post_title'][:50]}...")
                    logger.info(f"    Comment: {r['generated_comment'][:100]}...")
                publishing_results = []
            
            # Update state
            state_manager.update_last_run()
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # Build results summary
            results = {
                "status": "completed",
                "mode": "dry_run" if self.dry_run else "live",
                "duration_seconds": duration,
                "posts_scraped": len(posts),
                "comments_generated": sum(1 for r in generated_results if r["success"]),
                "comments_published": len(publishing_results),
                "timestamp": end_time.isoformat(),
            }
            
            logger.info("=" * 60)
            logger.info("PIPELINE COMPLETED")
            logger.info(f"Posts scraped: {results['posts_scraped']}")
            logger.info(f"Comments generated: {results['comments_generated']}")
            logger.info(f"Comments published: {results['comments_published']}")
            logger.info(f"Duration: {duration:.1f} seconds")
            logger.info("=" * 60)
            
            return results
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            raise
    
    async def test_connection(self) -> bool:
        """
        Test connections to all services.
        
        Returns:
            True if all connections successful
        """
        logger.info("Testing connections...")
        
        try:
            # Test Reddit
            reddit_ok = self.reddit_scraper.test_connection()
            logger.info(f"Reddit connection: {'OK' if reddit_ok else 'FAILED'}")
            
            # Test is implicit for Gemini (client initialized)
            logger.info("Gemini connection: OK (client initialized)")
            
            return reddit_ok
            
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def print_generated_comments(self, filepath: str = None) -> None:
        """
        Print all generated comments from the JSON file.
        
        Args:
            filepath: Optional custom filepath
        """
        from config.settings import GENERATED_COMMENTS_FILE
        
        path = Path(filepath) if filepath else GENERATED_COMMENTS_FILE
        
        if not path.exists():
            logger.warning(f"No generated comments file found at {path}")
            return
        
        with open(path, "r", encoding="utf-8") as f:
            comments = json.load(f)
        
        logger.info(f"\n{'=' * 60}")
        logger.info(f"GENERATED COMMENTS ({len(comments)} total)")
        logger.info(f"{'=' * 60}")
        
        for i, comment in enumerate(comments, 1):
            status = "✓" if comment.get("success") else "✗"
            logger.info(f"\n{status} [{i}] Post: {comment.get('post_title', 'N/A')[:50]}...")
            logger.info(f"    Subreddit: r/{comment.get('post_subreddit', 'N/A')}")
            if comment.get("generated_comment"):
                logger.info(f"    Comment:\n{comment['generated_comment']}")
            else:
                logger.info(f"    Error: {comment.get('error', 'Generation failed')}")
        
        logger.info(f"\n{'=' * 60}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Reddit Distributor Agent - Multi-Agent Marketing System"
    )
    parser.add_argument(
        "--mode",
        choices=["run", "scrape", "generate", "test"],
        default="run",
        help="Execution mode (default: run full pipeline)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Dry run mode (don't post to Reddit)"
    )
    parser.add_argument(
        "--live",
        action="store_false",
        dest="dry_run",
        help="Live mode (actually post to Reddit)"
    )
    parser.add_argument(
        "--subreddits",
        nargs="+",
        help="Specific subreddits to target"
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        help="Maximum posts to process"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Posts limit per subreddit (default: 20)"
    )
    parser.add_argument(
        "--print-comments",
        action="store_true",
        help="Print previously generated comments"
    )
    
    args = parser.parse_args()
    
    # Initialize controller
    controller = RedditDistributorController(dry_run=args.dry_run)
    
    if args.print_comments:
        controller.print_generated_comments()
        return
    
    if args.mode == "test":
        await controller.initialize()
        success = await controller.test_connection()
        sys.exit(0 if success else 1)
    
    elif args.mode == "scrape":
        await controller.initialize()
        posts = await controller.scrape_posts(
            subreddits=args.subreddits,
            limit=args.limit,
        )
        print(json.dumps(posts, indent=2, default=str))
    
    elif args.mode == "generate":
        await controller.initialize()
        posts = await controller.scrape_posts(
            subreddits=args.subreddits,
            limit=args.limit,
        )
        results = await controller.generate_comments(posts)
        print(json.dumps(results, indent=2, default=str))
    
    elif args.mode == "run":
        results = await controller.run_full_pipeline(
            subreddits=args.subreddits,
            max_posts=args.max_posts,
            limit_per_subreddit=args.limit,
        )
        print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
