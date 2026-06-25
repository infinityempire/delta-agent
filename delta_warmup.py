#!/usr/bin/env python3
"""
Delta Agent — Lead Hunter & Value-First Responder (Termux Edition)
Strategy:
1. Selenium for Login (get cookies).
2. Reddit API to fetch posts from entrepreneur/automation subreddits.
3. OpenAI API (or Gemini fallback) to analyze posts and generate value-first responses.
4. Reddit API to post comments.
"""
import os, sys, time, random, json
from datetime import datetime

USERNAME   = os.environ.get("REDDIT_USERNAME", "")
PASSWORD   = os.environ.get("REDDIT_PASSWORD", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

GECKODRIVER_PATH = "/data/data/com.termux/files/usr/bin/geckodriver"
FIREFOX_PATH     = "/data/data/com.termux/files/usr/bin/firefox"

SUBREDDITS = [
    "Entrepreneur", "SaaS", "Automate", "nocode",
    "SideProject", "smallbusiness", "startups"
]
COMMENTS_PER_RUN = 3
UPVOTES_PER_RUN  = 5

SYSTEM_PROMPT = """You are Delta, an AI agent representing 'Tal HaTil Empire'.
Your goal is to identify 'despair gaps' — moments where users are frustrated with manual tasks, seeking AI/automation tools, or stuck technically.

RULES FOR YOUR RESPONSE:
1. VALUE FIRST: Provide a practical, authoritative solution or insight to their specific problem. Give them the 'missing 100 meters'.
2. NO SPAM/SALES: Do NOT sound like a marketer. Do NOT say "check out our product".
3. TONE: Professional, helpful, concise, and direct.
4. If it fits organically, you may hint that building custom AI agents or automations is exactly what you do, but keep it subtle.
5. KEEP IT SHORT: 2-4 sentences max.

Output ONLY the comment text. No quotes, no intro.
If the post is irrelevant (not about automation, business struggles, AI, or tech), output exactly: "IRRELEVANT".
"""

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def generate_ai_comment(post_title, post_text):
    if not OPENAI_KEY:
        log("⚠️ OPENAI_API_KEY not set. Cannot generate AI comment.")
        return None

    try:
        import requests
        headers = {
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Title: {post_title}\n\nBody: {post_text[:1000]}"}
            ],
            "temperature": 0.7,
            "max_tokens": 150
        }
        r = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=20)
        if r.status_code == 200:
            text = r.json()["choices"][0]["message"]["content"].strip()
            if text == "IRRELEVANT":
                return None
            return text
        else:
            log(f"⚠️ OpenAI error: {r.status_code} {r.text}")
    except Exception as e:
        log(f"⚠️ OpenAI exception: {e}")
    return None

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
        if "login" in url.lower() and "solution" not in url.lower():
            log("❌ Login failed")
            return None

        cookies = {c['name']: c['value'] for c in driver.get_cookies()}
        log(f"✅ Login successful! Got {len(cookies)} cookies")
        return cookies

    finally:
        driver.quit()

def make_session(cookies):
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
    modhash = cookies.get("modhash", "")
    if modhash:
        s.headers["X-Modhash"] = modhash
    return s

def get_modhash(session):
    try:
        r = session.get("https://www.reddit.com/api/me.json", timeout=10)
        if r.status_code == 200:
            mh = r.json().get("data", {}).get("modhash", "")
            if mh:
                session.headers["X-Modhash"] = mh
                return mh
    except:
        pass
    return ""

def get_posts(session, subreddit, limit=25):
    try:
        r = session.get(f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}", timeout=15)
        if r.status_code == 200:
            posts = r.json().get("data", {}).get("children", [])
            return [p["data"] for p in posts
                    if not p["data"].get("locked")
                    and not p["data"].get("archived")
                    and p["data"].get("is_self") == True]  # Only text posts for analysis
    except:
        pass
    return []

def post_comment(session, post_fullname, comment_text):
    try:
        r = session.post(
            "https://www.reddit.com/api/comment",
            data={"api_type": "json", "thing_id": post_fullname, "text": comment_text},
            timeout=15
        )
        if r.status_code == 200:
            resp = r.json()
            if not resp.get("json", {}).get("errors", []):
                return True
    except:
        pass
    return False

def upvote(session, post_fullname):
    try:
        r = session.post("https://www.reddit.com/api/vote", data={"id": post_fullname, "dir": "1"}, timeout=10)
        return r.status_code == 200
    except:
        return False

def main():
    print()
    print("=" * 60)
    print("  Delta Agent — Lead Hunter")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  User: u/{USERNAME}")
    print("=" * 60)
    print()

    if not USERNAME or not PASSWORD or not OPENAI_KEY:
        print("❌ Set REDDIT_USERNAME, REDDIT_PASSWORD, and OPENAI_API_KEY!")
        sys.exit(1)

    cookies = selenium_login()
    if not cookies:
        sys.exit(1)

    session = make_session(cookies)
    get_modhash(session)

    comments_posted = 0
    upvotes_done    = 0
    subs_visited    = []

    subs = SUBREDDITS.copy()
    random.shuffle(subs)

    for sub in subs:
        if comments_posted >= COMMENTS_PER_RUN:
            break

        log(f"\n📌 r/{sub}...")
        posts = get_posts(session, sub)
        if not posts:
            continue

        subs_visited.append(sub)
        log(f"   {len(posts)} text posts found")

        for post in posts:
            if comments_posted >= COMMENTS_PER_RUN:
                break

            # Analyze post with AI
            title = post.get("title", "")
            text = post.get("selftext", "")
            
            # Skip short posts (probably not detailed problems)
            if len(text) < 100:
                continue

            comment = generate_ai_comment(title, text)
            
            if comment:
                fullname = f"t3_{post['id']}"
                log(f"   🎯 Match found: {title[:55]}...")
                log(f"   📝 Delta says: \"{comment}\"")
                
                if post_comment(session, fullname, comment):
                    comments_posted += 1
                    log(f"   ✅ Comment posted! ({comments_posted}/{COMMENTS_PER_RUN})")
                    
                    if upvotes_done < UPVOTES_PER_RUN:
                        upvote(session, fullname)
                        upvotes_done += 1
                else:
                    log(f"   ❌ Comment failed")
                
                time.sleep(random.uniform(8, 15))
            else:
                # log(f"   ⏭️ Irrelevant: {title[:30]}...")
                pass

    print()
    print("=" * 60)
    print("  ✅ Delta Run Complete!")
    print(f"  Subreddits checked: {len(subs_visited)}")
    print(f"  Comments posted:    {comments_posted}/{COMMENTS_PER_RUN}")
    print("=" * 60)
    print()

if __name__ == "__main__":
    main()
