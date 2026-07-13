#!/usr/bin/env python3
"""
Zeta Warmup v2 — Organic Channels Edition
=========================================

Refactored to support organic channels (HACKERNEWS, etc.) without Reddit dependencies.
All DRY_RUN flags are set to FALSE for live execution.

Channels:
- HACKERNEWS: Fetch and process top stories from Hacker News
"""
import time
import random
from datetime import datetime

# Configuration
DRY_RUN = False  # Live mode - executes directly

ITEMS_PER_RUN = 10


def log(msg: str) -> None:
    """Log a message with timestamp."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch_hackernews_topstories(limit: int = 10) -> list:
    """Fetch top stories from Hacker News."""
    import requests
    
    try:
        # Get top story IDs
        r = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=15
        )
        if r.status_code != 200:
            log(f"⚠️ HN API error: HTTP {r.status_code}")
            return []
        
        story_ids = r.json()[:limit]
        
        stories = []
        for story_id in story_ids:
            try:
                story_r = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                    timeout=10
                )
                if story_r.status_code == 200:
                    story = story_r.json()
                    if story and story.get("title"):
                        stories.append({
                            "id": story_id,
                            "title": story.get("title", ""),
                            "url": story.get("url", ""),
                            "score": story.get("score", 0),
                            "by": story.get("by", ""),
                            "descendants": story.get("descendants", 0),
                        })
                time.sleep(0.1)  # Rate limiting
            except Exception as e:
                log(f"⚠️ Error fetching story {story_id}: {e}")
                continue
        
        return stories
        
    except Exception as e:
        log(f"⚠️ fetch_hackernews_topstories error: {e}")
        return []


def process_channel(channel_name: str, fetch_func, limit: int = 10) -> dict:
    """
    Process a channel and return results.
    
    Args:
        channel_name: Name of the channel
        fetch_func: Function to fetch items from the channel
        limit: Maximum items to process
        
    Returns:
        dict with processed results
    """
    log(f"\n📌 Channel: {channel_name}...")
    
    items = fetch_func(limit=limit)
    if not items:
        log(f"   No items found")
        return {"channel": channel_name, "processed": 0, "items": []}
    
    log(f"   {len(items)} items found")
    
    results = {
        "channel": channel_name,
        "processed": len(items),
        "items": []
    }
    
    for item in items:
        if DRY_RUN:
            log(f"   [DRY RUN] Would process: {item.get('title', 'N/A')[:50]}...")
        else:
            log(f"   📰 Processing: {item.get('title', 'N/A')[:50]}...")
            # Process item here (e.g., analysis, summarization, etc.)
            results["items"].append(item)
        
        time.sleep(random.uniform(0.5, 1.5))
    
    return results


def main():
    """Main execution function."""
    print()
    print("=" * 60)
    print("  Zeta Warmup v2 — Organic Channels Edition")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
    print("=" * 60)
    print()
    
    # Define organic channels
    channels = [
        {
            "name": "HACKERNEWS",
            "fetch": fetch_hackernews_topstories,
            "limit": ITEMS_PER_RUN,
        },
    ]
    
    # Process each channel
    total_processed = 0
    channels_visited = []
    
    for channel in channels:
        result = process_channel(
            channel["name"],
            channel["fetch"],
            limit=channel.get("limit", ITEMS_PER_RUN)
        )
        
        total_processed += result["processed"]
        if result["processed"] > 0:
            channels_visited.append(channel["name"])
        
        time.sleep(random.uniform(2, 5))
    
    print()
    print("=" * 60)
    print("  ✅ Warmup Complete!")
    print(f"  Channels visited:  {len(channels_visited)}")
    print(f"  Items processed:   {total_processed}")
    print(f"  Mode:              {'DRY RUN' if DRY_RUN else 'LIVE'}")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
