#!/usr/bin/env python3
"""
Zeta - Reddit Marketing & Distribution Agent Runner

Usage:
    python zeta.py                    # Run with defaults (dry-run)
    python zeta.py --live             # Run live (posts to Reddit)
    python zeta.py --status           # Check agent status
    python zeta.py --subreddits startups entrepreneur
"""
import asyncio
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

from agents.zeta import Zeta


async def main():
    """Run Zeta agent."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Zeta - Reddit Distribution Agent")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry run mode (default)")
    parser.add_argument("--live", action="store_false", dest="dry_run", help="Live mode - posts to Reddit")
    parser.add_argument("--subreddits", nargs="+", help="Target subreddits")
    parser.add_argument("--max-posts", type=int, help="Maximum posts to process")
    parser.add_argument("--limit", type=int, default=20, help="Posts per subreddit")
    parser.add_argument("--status", action="store_true", help="Show agent status")
    
    args = parser.parse_args()
    
    zeta = Zeta(dry_run=args.dry_run)
    
    if args.status:
        status = await zeta.status()
        print(f"\n🤖 Zeta Status")
        print(f"   Version: {status['version']}")
        print(f"   Initialized: {status['initialized']}")
        print(f"   Mode: {status['mode']}")
        print(f"   Posts Processed: {status['stats']['total_processed_posts']}")
        print(f"   Last Run: {status['stats']['last_run'] or 'Never'}")
        return
    
    # Run Zeta
    print(f"\n🚀 Starting Zeta v{zeta.version}...")
    
    results = await zeta.run(
        subreddits=args.subreddits,
        max_posts=args.max_posts,
        limit=args.limit,
    )
    
    print(f"\n📊 Zeta Results:")
    print(f"   Status: {results.get('status')}")
    print(f"   Mode: {results.get('mode')}")
    print(f"   Posts Scouted: {results.get('scouted', 0)}")
    print(f"   Comments Generated: {results.get('generated', 0)}")
    print(f"   Duration: {results.get('duration', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(main())
