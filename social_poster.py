"""
Social Media Poster - Multi-Platform Automated Distribution
Supports: Reddit, Bluesky, Mastodon, Lemmy, Tumblr, Telegram, Dev.to, Hashnode
"""

import os
import json
import time
import base64
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_IDS = os.environ.get("TELEGRAM_CHAT_IDS", "").split(",")

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME = os.environ.get("REDDIT_USERNAME", "")
REDDIT_PASSWORD = os.environ.get("REDDIT_PASSWORD", "")

BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "")
BLUESKY_PASSWORD = os.environ.get("BLUESKY_PASSWORD", "")

MASTODON_INSTANCE = os.environ.get("MASTODON_INSTANCE", "mastodon.social")
MASTODON_TOKEN = os.environ.get("MASTODON_TOKEN", "")

# Lemmy Configuration
LEMMY_INSTANCES = os.environ.get("LEMMY_INSTANCES", "lemmy.ml,beehaw.org").split(",")
LEMMY_TOKEN = os.environ.get("LEMMY_TOKEN", "")

# Tumblr Configuration
TUMBLR_API_KEY = os.environ.get("TUMBLR_API_KEY", "")
TUMBLR_API_SECRET = os.environ.get("TUMBLR_API_SECRET", "")
TUMBLR_BLOG_NAME = os.environ.get("TUMBLR_BLOG_NAME", "")

# Dev.to Configuration
DEV_TO_API_KEY = os.environ.get("DEV_TO_API_KEY", "")

# Hashnode Configuration
HASHNODE_TOKEN = os.environ.get("HASHNODE_TOKEN", "")
HASHNODE_PUBLICATION_ID = os.environ.get("HASHNODE_PUBLICATION_ID", "")

# ── Output ────────────────────────────────────────────────────────────────────
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def log_result(platform, success, message):
    """Log posting results"""
    status = "✅" if success else "❌"
    print(f"{status} [{platform}] {message}")
    
    # Save to log file
    log_file = f"{OUTPUT_DIR}/social_posts_{datetime.now().strftime('%Y%m%d')}.json"
    logs = []
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            logs = json.load(f)
    
    logs.append({
        "timestamp": datetime.now().isoformat(),
        "platform": platform,
        "success": success,
        "message": message
    })
    
    with open(log_file, 'w') as f:
        json.dump(logs, f, indent=2)

# ── Telegram Posting ───────────────────────────────────────────────────────────
def post_to_telegram(message, chat_id=None):
    """Post message to Telegram bot/chat"""
    if not TELEGRAM_BOT_TOKEN:
        log_result("Telegram", False, "No bot token configured")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    targets = [chat_id] if chat_id else [c.strip() for c in TELEGRAM_CHAT_IDS if c.strip()]
    
    success_count = 0
    for target in targets:
        try:
            payload = {
                "chat_id": target,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                success_count += 1
            else:
                print(f"  Telegram error to {target}: {response.text[:100]}")
        except Exception as e:
            print(f"  Telegram exception: {e}")
    
    log_result("Telegram", success_count > 0, f"Posted to {success_count}/{len(targets)} chats")
    return success_count > 0

# ── Reddit Posting ─────────────────────────────────────────────────────────────
def get_reddit_token():
    """Get Reddit API access token"""
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]):
        return None
    
    try:
        auth = requests.auth.HTTPBasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
        data = {
            "grant_type": "password",
            "username": REDDIT_USERNAME,
            "password": REDDIT_PASSWORD
        }
        headers = {"User-Agent": "DeltaAgent/1.0 SocialPoster"}
        response = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=auth, data=data, headers=headers, timeout=30
        )
        
        if response.status_code == 200:
            return response.json().get("access_token")
    except Exception as e:
        print(f"  Reddit auth error: {e}")
    return None

def post_to_reddit(subreddit, title, content):
    """Post to a subreddit"""
    token = get_reddit_token()
    if not token:
        log_result("Reddit", False, "No Reddit credentials or auth failed")
        return False
    
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "DeltaAgent/1.0 SocialPoster",
            "Content-Type": "application/json"
        }
        
        # Submit post
        payload = {
            "sr": subreddit,
            "kind": "self",
            "title": title,
            "text": content
        }
        
        response = requests.post(
            "https://oauth.reddit.com/api/submit",
            headers=headers, json=payload, timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("json", {}).get("errors"):
                errors = result["json"]["errors"]
                log_result("Reddit", False, f"Post errors: {errors}")
            else:
                permalink = result.get("json", {}).get("data", {}).get("permalink", "")
                log_result("Reddit", True, f"Posted to r/{subreddit}: {permalink}")
                return True
        else:
            log_result("Reddit", False, f"HTTP {response.status_code}: {response.text[:100]}")
    except Exception as e:
        log_result("Reddit", False, str(e))
    
    return False

# ── Bluesky Posting ────────────────────────────────────────────────────────────
def post_to_bluesky(text, image_path=None):
    """Post to Bluesky (AT Protocol)"""
    if not all([BLUESKY_HANDLE, BLUESKY_PASSWORD]):
        log_result("Bluesky", False, "No Bluesky credentials")
        return False
    
    try:
        # Authenticate
        auth_url = "https://bsky.social/xrpc/com.atproto.server.createSession"
        auth_data = {"identifier": BLUESKY_HANDLE, "password": BLUESKY_PASSWORD}
        
        auth_response = requests.post(auth_url, json=auth_data, timeout=30)
        if auth_response.status_code != 200:
            log_result("Bluesky", False, f"Auth failed: {auth_response.text[:100]}")
            return False
        
        session = auth_response.json()
        access_token = session.get("accessJwt")
        did = session.get("did")
        
        # Create post
        post_url = "https://bsky.social/xrpc/com.atproto.server.createSession"
        
        # For now, simple text post (image upload requires additional steps)
        post_data = {
            "collection": "app.bsky.feed.post",
            "repo": did,
            "record": {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": datetime.utcnow().isoformat() + "Z"
            }
        }
        
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.post(post_url.replace("createSession", "createRecord"), 
                                json=post_data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            uri = response.json().get("uri", "")
            log_result("Bluesky", True, f"Posted: {uri}")
            return True
        else:
            log_result("Bluesky", False, f"Post failed: {response.text[:100]}")
    except Exception as e:
        log_result("Bluesky", False, str(e))
    
    return False

# ── Mastodon Posting ──────────────────────────────────────────────────────────
def post_to_mastodon(text, visibility="public", instance=None):
    """Post to Mastodon instance"""
    if not MASTODON_TOKEN:
        log_result("Mastodon", False, "No Mastodon token")
        return False
    
    instance = instance or MASTODON_INSTANCE
    try:
        url = f"https://{instance}/api/v1/statuses"
        headers = {
            "Authorization": f"Bearer {MASTODON_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "status": text,
            "visibility": visibility  # public, unlisted, private, direct
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code in [200, 201]:
            result = response.json()
            log_result(f"Mastodon ({instance})", True, f"Posted: {result.get('url', '')}")
            return True
        else:
            log_result(f"Mastodon ({instance})", False, f"HTTP {response.status_code}: {response.text[:100]}")
    except Exception as e:
        log_result(f"Mastodon ({instance})", False, str(e))
    
    return False

# ── Lemmy Posting ─────────────────────────────────────────────────────────────
def post_to_lemmy(community, text, instance=None):
    """Post to Lemmy instance"""
    if not LEMMY_TOKEN:
        log_result("Lemmy", False, "No Lemmy token")
        return False
    
    instance = instance or "lemmy.ml"
    try:
        # Lemmy post format: community@instance
        if "@" not in community:
            community = f"{community}@{instance}"
        
        url = f"https://{instance}/api/v3/post"
        headers = {
            "Authorization": f"Bearer {LEMMY_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "name": text[:300],  # Lemmy title limit
            "body": text,
            "community_id": 0,  # Would need to resolve community first
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            log_result(f"Lemmy ({instance})", True, f"Posted to {community}")
            return True
        else:
            log_result(f"Lemmy ({instance})", False, f"HTTP {response.status_code}")
    except Exception as e:
        log_result(f"Lemmy ({instance})", False, str(e))
    
    return False

# ── Tumblr Posting ───────────────────────────────────────────────────────────
def post_to_tumblr(text, tags=None):
    """Post to Tumblr blog"""
    if not all([TUMBLR_API_KEY, TUMBLR_BLOG_NAME]):
        log_result("Tumblr", False, "Missing Tumblr credentials")
        return False
    
    try:
        url = f"https://api.tumblr.com/v2/blog/{TUMBLR_BLOG_NAME}/post"
        headers = {"Content-Type": "application/json"}
        data = {
            "content": text,
            "tags": tags or ["ai", "productivity", "telegram", "bot"],
            "format": "html"
        }
        
        # Tumblr uses OAuth 1.0 - simplified for demo
        # Full implementation would need oauth1 library
        log_result("Tumblr", False, "OAuth 1.0 required - needs full implementation")
    except Exception as e:
        log_result("Tumblr", False, str(e))
    
    return False

# ── Dev.to Posting ────────────────────────────────────────────────────────────
def post_to_devto(title, content, tags=None, canonical_url=None):
    """Post article to Dev.to"""
    if not DEV_TO_API_KEY:
        log_result("Dev.to", False, "No Dev.to API key")
        return False
    
    try:
        url = "https://dev.to/api/articles"
        headers = {
            "Authorization": DEV_TO_API_KEY,
            "Content-Type": "application/json"
        }
        data = {
            "title": title,
            "body_markdown": content,
            "tags": tags or ["ai", "productivity", "telegram"],
            "published": True
        }
        if canonical_url:
            data["canonical_url"] = canonical_url
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code in [200, 201]:
            result = response.json()
            log_result("Dev.to", True, f"Published: {result.get('url', '')}")
            return True
        else:
            log_result("Dev.to", False, f"HTTP {response.status_code}: {response.text[:100]}")
    except Exception as e:
        log_result("Dev.to", False, str(e))
    
    return False

# ── Hashnode Posting ───────────────────────────────────────────────────────────
def post_to_hashnode(title, content, tags=None, cover_image_url=None):
    """Post article to Hashnode"""
    if not HASHNODE_TOKEN:
        log_result("Hashnode", False, "No Hashnode token")
        return False
    
    try:
        url = "https://gql.hashnode.com"
        headers = {
            "Authorization": HASHNODE_TOKEN,
            "Content-Type": "application/json"
        }
        query = """
        mutation CreatePublicationStory($input: CreateStoryInput!) {
            publicationStory(input: $input) {
                success
                post {
                    slug
                    url
                }
            }
        }
        """
        data = {
            "query": query,
            "variables": {
                "input": {
                    "title": title,
                    "content": content,
                    "tags": tags or [{"name": "AI"}, {"name": "Productivity"}],
                    "publicationId": HASHNODE_PUBLICATION_ID
                }
            }
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("data", {}).get("publicationStory", {}).get("success"):
                url = result["data"]["publicationStory"]["post"]["url"]
                log_result("Hashnode", True, f"Published: {url}")
                return True
        
        log_result("Hashnode", False, f"Failed: {response.text[:100]}")
    except Exception as e:
        log_result("Hashnode", False, str(e))
    
    return False

# ── Bulk Posting ──────────────────────────────────────────────────────────────
def distribute_content(platforms=None):
    """Distribute marketing content to all configured platforms"""
    
    # Hebrew post (for Israeli audiences)
    hebrew_post = """נמאס לכם מהודעות קוליות של 5 דקות? 🤯

בניתי בוט שעושה את זה:
🎙️ שולחים הודעה קולית
⚡ מקבלים טקסט תוך שניות
🇮🇱 כחול-לבן וחינמי בהתחלה

נסו עכשיו: @replyq1_bot 🚀"""

    # English post (for international audiences)
    english_post = """Tired of 5-minute voice messages? 🤯

I built a bot that does this:
🎙️ Send a voice message
⚡ Get text in seconds
🇮🇱 Made in Israel, free to start

Try it now: @replyq1_bot 🚀

#AI #Productivity #Telegram #VoiceToText"""

    # Full article for blog platforms
    full_article = """# I Built an AI Bot That Transcribes Voice Messages in 2 Seconds 🇮🇱

**The Problem:** In Israeli culture (and many others), sending long voice messages (5-10 minutes!) is extremely common. It's more personal than text, but incredibly time-consuming to listen to.

**The Solution:** I built zeta ai, a Telegram bot that uses Google's AI to transcribe any voice message instantly.

## Features

- ⚡ Sub-2-second transcription
- 🧠 AI-powered accuracy  
- 👥 Works in groups - auto-transcribes all voice messages
- 🌍 Multi-language support
- 🇮🇱 Made with love in Israel

## How It Works

1. Open the bot: @replyq1_bot
2. Forward any voice message
3. Get accurate text instantly!

## The Viral Loop

The best part? Add it to Telegram groups, and it auto-transcribes every voice message. Everyone in the group sees the magic and wants it for themselves!

## Try It Free

The service is free for the first 5 transcriptions. Start saving time now: @replyq1_bot 🚀

#AI #VoiceToText #Productivity #Telegram #Israel #Startup"""

    results = {}
    
    if not platforms or "telegram" in platforms:
        print("\n[📱] Posting to Telegram...")
        results["telegram"] = post_to_telegram(hebrew_post)
        time.sleep(2)
    
    if not platforms or "reddit" in platforms:
        print("\n[📺] Posting to Reddit...")
        subreddits = ["startups", "entrepreneur", "SideProject", "technology", "android", "iOS"]
        for sub in subreddits:
            post_to_reddit(sub, english_post[:300], english_post)
            time.sleep(10)  # Rate limiting
    
    if not platforms or "bluesky" in platforms:
        print("\n[🌀] Posting to Bluesky...")
        results["bluesky"] = post_to_bluesky(english_post)
        time.sleep(2)
    
    if not platforms or "mastodon" in platforms:
        print("\n[🐘] Posting to Mastodon...")
        # Post to multiple instances
        instances = ["mastodon.social", "fosstodon.org", "hachyderm.io"]
        for instance in instances:
            results[f"mastodon_{instance}"] = post_to_mastodon(english_post, instance=instance)
            time.sleep(2)
    
    if not platforms or "lemmy" in platforms:
        print("\n[🦎] Posting to Lemmy...")
        communities = ["technology", "programming", "artificial"]
        for instance in LEMMY_INSTANCES:
            for community in communities:
                post_to_lemmy(community, english_post[:300], instance=instance)
                time.sleep(3)
    
    if not platforms or "devto" in platforms:
        print("\n[� DEV] Posting to Dev.to...")
        results["devto"] = post_to_devto(
            "I Built an AI Bot That Transcribes Voice Messages in 2 Seconds 🇮🇱",
            full_article,
            tags=["ai", "productivity", "telegram", "python", "voice"]
        )
        time.sleep(2)
    
    if not platforms or "hashnode" in platforms:
        print("\n[📝] Posting to Hashnode...")
        results["hashnode"] = post_to_hashnode(
            "I Built an AI Bot That Transcribes Voice Messages in 2 Seconds 🇮🇱",
            full_article,
            tags=[{"name": "AI"}, {"name": "Productivity"}, {"name": "Telegram"}]
        )
        time.sleep(2)
    
    return results

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    
    platforms = None
    if len(sys.argv) > 1:
        platforms = [p.strip().lower() for p in sys.argv[1].split(",")]
    
    print("=" * 60)
    print("DELTA AGENT - Social Media Distributor")
    print(f"Platforms: {platforms or 'ALL'}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 60)
    
    results = distribute_content(platforms)
    
    print("\n" + "=" * 60)
    print("DISTRIBUTION COMPLETE")
    success_count = sum(1 for v in results.values() if v)
    print(f"Success: {success_count}/{len(results)} platforms")
    print("=" * 60)
