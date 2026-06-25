#!/usr/bin/env python3
"""
Zeta Warmup v2 — Termux Edition
Strategy: Use Selenium ONLY for login (to get session cookies).
Then use requests + cookies for all Reddit API calls (comments, upvotes).
This avoids all Selenium DOM issues with Reddit's Web Components.
"""
import os, sys, time, random, json
from datetime import datetime

USERNAME   = os.environ.get("REDDIT_USERNAME", "")
PASSWORD   = os.environ.get("REDDIT_PASSWORD", "")

GECKODRIVER_PATH = "/data/data/com.termux/files/usr/bin/geckodriver"
FIREFOX_PATH     = "/data/data/com.termux/files/usr/bin/firefox"

SUBREDDITS = [
    "AskReddit", "funny", "todayilearned", "mildlyinteresting",
    "worldnews", "science", "LifeProTips", "Showerthoughts",
    "technology", "pics"
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
    "Haha, this is so true.",
    "Never thought about it this way before. Thanks!",
]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def selenium_login():
    """Use Firefox headless to login and return session cookies as dict."""
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service
    from selenium.webdriver.common.keys import Keys

    opts = Options()
    opts.add_argument("-headless")
    opts.binary_location = FIREFOX_PATH
    opts.set_preference("dom.webdriver.enabled", False)
    opts.set_preference("useAutomationExtension", False)

    service = Service(executable_path=GECKODRIVER_PATH, log_path="/dev/null")
    driver = webdriver.Firefox(options=opts, service=service)
    driver.set_page_load_timeout(30)

    try:
        log("Opening Reddit login page...")
        driver.get("https://www.reddit.com/login/")
        time.sleep(5)

        # Username — via Shadow DOM
        user_field = driver.execute_script("""
            var els = document.querySelectorAll('faceplate-text-input');
            for (var i=0; i<els.length; i++) {
                var sr = els[i].shadowRoot;
                if (!sr) continue;
                var inp = sr.querySelector('input');
                if (inp) return inp;
            }
            return null;
        """)
        if not user_field:
            log("❌ Username field not found")
            return None

        driver.execute_script("arguments[0].focus();", user_field)
        user_field.send_keys(USERNAME)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input',{bubbles:true}));", user_field)
        time.sleep(0.5)

        # Password — via Shadow DOM
        pass_field = driver.execute_script("""
            var els = document.querySelectorAll('faceplate-text-input');
            for (var i=0; i<els.length; i++) {
                var sr = els[i].shadowRoot;
                if (!sr) continue;
                var inp = sr.querySelector('input[type=password]');
                if (inp) return inp;
            }
            return null;
        """)
        if not pass_field:
            log("❌ Password field not found")
            return None

        driver.execute_script("arguments[0].focus();", pass_field)
        pass_field.send_keys(PASSWORD)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input',{bubbles:true}));", pass_field)
        time.sleep(0.5)
        pass_field.send_keys(Keys.RETURN)

        log("Login submitted, waiting...")
        time.sleep(7)

        url = driver.current_url
        log(f"URL: {url}")
        if "login" in url.lower() and "solution" not in url.lower():
            log("❌ Login failed")
            return None

        # Extract cookies
        cookies = {c['name']: c['value'] for c in driver.get_cookies()}
        log(f"✅ Login successful! Got {len(cookies)} cookies")
        return cookies

    finally:
        driver.quit()

def make_session(cookies):
    """Create a requests.Session with Reddit cookies."""
    import requests
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Android 13; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.5",
        "X-Requested-With": "XMLHttpRequest",
    })
    for name, value in cookies.items():
        s.cookies.set(name, value, domain=".reddit.com")
    # Set modhash header if available
    modhash = cookies.get("modhash", "")
    if modhash:
        s.headers["X-Modhash"] = modhash
    return s

def get_modhash(session):
    """Fetch modhash from Reddit API."""
    try:
        r = session.get("https://www.reddit.com/api/me.json", timeout=10)
        if r.status_code == 200:
            data = r.json()
            mh = data.get("data", {}).get("modhash", "")
            if mh:
                session.headers["X-Modhash"] = mh
                log(f"Got modhash: {mh[:8]}...")
                return mh
    except Exception as e:
        log(f"⚠️ modhash error: {e}")
    return ""

def get_posts(session, subreddit, limit=25):
    """Fetch hot posts from subreddit."""
    try:
        r = session.get(
            f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}",
            timeout=15
        )
        if r.status_code == 200:
            posts = r.json().get("data", {}).get("children", [])
            return [p["data"] for p in posts
                    if not p["data"].get("locked")
                    and not p["data"].get("archived")
                    and not p["data"].get("is_self") == False]  # prefer text posts
    except Exception as e:
        log(f"⚠️ get_posts error: {e}")
    return []

def post_comment(session, post_fullname, comment_text):
    """Post a comment via Reddit API."""
    try:
        r = session.post(
            "https://www.reddit.com/api/comment",
            data={
                "api_type": "json",
                "thing_id": post_fullname,
                "text": comment_text,
            },
            timeout=15
        )
        if r.status_code == 200:
            resp = r.json()
            errors = resp.get("json", {}).get("errors", [])
            if not errors:
                comment_id = resp.get("json", {}).get("data", {}).get("things", [{}])[0].get("data", {}).get("id", "")
                log(f"✅ Comment posted! id={comment_id}")
                return True
            else:
                log(f"⚠️ Comment errors: {errors}")
        else:
            log(f"⚠️ Comment HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log(f"⚠️ post_comment error: {e}")
    return False

def upvote(session, post_fullname):
    """Upvote a post via Reddit API."""
    try:
        r = session.post(
            "https://www.reddit.com/api/vote",
            data={"id": post_fullname, "dir": "1"},
            timeout=10
        )
        return r.status_code == 200
    except:
        return False

def main():
    print()
    print("=" * 60)
    print("  Zeta Warmup v2 — API Edition")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  User: u/{USERNAME}")
    print("=" * 60)
    print()

    if not USERNAME or not PASSWORD:
        print("❌ Set REDDIT_USERNAME and REDDIT_PASSWORD!")
        sys.exit(1)

    # Step 1: Login with Selenium to get cookies
    cookies = selenium_login()
    if not cookies:
        log("❌ Could not get session cookies. Aborting.")
        sys.exit(1)

    # Step 2: Create requests session
    session = make_session(cookies)

    # Step 3: Get modhash (needed for API calls)
    modhash = get_modhash(session)
    if not modhash:
        log("⚠️ No modhash — comments may fail. Trying anyway...")

    # Step 4: Browse subreddits and act
    comments_posted = 0
    upvotes_done    = 0
    subs_visited    = []

    subs = SUBREDDITS.copy()
    random.shuffle(subs)

    for sub in subs:
        if comments_posted >= COMMENTS_PER_RUN and upvotes_done >= UPVOTES_PER_RUN:
            break

        log(f"\n📌 r/{sub}...")
        posts = get_posts(session, sub)
        if not posts:
            log(f"   No posts found")
            continue

        subs_visited.append(sub)
        log(f"   {len(posts)} posts found")

        # Upvote first few posts
        for post in posts[:3]:
            if upvotes_done >= UPVOTES_PER_RUN:
                break
            fullname = f"t3_{post['id']}"
            if upvote(session, fullname):
                upvotes_done += 1
                log(f"   👍 Upvoted: {post['title'][:55]}...")
            time.sleep(random.uniform(1, 3))

        # Post a comment
        if comments_posted < COMMENTS_PER_RUN:
            eligible = [p for p in posts if p.get("num_comments", 0) > 2]
            if eligible:
                post = random.choice(eligible[:8])
                comment = random.choice(FALLBACK_COMMENTS)
                fullname = f"t3_{post['id']}"
                log(f"   💬 Commenting on: {post['title'][:55]}...")
                log(f"   📝 \"{comment}\"")
                if post_comment(session, fullname, comment):
                    comments_posted += 1
                    log(f"   ✅ ({comments_posted}/{COMMENTS_PER_RUN})")
                else:
                    log(f"   ❌ Comment failed")
                time.sleep(random.uniform(8, 15))

        time.sleep(random.uniform(3, 7))

    print()
    print("=" * 60)
    print("  ✅ Warmup Complete!")
    print(f"  Subreddits visited: {len(subs_visited)}")
    print(f"  Comments posted:    {comments_posted}/{COMMENTS_PER_RUN}")
    print(f"  Upvotes given:      {upvotes_done}/{UPVOTES_PER_RUN}")
    print("=" * 60)
    print()

if __name__ == "__main__":
    main()
