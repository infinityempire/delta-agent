#!/usr/bin/env python3
"""
Zeta Warmup - Termux Edition v3
Uses www.reddit.com/login + token_v2 cookie for API access.
No OAuth App needed. Runs on native IP (Termux/home network).
"""
import os, sys, json, time, random, requests
from datetime import datetime

# ── Credentials ──────────────────────────────────────────────────────────────
USERNAME   = os.environ.get("REDDIT_USERNAME", "")
PASSWORD   = os.environ.get("REDDIT_PASSWORD", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

SUBREDDITS = [
    "AskReddit", "funny", "pics", "todayilearned",
    "mildlyinteresting", "worldnews", "science", "technology",
    "LifeProTips", "Showerthoughts"
]
COMMENTS_PER_RUN = 3
UPVOTES_PER_RUN  = 8

FALLBACK_COMMENTS = [
    "Great point! I've been thinking about this too.",
    "This is really interesting, thanks for sharing!",
    "I can relate to this. Well said!",
    "Thanks for the insight, very helpful!",
    "That's a fair take. Appreciate the perspective.",
    "Interesting! Never thought about it that way.",
    "Good observation. Thanks for bringing this up!",
    "Solid point, couldn't agree more.",
    "Really appreciate you sharing this.",
    "This is exactly what I needed to read today.",
]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ── Login ─────────────────────────────────────────────────────────────────────
def login(username, password):
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })

    log("Connecting to Reddit...")
    try:
        # Step 1: Get login page + CSRF cookie
        r = s.get("https://www.reddit.com/login", timeout=20)
        if r.status_code != 200:
            log(f"❌ Login page HTTP {r.status_code}")
            return None

        time.sleep(1.5)

        # Step 2: Extract CSRF token from cookies
        csrf = next((c.value for c in s.cookies if "csrf" in c.name.lower()), "")
        log(f"CSRF: {csrf[:15]}..." if csrf else "No CSRF found (continuing anyway)")

        # Step 3: POST login
        log(f"Logging in as u/{username}...")
        r2 = s.post(
            "https://www.reddit.com/login",
            data={
                "username": username,
                "password": password,
                "dest": "https://www.reddit.com",
                "csrf_token": csrf,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://www.reddit.com",
                "Referer": "https://www.reddit.com/login/",
            },
            timeout=20,
            allow_redirects=True,
        )
        log(f"Login response: HTTP {r2.status_code}")

        # Step 4: Extract token_v2 from cookies
        token_v2 = next((c.value for c in s.cookies if c.name == "token_v2"), "")
        if not token_v2:
            log("❌ No token_v2 cookie — login may have failed")
            log(f"Cookies: {[c.name for c in s.cookies]}")
            return None

        log(f"✅ Got token_v2: {token_v2[:20]}...")

        # Step 5: Set Authorization header for API calls
        s.headers.update({
            "Authorization": f"Bearer {token_v2}",
            "User-Agent": "Reddit/Version 2023.45.0/Android 13",
        })

        # Step 6: Verify login
        me = s.get("https://oauth.reddit.com/api/v1/me", timeout=15)
        if me.status_code == 200:
            me_data = me.json()
            name = me_data.get("name", "")
            lk = me_data.get("link_karma", 0)
            ck = me_data.get("comment_karma", 0)
            if name:
                log(f"✅ Verified as u/{name} | Karma: {lk} link / {ck} comment")
                return s
            else:
                log(f"⚠️ me.json response: {json.dumps(me_data)[:200]}")
        else:
            log(f"⚠️ me.json HTTP {me.status_code}: {me.text[:100]}")

        # Even if verification fails, try to proceed with the session
        log("⚠️ Could not verify identity, but proceeding with session...")
        return s

    except Exception as e:
        log(f"❌ Login error: {e}")
        return None

# ── Reddit API ────────────────────────────────────────────────────────────────
def get_hot_posts(session, subreddit, limit=20):
    try:
        r = session.get(
            f"https://oauth.reddit.com/r/{subreddit}/hot.json?limit={limit}",
            timeout=15
        )
        if r.status_code == 200:
            posts = r.json().get("data", {}).get("children", [])
            return [p["data"] for p in posts
                    if not p["data"].get("locked")
                    and not p["data"].get("archived")]
        log(f"⚠️ r/{subreddit}: HTTP {r.status_code}")
    except Exception as e:
        log(f"⚠️ r/{subreddit}: {e}")
    return []

def post_comment(session, post_id, text):
    try:
        r = session.post(
            "https://oauth.reddit.com/api/comment",
            data={
                "api_type": "json",
                "thing_id": f"t3_{post_id}",
                "text": text,
            },
            timeout=15
        )
        if r.status_code == 200:
            result = r.json()
            errors = result.get("json", {}).get("errors", [])
            if not errors:
                return True
            log(f"⚠️ Comment errors: {errors}")
        else:
            log(f"⚠️ Comment HTTP {r.status_code}: {r.text[:150]}")
    except Exception as e:
        log(f"⚠️ Comment error: {e}")
    return False

def upvote(session, post_id):
    try:
        r = session.post(
            "https://oauth.reddit.com/api/vote",
            data={"id": f"t3_{post_id}", "dir": "1"},
            timeout=10
        )
        return r.status_code == 200
    except:
        return False

def get_karma(session):
    try:
        r = session.get("https://oauth.reddit.com/api/v1/me", timeout=10)
        if r.status_code == 200:
            d = r.json()
            return d.get("link_karma", 0), d.get("comment_karma", 0)
    except:
        pass
    return 0, 0

def ai_comment(post_title, subreddit):
    if GEMINI_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(
                f"Write a SHORT natural Reddit comment (1-2 sentences) for this post in r/{subreddit}:\n"
                f"\"{post_title}\"\n\n"
                "Rules: sound like a real human, be relevant, no hashtags/emojis/marketing. Just the comment text."
            )
            c = resp.text.strip()
            return c[:280] if len(c) > 280 else c
        except Exception as e:
            log(f"⚠️ Gemini error: {e}")
    return random.choice(FALLBACK_COMMENTS)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print()
    print("=" * 60)
    print("  Zeta Warmup - Termux Edition v3")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  User: u/{USERNAME}")
    print("=" * 60)
    print()

    if not USERNAME or not PASSWORD:
        print("❌ Set REDDIT_USERNAME and REDDIT_PASSWORD!")
        sys.exit(1)

    session = login(USERNAME, PASSWORD)
    if not session:
        print("❌ Login failed.")
        sys.exit(1)

    comments_posted = 0
    upvotes_done = 0
    subs_visited = []

    subs = SUBREDDITS.copy()
    random.shuffle(subs)

    for sub in subs:
        if comments_posted >= COMMENTS_PER_RUN and upvotes_done >= UPVOTES_PER_RUN:
            break

        log(f"\n📌 r/{sub}...")
        posts = get_hot_posts(session, sub)
        if not posts:
            continue

        subs_visited.append(sub)
        log(f"   {len(posts)} posts found")

        # Upvote
        for post in posts[:3]:
            if upvotes_done >= UPVOTES_PER_RUN:
                break
            if upvote(session, post["id"]):
                upvotes_done += 1
                log(f"   👍 Upvoted: {post['title'][:55]}...")
            time.sleep(random.uniform(1, 3))

        # Comment
        if comments_posted < COMMENTS_PER_RUN:
            eligible = [p for p in posts if p.get("num_comments", 0) > 3]
            if eligible:
                post = random.choice(eligible[:8])
                comment = ai_comment(post["title"], sub)
                log(f"   💬 Commenting on: {post['title'][:55]}...")
                log(f"   📝 \"{comment}\"")
                if post_comment(session, post["id"], comment):
                    comments_posted += 1
                    log(f"   ✅ Comment posted! ({comments_posted}/{COMMENTS_PER_RUN})")
                else:
                    log(f"   ❌ Comment failed")
                time.sleep(random.uniform(5, 10))

        time.sleep(random.uniform(3, 7))

    lk, ck = get_karma(session)
    print()
    print("=" * 60)
    print("  ✅ Warmup Complete!")
    print(f"  Subreddits visited: {len(subs_visited)}")
    print(f"  Comments posted:    {comments_posted}/{COMMENTS_PER_RUN}")
    print(f"  Upvotes given:      {upvotes_done}/{UPVOTES_PER_RUN}")
    print(f"  Karma:              {lk} link / {ck} comment")
    print("=" * 60)
    print()

if __name__ == "__main__":
    main()
