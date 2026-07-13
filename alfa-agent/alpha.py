#!/usr/bin/env python3
"""
Alpha - Reddit Marketing & Distribution Agent Runner

Usage:
    python alpha.py                    # Run with defaults (dry-run)
    python alpha.py --live             # Run live (posts to Reddit)
    python alpha.py --status           # Check agent status
    python alpha.py --subreddits startups entrepreneur
"""
import asyncio
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

from agents.alpha import Alpha


async def main():
    """Run Alpha agent."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Alpha - Reddit Distribution Agent")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry run mode (default)")
    parser.add_argument("--live", action="store_false", dest="dry_run", help="Live mode - posts to Reddit")
    parser.add_argument("--subreddits", nargs="+", help="Target subreddits")
    parser.add_argument("--max-posts", type=int, help="Maximum posts to process")
    parser.add_argument("--limit", type=int, default=20, help="Posts per subreddit")
    parser.add_argument("--status", action="store_true", help="Show agent status")
    
    args = parser.parse_args()
    
    alpha = Alpha(dry_run=args.dry_run)
    
    if args.status:
        status = await alpha.status()
        print(f"\n🤖 Alpha Status")
        print(f"   Version: {status['version']}")
        print(f"   Initialized: {status['initialized']}")
        print(f"   Mode: {status['mode']}")
        print(f"   Posts Processed: {status['stats']['total_processed_posts']}")
        print(f"   Last Run: {status['stats']['last_run'] or 'Never'}")
        return
    
    # Run Alpha
    print(f"\n🚀 Starting Alpha v{alpha.version}...")
    
    results = await alpha.run(
        subreddits=args.subreddits,
        max_posts=args.max_posts,
        limit=args.limit,
    )
    
    print(f"\n📊 Alpha Results:")
    print(f"   Status: {results.get('status')}")
    print(f"   Mode: {results.get('mode')}")
    print(f"   Posts Scouted: {results.get('scouted', 0)}")
    print(f"   Comments Generated: {results.get('generated', 0)}")
    print(f"   Duration: {results.get('duration', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(main())
