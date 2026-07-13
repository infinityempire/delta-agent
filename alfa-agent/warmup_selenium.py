#!/usr/bin/env python3
"""
Zeta Warmup - Selenium Edition (Termux)
Uses Firefox headless + geckodriver to login to Reddit and post comments.
Runs on native IP (no proxy needed). Works on Termux/Android.
"""
import os, sys, json, time, random
from datetime import datetime

USERNAME   = os.environ.get("REDDIT_USERNAME", "")
PASSWORD   = os.environ.get("REDDIT_PASSWORD", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

# Termux paths — explicit to avoid Selenium auto-detection failure
GECKODRIVER_PATH = "/data/data/com.termux/files/usr/bin/geckodriver"
FIREFOX_PATH     = "/data/data/com.termux/files/usr/bin/firefox"

SUBREDDITS = [
    "AskReddit", "funny", "todayilearned",
    "mildlyinteresting", "worldnews", "science",
    "LifeProTips", "Showerthoughts", "technology", "pics"
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

def setup_driver():
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service

    opts = Options()
    opts.add_argument("-headless")
    opts.binary_location = FIREFOX_PATH
    opts.set_preference("general.useragent.override",
        "Mozilla/5.0 (Android 13; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0")
    opts.set_preference("dom.webdriver.enabled", False)
    opts.set_preference("useAutomationExtension", False)

    service = Service(
        executable_path=GECKODRIVER_PATH,
        log_path="/dev/null"
    )
    driver = webdriver.Firefox(options=opts, service=service)
    driver.set_page_load_timeout(30)
    return driver

def login(driver):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    log("Opening Reddit login page...")
    driver.get("https://www.reddit.com/login/")
    time.sleep(4)

    try:
        # Reddit uses faceplate-text-input (Web Component) with Shadow DOM
        # Must access via shadowRoot
        user_field = driver.execute_script("""
            var els = document.querySelectorAll('faceplate-text-input');
            for (var i=0; i<els.length; i++) {
                var sr = els[i].shadowRoot;
                if (!sr) continue;
                var inp = sr.querySelector('input');
                if (inp && (inp.name === 'username' || inp.type === 'text' || inp.type === '')) {
                    return inp;
                }
            }
            return null;
        """)

        if not user_field:
            log("❌ Username shadow input not found")
            return False

        driver.execute_script("arguments[0].value = '';", user_field)
        driver.execute_script("arguments[0].focus();", user_field)
        user_field.send_keys(USERNAME)
        # Trigger input event so React/Lit picks up the value
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
            user_field
        )
        time.sleep(0.5)

        # Password field — also in Shadow DOM
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
            log("❌ Password shadow input not found")
            return False

        driver.execute_script("arguments[0].value = '';", pass_field)
        driver.execute_script("arguments[0].focus();", pass_field)
        pass_field.send_keys(PASSWORD)
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
            pass_field
        )
        time.sleep(0.5)

        # Submit button
        submit = driver.execute_script(
            "return document.querySelector('button[type=submit]') "
            "|| document.querySelector('auth-flow-modal button');"
        )
        if submit:
            submit.click()
        else:
            from selenium.webdriver.common.keys import Keys
            pass_field.send_keys(Keys.RETURN)

        log("Login submitted, waiting...")
        time.sleep(6)

        current_url = driver.current_url
        log(f"URL after login: {current_url}")

        if "login" not in current_url.lower():
            log("✅ Login successful!")
            return True

        page = driver.page_source
        if USERNAME.lower() in page.lower():
            log("✅ Login successful (username found in page)!")
            return True

        log("❌ Still on login page")
        return False

    except Exception as e:
        log(f"❌ Login error: {e}")
        return False

def get_posts_via_api(driver, subreddit, limit=20):
    """Use Reddit JSON API with session cookies from Selenium"""
    import requests

    # Extract cookies from Selenium
    cookies = {c['name']: c['value'] for c in driver.get_cookies()}

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Android 13; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
    })
    for name, value in cookies.items():
        s.cookies.set(name, value, domain=".reddit.com")

    try:
        r = s.get(f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}", timeout=15)
        if r.status_code == 200:
            posts = r.json().get("data", {}).get("children", [])
            return [p["data"] for p in posts
                    if not p["data"].get("locked")
                    and not p["data"].get("archived")]
    except Exception as e:
        log(f"⚠️ API error: {e}")
    return []

def post_comment_via_browser(driver, post_url, comment_text):
    """Navigate to post and submit comment via browser"""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys

    try:
        driver.get(post_url)
        time.sleep(5)  # wait for JS to render

        comment_box = None

        # Try 1: div[contenteditable='true'] — skip reCAPTCHA iframes
        try:
            boxes = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div[contenteditable='true']"))
            )
            for box in boxes:
                # Skip hidden or zero-size elements
                if box.is_displayed() and box.size.get('height', 0) > 5:
                    comment_box = box
                    log("   Found contenteditable div")
                    break
        except:
            pass

        # Try 2: visible textarea (not reCAPTCHA, not hidden)
        if not comment_box:
            try:
                textareas = driver.find_elements(By.CSS_SELECTOR, "textarea")
                for ta in textareas:
                    name = (ta.get_attribute("name") or "").lower()
                    cls  = (ta.get_attribute("class") or "").lower()
                    tid  = (ta.get_attribute("id") or "").lower()
                    # Skip reCAPTCHA and hidden textareas
                    if any(x in name+cls+tid for x in ["recaptcha", "g-recaptcha", "captcha"]):
                        continue
                    # Check actual size via JS (not just is_displayed)
                    rect = driver.execute_script(
                        "var r=arguments[0].getBoundingClientRect(); return {w:r.width,h:r.height};", ta
                    )
                    if rect.get('h', 0) > 10 and rect.get('w', 0) > 10:
                        comment_box = ta
                        log("   Found textarea")
                        break
            except:
                pass

        if not comment_box:
            log("⚠️ Comment box not found")
            return False

        # Click to focus, then type
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", comment_box)
        time.sleep(0.5)
        comment_box.click()
        time.sleep(0.5)
        comment_box.send_keys(comment_text)
        time.sleep(1)

        # Find submit button — try multiple selectors
        submit_btn = None
        for sel in [
            "button[type='submit']",
            "button.submit",
            "[data-testid='comment-submit-button']",
            "shreddit-composer button",
        ]:
            try:
                submit_btn = driver.find_element(By.CSS_SELECTOR, sel)
                if submit_btn.is_displayed():
                    break
                submit_btn = None
            except:
                pass

        if submit_btn:
            driver.execute_script("arguments[0].scrollIntoView(true);", submit_btn)
            time.sleep(0.3)
            submit_btn.click()
            time.sleep(4)
            log("✅ Comment submitted via button!")
            return True
        else:
            # Fallback: Ctrl+Enter
            comment_box.send_keys(Keys.CONTROL + Keys.RETURN)
            time.sleep(4)
            log("✅ Comment submitted via Ctrl+Enter!")
            return True

    except Exception as e:
        log(f"⚠️ Browser comment error: {e}")
        return False

def upvote_via_api(driver, post_id):
    """Upvote using session cookies"""
    import requests

    cookies = {c['name']: c['value'] for c in driver.get_cookies()}
    modhash = cookies.get("modhash", "")

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Android 13; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
        "X-Modhash": modhash,
    })
    for name, value in cookies.items():
        s.cookies.set(name, value, domain=".reddit.com")

    try:
        r = s.post("https://www.reddit.com/api/vote",
            data={"id": f"t3_{post_id}", "dir": "1"},
            timeout=10)
        return r.status_code == 200
    except:
        return False

def main():
    print()
    print("=" * 60)
    print("  Zeta Warmup - Selenium Edition")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  User: u/{USERNAME}")
    print("=" * 60)
    print()

    if not USERNAME or not PASSWORD:
        print("❌ Set REDDIT_USERNAME and REDDIT_PASSWORD!")
        sys.exit(1)

    log(f"geckodriver: {GECKODRIVER_PATH}")
    log(f"Firefox:     {FIREFOX_PATH}")
    log("Starting Firefox (headless)...")
    try:
        driver = setup_driver()
    except Exception as e:
        log(f"❌ Firefox failed to start: {e}")
        sys.exit(1)

    try:
        if not login(driver):
            log("❌ Login failed.")
            driver.quit()
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
            posts = get_posts_via_api(driver, sub)
            if not posts:
                continue

            subs_visited.append(sub)
            log(f"   {len(posts)} posts found")

            # Upvote
            for post in posts[:3]:
                if upvotes_done >= UPVOTES_PER_RUN:
                    break
                if upvote_via_api(driver, post["id"]):
                    upvotes_done += 1
                    log(f"   👍 Upvoted: {post['title'][:55]}...")
                time.sleep(random.uniform(1, 3))

            # Comment
            if comments_posted < COMMENTS_PER_RUN:
                eligible = [p for p in posts if p.get("num_comments", 0) > 3]
                if eligible:
                    post = random.choice(eligible[:8])
                    comment = ai_comment(post["title"], sub)
                    post_url = f"https://www.reddit.com{post['permalink']}"
                    log(f"   💬 Commenting on: {post['title'][:55]}...")
                    log(f"   📝 \"{comment}\"")
                    if post_comment_via_browser(driver, post_url, comment):
                        comments_posted += 1
                        log(f"   ✅ Comment posted! ({comments_posted}/{COMMENTS_PER_RUN})")
                    else:
                        log(f"   ❌ Comment failed")
                    time.sleep(random.uniform(5, 10))

            time.sleep(random.uniform(3, 7))

        print()
        print("=" * 60)
        print("  ✅ Warmup Complete!")
        print(f"  Subreddits visited: {len(subs_visited)}")
        print(f"  Comments posted:    {comments_posted}/{COMMENTS_PER_RUN}")
        print(f"  Upvotes given:      {upvotes_done}/{UPVOTES_PER_RUN}")
        print("=" * 60)
        print()

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
