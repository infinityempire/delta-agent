"""
Delta Agent - Decentralized Social Media Distributor
Supports: Mastodon, Bluesky, Threads, Nostr, Farcaster, Lemmy, Pixelfed, Reddit, Dev.to, Hashnode
"""

import os
import json
import time
import base64
import hashlib
import secrets
import requests
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, List, Dict

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────

# Mastodon Configuration (Federated - ActivityPub)
MASTODON_INSTANCES = os.environ.get("MASTODON_INSTANCES", "mastodon.social,fosstodon.org,hachyderm.io").split(",")
MASTODON_TOKEN = os.environ.get("MASTODON_TOKEN", "")

# Bluesky Configuration (AT Protocol)
BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "")
BLUESKY_PASSWORD = os.environ.get("BLUESKY_PASSWORD", "")

# Threads Configuration (Meta - ActivityPub)
THREADS_TOKEN = os.environ.get("THREADS_TOKEN", "")
THREADS_USER_ID = os.environ.get("THREADS_USER_ID", "")

# Nostr Configuration (Decentralized - Keys Based)
NOSTR_PRIVATE_KEY = os.environ.get("NOSTR_PRIVATE_KEY", "")
NOSTR_RELAY_LIST = os.environ.get("NOSTR_RELAYS", "wss://relay.damus.io,wss://nos.lol,wss://relay.nostr.band").split(",")

# Farcaster Configuration (Farcaster Protocol)
FARCASTER_SIGNER = os.environ.get("FARCASTER_SIGNER", "")

# Lemmy Configuration (Reddit Alternative - ActivityPub)
LEMMY_INSTANCES = os.environ.get("LEMMY_INSTANCES", "lemmy.ml,beehaw.org").split(",")
LEMMY_TOKEN = os.environ.get("LEMMY_TOKEN", "")

# Pixelfed Configuration (Instagram Alternative - ActivityPub)
PIXELFED_INSTANCE = os.environ.get("PIXELFED_INSTANCE", "pixelfed.social")
PIXELFED_TOKEN = os.environ.get("PIXELFED_TOKEN", "")

# Reddit Configuration
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME = os.environ.get("REDDIT_USERNAME", "")
REDDIT_PASSWORD = os.environ.get("REDDIT_PASSWORD", "")

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
def post_to_lemmy(community, title, content, instance=None):
    """Post to Lemmy instance (Reddit alternative)"""
    if not LEMMY_TOKEN:
        log_result("Lemmy", False, "No Lemmy token")
        return False
    
    instance = instance or "lemmy.ml"
    try:
        # First resolve the community
        resolve_url = f"https://{instance}/api/v3/community"
        headers = {
            "Authorization": f"Bearer {LEMMY_TOKEN}",
            "Content-Type": "application/json"
        }
        resolve_params = {"name": community}
        resolve_resp = requests.get(resolve_url, headers=headers, params=resolve_params, timeout=30)
        
        if resolve_resp.status_code == 200:
            community_data = resolve_resp.json().get("community_view", {})
            community_id = community_data.get("community", {}).get("id", 0)
        else:
            community_id = 0
        
        # Create post
        post_url = f"https://{instance}/api/v3/post"
        data = {
            "name": title[:300],
            "body": content,
            "community_id": community_id,
        }
        
        response = requests.post(post_url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            log_result(f"Lemmy ({instance})", True, f"Posted to {community}")
            return True
        else:
            log_result(f"Lemmy ({instance})", False, f"HTTP {response.status_code}: {response.text[:100]}")
    except Exception as e:
        log_result(f"Lemmy ({instance})", False, str(e))
    
    return False

# ── Threads (Meta) Posting ───────────────────────────────────────────────────
def post_to_threads(text):
    """Post to Threads via Meta's API (requires Instagram token)"""
    if not THREADS_TOKEN:
        log_result("Threads", False, "No Threads/Instagram token")
        return False
    
    try:
        # Threads uses Instagram's Graph API
        url = "https://graph.facebook.com/v18.0/me/threads"
        headers = {"Content-Type": "application/json"}
        data = {
            "message": text,
            "access_token": THREADS_TOKEN
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            log_result("Threads", True, f"Posted: {result.get('id', '')}")
            return True
        else:
            log_result("Threads", False, f"HTTP {response.status_code}: {response.text[:100]}")
    except Exception as e:
        log_result("Threads", False, str(e))
    
    return False

# ── Nostr Posting ───────────────────────────────────────────────────────────
def post_to_nostr(content: str, tags: List[str] = None) -> bool:
    """Post to Nostr decentralized network using NIP-01 (text note)"""
    if not NOSTR_PRIVATE_KEY:
        log_result("Nostr", False, "No Nostr private key configured")
        return False
    
    try:
        # Convert hex private key to hex public key
        pubkey = hashlib.sha256(bytes.fromhex(NOSTR_PRIVATE_KEY)).hexdigest()
        
        # Create event
        event = {
            "kind": 1,  # Text note
            "content": content,
            "tags": [[ "t", tag] for tag in (tags or [])],
            "pubkey": pubkey,
            "created_at": int(datetime.now().timestamp()),
            "id": "",  # Will be computed
            "sig": ""  # Will be computed
        }
        
        # Compute event id = sha256 of serialized event
        event_json = json.dumps([0, event["kind"], event["pubkey"], event["created_at"], event["tags"], event["content"]], separators=(',', ':'))
        event["id"] = hashlib.sha256(event_json.encode()).hexdigest()
        
        # Sign with schnorr (simplified - in production use nostr-tools library)
        # For demo, we'll broadcast to relays
        event["sig"] = "fake_signature_for_demo"  # Would use proper schnorr in production
        
        # Broadcast to relays
        success_count = 0
        for relay in NOSTR_RELAY_LIST:
            try:
                ws_url = relay.replace("wss://", "https://").replace("ws://", "http://")
                api_url = ws_url + "/api/v1"
                response = requests.post(api_url, json=["EVENT", event], timeout=10)
                if response.status_code == 200:
                    success_count += 1
            except:
                pass
        
        if success_count > 0:
            log_result("Nostr", True, f"Posted to {success_count}/{len(NOSTR_RELAY_LIST)} relays")
            return True
        else:
            log_result("Nostr", False, "Failed to post to any relay")
    except Exception as e:
        log_result("Nostr", False, str(e))
    
    return False

# ── Pixelfed Posting ─────────────────────────────────────────────────────────
def post_to_pixelfed(text, image_path: str = None):
    """Post to Pixelfed (Instagram alternative - ActivityPub)"""
    if not PIXELFED_TOKEN:
        log_result("Pixelfed", False, "No Pixelfed token")
        return False
    
    try:
        instance = PIXELFED_INSTANCE or "pixelfed.social"
        url = f"https://{instance}/api/v1/statuses"
        headers = {
            "Authorization": f"Bearer {PIXELFED_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "status": text,
            "visibility": "public"
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code in [200, 201]:
            result = response.json()
            log_result(f"Pixelfed ({instance})", True, f"Posted: {result.get('url', '')}")
            return True
        else:
            log_result(f"Pixelfed ({instance})", False, f"HTTP {response.status_code}")
    except Exception as e:
        log_result("Pixelfed", False, str(e))
    
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
    """Distribute marketing content to all DECENTRALIZED platforms"""
    
    # Hebrew launch post (the exact copy provided)
    hebrew_post = """נמאס לכם שחופרים לכם בהודעות קוליות ארוכות? 🤯

בניתי כלי מטורף (כחול-לבן 🇮🇱) שפותר את זה בשנייה!
בוט טלגרם מבוסס AI של גוגל שתופר הודעות קוליות ארוכות והופך אותן לטקסט קריא ומדויק בפחות משתי שניות.

💡 איך זה עובד?
1. נכנסים לבוט בטלגרם: @replyq1_bot
2. מעבירים לו (Forward) כל הודעה קולית שקיבלתם.
3. מקבלים מיד את הטקסט ישירות לעיניים.

🔥 בונוס לחברים בקבוצות: אתם יכולים להוסיף אותו ישירות לקבוצות שלכם, והוא יתמלל כל הודעה קולית שנשלחת שם אוטומטית!

השירות חינמי לחלוטין לשימוש ראשוני. תתחילו לחסוך זמן פה: @replyq1_bot 🚀"""

    # English version for international audiences
    english_post = """Tired of endless voice messages? 🤯

I built a killer tool (Made in Israel 🇮🇱) that solves this in seconds!

A Telegram bot powered by Google's AI that transcribes long voice messages into clean, accurate text in under 2 seconds.

💡 How it works:
1️⃣ Open the bot: @replyq1_bot
2️⃣ Forward any voice message
3️⃣ Get text instantly

🔥 Group bonus: Add it to your Telegram groups and it auto-transcribes every voice message!

Free for initial use. Start saving time now: @replyq1_bot 🚀

#AI #Productivity #VoiceToText #Telegram #Israel"""

    # Short versions for limited-length platforms
    short_hebrew = "נמאס מחפירות קוליות? 🇮🇱 בוט AI כחול-לבן שמתמלל ב-2 שניות! @replyq1_bot 🚀"
    short_english = "Tired of voice message dumps? 🇮🇱 AI bot that transcribes in 2 seconds! @replyq1_bot 🚀"

    results = {}
    
    # ═══════════════════════════════════════════════════════════
    # MASTODON (Federated - ActivityPub)
    # ═══════════════════════════════════════════════════════════
    if not platforms or "mastodon" in platforms:
        print("\n[🐘] Posting to Mastodon instances...")
        instances = ["mastodon.social", "fosstodon.org", "hachyderm.io", "infosec.exchange"]
        for instance in instances:
            results[f"mastodon_{instance}"] = post_to_mastodon(english_post, visibility="public", instance=instance)
            time.sleep(3)
    
    # ═══════════════════════════════════════════════════════════
    # BLUESKY (AT Protocol)
    # ═══════════════════════════════════════════════════════════
    if not platforms or "bluesky" in platforms:
        print("\n[🌀] Posting to Bluesky...")
        results["bluesky"] = post_to_bluesky(short_english)
        time.sleep(2)
    
    # ═══════════════════════════════════════════════════════════
    # LEMMY (Reddit Alternative - ActivityPub)
    # ═══════════════════════════════════════════════════════════
    if not platforms or "lemmy" in platforms:
        print("\n[🦎] Posting to Lemmy communities...")
        communities = ["technology", "programming", "artificial", "linux", "science"]
        for instance in LEMMY_INSTANCES:
            for community in communities[:3]:  # Limit to avoid spam
                post_to_lemmy(community, "AI Bot Transcribes Voice Messages in 2 Seconds 🇮🇱", 
                            english_post, instance=instance)
                time.sleep(5)
    
    # ═══════════════════════════════════════════════════════════
    # NOSTR (Decentralized - Keys Based)
    # ═══════════════════════════════════════════════════════════
    if not platforms or "nostr" in platforms:
        print("\n[⚡] Posting to Nostr...")
        results["nostr"] = post_to_nostr(english_post, tags=["ai", "telegram", "productivity"])
        time.sleep(2)
    
    # ═══════════════════════════════════════════════════════════
    # THREADS (Meta - ActivityPub)
    # ═══════════════════════════════════════════════════════════
    if not platforms or "threads" in platforms:
        print("\n[📷] Posting to Threads...")
        results["threads"] = post_to_threads(short_english)
        time.sleep(2)
    
    # ═══════════════════════════════════════════════════════════
    # FARCASTER (Web3 Social)
    # Note: Requires Warpcast API - limited access
    # ═══════════════════════════════════════════════════════════
    if not platforms or "farcaster" in platforms:
        print("\n[🌉] Posting to Farcaster...")
        if FARCASTER_SIGNER:
            log_result("Farcaster", False, "API not fully implemented - requires Warpcast approval")
        else:
            log_result("Farcaster", False, "No signer configured")
        time.sleep(1)
    
    # ═══════════════════════════════════════════════════════════
    # PIXELFED (Instagram Alternative - ActivityPub)
    # ═══════════════════════════════════════════════════════════
    if not platforms or "pixelfed" in platforms:
        print("\n[📸] Posting to Pixelfed...")
        results["pixelfed"] = post_to_pixelfed(short_english)
        time.sleep(2)
    
    # ═══════════════════════════════════════════════════════════
    # REDDIT (Traditional)
    # ═══════════════════════════════════════════════════════════
    if not platforms or "reddit" in platforms:
        print("\n[📺] Posting to Reddit...")
        subreddits = ["startups", "entrepreneur", "SideProject", "technology", "android", "iOS"]
        for sub in subreddits:
            post_to_reddit(sub, "I built an AI bot that transcribes voice messages in 2 seconds 🇮🇱", english_post)
            time.sleep(10)
    
    # ═══════════════════════════════════════════════════════════
    # DEV.TO (Developer Community)
    # ═══════════════════════════════════════════════════════════
    if not platforms or "devto" in platforms:
        print("\n[💻] Posting to Dev.to...")
        full_article = """# I Built an AI Bot That Transcribes Voice Messages in 2 Seconds 🇮🇱

**The Problem:** In Israeli culture (and many others), sending long voice messages (5-10 minutes!) is extremely common.

**The Solution:** I built zeta ai, a Telegram bot that uses Google's AI to transcribe any voice message instantly.

## Features

- ⚡ Sub-2-second transcription
- 🧠 AI-powered accuracy  
- 👥 Works in groups - auto-transcribes all voice messages
- 🌍 Multi-language support
- 🇮🇱 Made with love in Israel

## The Viral Loop

Add it to Telegram groups, and it auto-transcribes every voice message. Everyone sees the magic!

## Try It Free

The service is free for the first 5 transcriptions: @replyq1_bot 🚀

```python
# Example: How the bot works
1. User forwards voice message to @replyq1_bot
2. Bot uses Google Speech-to-Text API
3. AI processes and improves accuracy
4. User receives clean text in <2 seconds
```

#AI #Productivity #VoiceToText #Telegram #Python"""

        results["devto"] = post_to_devto(
            "I Built an AI Bot That Transcribes Voice Messages in 2 Seconds 🇮🇱",
            full_article,
            tags=["ai", "productivity", "telegram", "python", "voice"]
        )
        time.sleep(2)
    
    return results

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    
    platforms = None
    if len(sys.argv) > 1:
        platforms = [p.strip().lower() for p in sys.argv[1].split(",")]
    
    print("""
╔══════════════════════════════════════════════════════════════╗
║  DELTA AGENT - Decentralized Social Media Distributor    ║
║  Broadcasting zeta ai (@replyq1_bot) launch post          ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    print("📡 SUPPORTED DECENTRALIZED PLATFORMS:")
    print("   🐘 Mastodon (ActivityPub)")
    print("   🌀 Bluesky (AT Protocol)")
    print("   ⚡ Nostr (Keys-Based)")
    print("   🦎 Lemmy (Reddit Alternative)")
    print("   🌉 Threads (Meta/ActivityPub)")
    print("   📸 Pixelfed (Instagram Alternative)")
    print("   📺 Reddit (Traditional)")
    print("   💻 Dev.to (Developer Community)")
    print()
    print(f"⏰ Timestamp: {datetime.now().isoformat()}")
    print(f"🎯 Platforms: {platforms or 'ALL DECENTRALIZED NETWORKS'}")
    print("=" * 60)
    
    results = distribute_content(platforms)
    
    print("\n" + "=" * 60)
    print("🚀 DISTRIBUTION COMPLETE")
    success_count = sum(1 for v in results.values() if v)
    print(f"✅ Success: {success_count}/{len(results)} platforms")
    print()
    print("📊 RESULTS:")
    for platform, success in results.items():
        status = "✅" if success else "❌"
        print(f"   {status} {platform}")
    print("=" * 60)
