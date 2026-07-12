"""
Social Media Poster - Multi-Platform Automated Distribution
Supports: Reddit, Bluesky, Mastodon, Telegram
"""

import os
import json
import time
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
def post_to_mastodon(text, visibility="public"):
    """Post to Mastodon instance"""
    if not MASTODON_TOKEN:
        log_result("Mastodon", False, "No Mastodon token")
        return False
    
    try:
        url = f"https://{MASTODON_INSTANCE}/api/v1/statuses"
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
            log_result("Mastodon", True, f"Posted: {result.get('url', '')}")
            return True
        else:
            log_result("Mastodon", False, f"HTTP {response.status_code}: {response.text[:100]}")
    except Exception as e:
        log_result("Mastodon", False, str(e))
    
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

#AI #Productivity #Telegram"""

    # Reddit versions
    reddit_title_he = "🎙️ I built an AI bot that transcribes voice messages in 2 seconds (Made in Israel 🇮🇱)"
    reddit_title_en = "I built a Telegram bot that auto-transcribes voice messages - it's going viral in Israel"
    
    results = {}
    
    if not platforms or "telegram" in platforms:
        print("\n[📱] Posting to Telegram...")
        results["telegram"] = post_to_telegram(hebrew_post)
        time.sleep(2)
    
    if not platforms or "reddit" in platforms:
        print("\n[📺] Posting to Reddit...")
        # Post to multiple subreddits
        subreddits = ["startups", "entrepreneur", "SideProject", "technology"]
        for sub in subreddits:
            post_to_reddit(sub, reddit_title_en, english_post)
            time.sleep(10)  # Rate limiting
    
    if not platforms or "bluesky" in platforms:
        print("\n[🌀] Posting to Bluesky...")
        results["bluesky"] = post_to_bluesky(english_post)
        time.sleep(2)
    
    if not platforms or "mastodon" in platforms:
        print("\n[🐘] Posting to Mastodon...")
        results["mastodon"] = post_to_mastodon(english_post)
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
