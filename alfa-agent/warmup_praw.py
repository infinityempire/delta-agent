#!/usr/bin/env python3
"""
Warmup PRAW Mode - Reddit Engagement via API (No Browser Required)
==================================================================
Uses PRAW (Python Reddit API Wrapper) directly.
No Playwright, no Chromium, no browser needed.
Works on any server including Render.com free tier.

Required environment variables:
- REDDIT_USERNAME
- REDDIT_PASSWORD
- REDDIT_CLIENT_ID
- REDDIT_CLIENT_SECRET

Optional:
- GEMINI_API_KEY (for AI-generated comments)
- COMMENTS_PER_RUN (default: 3)
"""
import os
import sys
import time
import random
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("warmup_praw")

# Casual warmup comments (no AI needed)
WARMUP_COMMENTS = [
    "Great point! I've been thinking about this too.",
    "This is really interesting, thanks for sharing!",
    "I can relate to this. Well said!",
    "Thanks for the insight, appreciate it!",
    "That's a fair take. Thanks for the perspective.",
    "Interesting! Never thought about it that way.",
    "Good observation. Thanks for bringing this up!",
    "I agree with this. Well explained!",
    "Nice one! Thanks for posting this.",
    "Very true! I've had similar experiences.",
    "This is helpful, thank you!",
    "Solid advice. Bookmarking this.",
    "Couldn't agree more with this.",
    "This resonates a lot, thanks for sharing.",
    "Really appreciate you taking the time to write this out.",
]

TARGET_SUBREDDITS = [
    "AskReddit",
    "funny",
    "todayilearned",
    "mildlyinteresting",
    "pics",
]


def get_reddit_client():
    """Create and return authenticated Reddit client."""
    try:
        import praw
    except ImportError:
        logger.error("PRAW not installed. Run: pip install praw")
        sys.exit(1)

    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    username = os.environ.get("REDDIT_USERNAME")
    password = os.environ.get("REDDIT_PASSWORD")
    user_agent = os.environ.get("REDDIT_USER_AGENT", f"warmup_bot:v1.0 (by u/{username})")

    if not all([client_id, client_secret, username, password]):
        logger.error("Missing required environment variables!")
        logger.error("Required: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD")
        sys.exit(1)

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        password=password,
        user_agent=user_agent,
    )

    # Verify authentication
    try:
        me = reddit.user.me()
        logger.info(f"Authenticated as: u/{me.name}")
        return reddit
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        sys.exit(1)


def run_warmup(reddit, subreddits=None, comments_per_run=3):
    """Post warmup comments to Reddit via API."""
    if subreddits is None:
        subreddits = TARGET_SUBREDDITS

    total_posted = 0
    total_failed = 0

    logger.info(f"Starting warmup on {len(subreddits)} subreddits, {comments_per_run} comments each")

    for subreddit_name in subreddits:
        logger.info(f"\n--- Processing r/{subreddit_name} ---")
        posted_in_sub = 0

        try:
            subreddit = reddit.subreddit(subreddit_name)
            posts = list(subreddit.hot(limit=25))
            random.shuffle(posts)

            for post in posts:
                if posted_in_sub >= comments_per_run:
                    break

                # Skip posts with locked comments or low engagement
                if post.locked or post.archived:
                    continue
                if post.num_comments < 5:
                    continue

                comment_text = random.choice(WARMUP_COMMENTS)

                try:
                    post.reply(comment_text)
                    posted_in_sub += 1
                    total_posted += 1
                    logger.info(f"  Posted comment on: '{post.title[:60]}...'")
                    logger.info(f"  Comment: '{comment_text}'")

                    # Human-like delay between comments (30-90 seconds)
                    if posted_in_sub < comments_per_run:
                        delay = random.randint(30, 90)
                        logger.info(f"  Waiting {delay}s before next comment...")
                        time.sleep(delay)

                except Exception as e:
                    logger.warning(f"  Failed to post comment: {e}")
                    total_failed += 1
                    time.sleep(10)
                    continue

        except Exception as e:
            logger.error(f"Error processing r/{subreddit_name}: {e}")
            continue

        # Delay between subreddits (2-5 minutes)
        if subreddit_name != subreddits[-1]:
            delay = random.randint(120, 300)
            logger.info(f"\nWaiting {delay}s before next subreddit...")
            time.sleep(delay)

    logger.info(f"\n{'='*50}")
    logger.info(f"Warmup complete!")
    logger.info(f"  Posted: {total_posted} comments")
    logger.info(f"  Failed: {total_failed} attempts")
    logger.info(f"{'='*50}")

    return {"posted": total_posted, "failed": total_failed}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Reddit Warmup via PRAW API")
    parser.add_argument("-c", "--comments", type=int,
                        default=int(os.environ.get("COMMENTS_PER_RUN", "3")),
                        help="Comments per subreddit (default: 3)")
    parser.add_argument("-s", "--subreddits", nargs="+",
                        default=TARGET_SUBREDDITS,
                        help="Subreddits to target")
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("Reddit Warmup - PRAW API Mode")
    logger.info("=" * 50)
    logger.info(f"Username: {os.environ.get('REDDIT_USERNAME', 'NOT SET')}")
    logger.info(f"Comments per subreddit: {args.comments}")
    logger.info(f"Subreddits: {', '.join(args.subreddits)}")
    logger.info("=" * 50)

    reddit = get_reddit_client()
    results = run_warmup(reddit, subreddits=args.subreddits, comments_per_run=args.comments)

    if results["posted"] == 0:
        logger.error("No comments posted!")
        sys.exit(1)


if __name__ == "__main__":
    main()
