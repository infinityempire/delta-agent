"""
Delta Agent – Automated Lead Hunter for Tal HaTil
==================================================
Stage 1: Live Reddit Scraper (ScrapingBee → ScraperAPI → Reddit RSS)
Stage 2: Gemini AI Analysis (gemini-2.5-flash, with retry/backoff)
Stage 3: JSON Report Generation
Stage 4: SMTP Email Delivery
"""

import os
import sys
import json
import time
import smtplib
import ssl
import html
import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# ── Environment Variables ────────────────────────────────────────────────────
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")
SMTP_HOST       = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT       = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER       = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD   = os.environ.get("SMTP_PASSWORD", "")
SMTP_TO         = os.environ.get("SMTP_TO", "")
SCRAPER_API_KEY     = os.environ.get("SCRAPER_API_KEY", "")
SCRAPINGBEE_API_KEY = os.environ.get("SCRAPINGBEE_API_KEY", "")

# ── Config ───────────────────────────────────────────────────────────────────
SUBREDDITS     = ["entrepreneur", "startups", "smallbusiness", "forhire", "freelance"]
POSTS_PER_SUB  = 25
MAX_BODY_CHARS = 800   # trimmed to save Gemini tokens
TOP_LEADS      = 10
OUTPUT_DIR     = "output"
REPORT_PATH    = f"{OUTPUT_DIR}/execution_report.json"
GEMINI_MODEL   = "gemini-2.5-flash"
GEMINI_RETRIES = 3
GEMINI_BACKOFF = [15, 45, 90]        # seconds to wait before each retry (max 3 attempts)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive"
}

# ── Startup ───────────────────────────────────────────────────────────────────
print("=" * 60)
print("DELTA AGENT – Starting Up")
print(f"Timestamp : {datetime.now(timezone.utc).isoformat()}")
print(f"Model     : {GEMINI_MODEL}")
print("=" * 60)

missing = []
if not GEMINI_API_KEY:  missing.append("GEMINI_API_KEY")
if not SMTP_USER:       missing.append("SMTP_USER")
if not SMTP_PASSWORD:   missing.append("SMTP_PASSWORD")
if not SMTP_TO:         missing.append("SMTP_TO")
if missing:
    print(f"[CRITICAL] Missing environment variables: {missing}")
    sys.exit(1)

print("[OK] All required env vars present")
if not SCRAPINGBEE_API_KEY:
    print("[WARN] SCRAPINGBEE_API_KEY not set. ScraperAPI will be used as the first proxy fallback.")
if not SCRAPER_API_KEY:
    print("[WARN] SCRAPER_API_KEY not set. Reddit RSS will be used if ScrapingBee is unavailable.")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Stage 1: Reddit Scraper ──────────────────────────────────────────────────
print("\n[STAGE 1] Scraping Reddit via ScrapingBee → ScraperAPI → Reddit RSS...")

def _normalize_post(subreddit, title, body, url, author=""):
    title = (title or "").strip()
    body = (body or "").strip()
    if not title or body in ("", "[deleted]", "[removed]"):
        return None
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS] + "..."
    return {
        "subreddit": subreddit,
        "title": title,
        "body": body,
        "url": url,
        "author": author or "",
    }


def _posts_from_reddit_json(subreddit, payload):
    posts = []
    for p in payload.get("data", {}).get("children", []):
        d = p.get("data", {})
        normalized = _normalize_post(
            subreddit=subreddit,
            title=d.get("title", ""),
            body=d.get("selftext", ""),
            url="https://reddit.com" + d.get("permalink", ""),
            author=d.get("author", ""),
        )
        if normalized:
            posts.append(normalized)
    return posts


def _fetch_with_scrapingbee(subreddit):
    if not SCRAPINGBEE_API_KEY:
        return []
    reddit_url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={POSTS_PER_SUB}"
    resp = requests.get(
        "https://app.scrapingbee.com/api/v1/",
        params={
            "api_key": SCRAPINGBEE_API_KEY,
            "url": reddit_url,
            "render_js": "false",
        },
        headers=HEADERS,
        timeout=60,
    )
    if resp.status_code != 200:
        print(f"  [WARN] r/{subreddit}: ScrapingBee HTTP {resp.status_code}")
        return []
    return _posts_from_reddit_json(subreddit, resp.json())


def _fetch_with_scraperapi(subreddit):
    if not SCRAPER_API_KEY:
        return []
    reddit_url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={POSTS_PER_SUB}"
    proxy_url = (
        f"http://api.scraperapi.com"
        f"?api_key={SCRAPER_API_KEY}"
        f"&url={requests.utils.quote(reddit_url, safe='')}"
    )
    resp = requests.get(proxy_url, headers=HEADERS, timeout=60)
    if resp.status_code != 200:
        print(f"  [WARN] r/{subreddit}: ScraperAPI HTTP {resp.status_code}")
        return []
    return _posts_from_reddit_json(subreddit, resp.json())


def _fetch_with_reddit_rss(subreddit):
    rss_url = f"https://www.reddit.com/r/{subreddit}/new/.rss?limit={POSTS_PER_SUB}"
    resp = requests.get(rss_url, headers=HEADERS, timeout=60)
    if resp.status_code != 200:
        print(f"  [WARN] r/{subreddit}: Reddit RSS HTTP {resp.status_code}")
        return []

    root = ET.fromstring(resp.content)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    posts = []
    for entry in root.findall("atom:entry", ns):
        title = entry.findtext("atom:title", default="", namespaces=ns)
        body = entry.findtext("atom:content", default="", namespaces=ns)
        author = entry.findtext("atom:author/atom:name", default="", namespaces=ns)
        link = entry.find("atom:link", ns)
        url = link.get("href", "") if link is not None else ""
        normalized = _normalize_post(
            subreddit=subreddit,
            title=html.unescape(title),
            body=html.unescape(body),
            url=url,
            author=author,
        )
        if normalized:
            posts.append(normalized)
    return posts


raw_posts = []
for sub in SUBREDDITS:
    providers = (
        ("ScrapingBee", _fetch_with_scrapingbee),
        ("ScraperAPI", _fetch_with_scraperapi),
        ("Reddit RSS", _fetch_with_reddit_rss),
    )
    collected = []
    for provider_name, fetch_posts in providers:
        try:
            collected = fetch_posts(sub)
            if collected:
                raw_posts.extend(collected)
                print(f"  [OK] r/{sub}: {len(collected)} posts collected via {provider_name}")
                break
        except Exception as e:
            print(f"  [WARN] r/{sub}: {provider_name} failed: {e}")
    if not collected:
        print(f"  [ERROR] r/{sub}: all scraping providers failed")
    time.sleep(1)

print(f"\n[STAGE 1] Total posts collected: {len(raw_posts)}")

scraping_failed = not raw_posts
if scraping_failed:
    print("[WARN] No posts collected. Continuing with a deliverable failure report instead of failing the workflow.")

# ── Stage 2: Gemini AI Analysis (with retry/backoff) ─────────────────────────
print(f"\n[STAGE 2] Analyzing with Gemini AI ({GEMINI_MODEL})...")

posts_text = ""
for i, p in enumerate(raw_posts):
    posts_text += (
        f"\n--- Post {i+1} ---\n"
        f"Subreddit: r/{p['subreddit']}\n"
        f"Title: {p['title']}\n"
        f"Body: {p['body']}\n"
        f"URL: {p['url']}\n"
        f"Author: {p['author']}\n"
    )

prompt = f"""You are Delta's compliance-first Reddit market intelligence analyst.
Your only offer is the high-ticket service named: Reddit Intent Intelligence Sprint.

MISSION
Analyze the following {len(raw_posts)} Reddit posts and produce a single, executive-ready markdown report for Reddit Intent Intelligence Sprint.
Prioritize posts showing strong buying intent, urgent pain, operational friction, repeated industry frustration, or founder/operator willingness to pay for expertise.

COMPLIANCE BOUNDARY
- Absolutely NO automated outreach instructions.
- Do NOT recommend auto-DMs, bot posting, automated replies, scripted mass commenting, scraping-to-message workflows, or any other automated engagement.
- Every action item MUST be explicitly labeled exactly as: Reddit Pro Manual Step.
- Do not include tactical engagement guidance under any other label.
- Focus 100% on value-driven authority building inside Reddit communities.
- Never draft aggressive sales pitches, pressure-based CTAs, spam, link drops, fake scarcity, or manipulative language.
- Draft replies must be insightful, non-salesy comments that solve part of the user's problem and build brand authority.
- Draft replies must contain no links, no promotional claims, and no request to DM.

OUTPUT RULES
- Return ONLY markdown.
- Do NOT return JSON.
- Follow the report structure below exactly.
- Preserve the exact section headings and required labels shown in REPORT FORMAT.
- Use the source subreddit and post title from the raw Reddit data.
- Include up to {TOP_LEADS} strongest high-intent signals in section 2.
- Include one strongest trending debate or discussion angle in section 3.
- The Executive Action Items section must include a numeric count for Total Intent Opportunities Captured.

REPORT FORMAT
# 📊 Reddit Intent Intelligence Sprint Report
**Target Market Analyzer:** [Identify the core niche from data]
**Compliance Status:** 100% Secure (Manual Action Only)
---
### 1. 🔥 The Pain Map
* **Core Trigger:** [Analyze the raw data to extract core triggers and industry frustrations]
* **Emotional Hook & Scale:** [Emotional triggers of users]
---
### 2. 🎯 High-Intent Signals
> **Subreddit:** r/[Name] | **Post Title:** "[Title]"
> - **The Signal:** [Why this user is a high-value lead]
> - **Reddit Pro Manual Step:** [Action item for human using Reddit Pro features]
> - **Value-First Draft Reply (Ready for Review):**
>   > "[Draft a deeply insightful, non-salesy comment that solves a piece of their problem and builds instant brand authority. No links, no spam.]"
---
### 3. 📈 Hot Discussion Angle
> **Subreddit:** r/[Name] | **Post Title:** "[Title]"
> - **The Angle:** [What the debate is about and why it's trending]
> - **Reddit Pro Manual Step:** [How a human should enter the comment section to build organic authority]
---
### 4. 🛠️ Executive Action Items
- **Total Intent Opportunities Captured:** [Count]
- **Recommended Strategy:** Have your representative spend exactly 15 minutes manually applying the value-first drafts to build organic pipeline.
- **Safe Boundary Check:** Verified. 0 automated actions suggested. Brand reputation fully protected.

POSTS TO ANALYZE:
{posts_text}"""

from google import genai as genai_new

leads            = []
sprint_report_md = "ניתוח ה-AI לא הצליח להשלים."
gemini_ok        = False

if scraping_failed:
    sprint_report_md = """# 📊 Reddit Intent Intelligence Sprint Report
**Target Market Analyzer:** Unable to determine because Reddit collection returned 0 posts
**Compliance Status:** 100% Secure (Manual Action Only)
---
### 1. 🔥 The Pain Map
* **Core Trigger:** No live Reddit posts were collected from the configured providers during this run.
* **Emotional Hook & Scale:** No current market signals were available to analyze.
---
### 2. 🎯 High-Intent Signals
No high-intent signals captured because all Reddit collection providers returned 0 usable posts.
---
### 3. 📈 Hot Discussion Angle
No discussion angle captured because there were no posts to analyze.
---
### 4. 🛠️ Executive Action Items
- **Total Intent Opportunities Captured:** 0
- **Recommended Strategy:** Verify SCRAPINGBEE_API_KEY or SCRAPER_API_KEY secrets and rerun the workflow.
- **Safe Boundary Check:** Verified. 0 automated actions suggested. Brand reputation fully protected.
"""
    print("[WARN] Skipping Gemini because there are no posts to analyze")
else:
    _gclient = genai_new.Client(api_key=GEMINI_API_KEY)

for attempt in range(GEMINI_RETRIES if not scraping_failed else 0):
    try:
        print(f"  [INFO] Gemini attempt {attempt + 1}/{GEMINI_RETRIES}...")
        response = _gclient.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        sprint_report_md = response.text.strip()
        if not sprint_report_md.startswith("# 📊 Reddit Intent Intelligence Sprint Report"):
            raise ValueError("Gemini response did not match the required sprint report markdown format")
        high_intent_section = sprint_report_md.split("### 3. 📈 Hot Discussion Angle", 1)[0]
        leads = [
            line for line in high_intent_section.splitlines()
            if line.startswith("> **Subreddit:**")
        ]
        print(f"[OK] Gemini returned sprint report with {len(leads)} intent opportunities")
        gemini_ok = True
        break
    except Exception as e:
        err_str = str(e)
        print(f"  [ERROR] Attempt {attempt + 1} failed: {type(e).__name__}: {err_str[:200]}")
        if attempt < GEMINI_RETRIES - 1:
            wait = GEMINI_BACKOFF[attempt]
            print(f"  [INFO] Waiting {wait}s before retry...")
            time.sleep(wait)

if not gemini_ok and not scraping_failed:
    print("[WARN] All Gemini attempts failed. Sending empty report.")
    sprint_report_md = "ניתוח ה-AI נכשל לאחר מספר ניסיונות. ראה לוגים לפרטים."

# ── Stage 3: JSON Report ─────────────────────────────────────────────────────
print("\n[STAGE 3] Generating report...")

report = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "scan_stats": {
        "subreddits_scanned": SUBREDDITS,
        "total_posts_collected": len(raw_posts),
        "leads_identified": len(leads)
    },
    "ai_report_markdown": sprint_report_md,
    "intent_opportunities": leads
}

with open(REPORT_PATH, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f"[OK] Report saved to {REPORT_PATH}")

# ── Stage 4: SMTP Email Delivery ─────────────────────────────────────────────
print("\n[STAGE 4] Sending email report...")

email_sent = False
try:
    msg   = MIMEMultipart("mixed")
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    msg["Subject"] = f"📊 Reddit Intent Intelligence Sprint – {len(leads)} opportunities | {today}"
    msg["From"]    = SMTP_USER
    msg["To"]      = SMTP_TO

    report_html = html.escape(sprint_report_md)

    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;direction:rtl;text-align:right;">
      <h2 style="color:#2c3e50;">📊 Reddit Intent Intelligence Sprint</h2>
      <p style="color:#7f8c8d;">{today} | {datetime.now(timezone.utc).strftime('%H:%M')} UTC</p>
      <div style="background:#ecf0f1;padding:15px;border-radius:8px;margin-bottom:20px;direction:ltr;text-align:left;white-space:pre-wrap;font-family:Consolas,Menlo,monospace;">
        {report_html}
      </div>
      <p style="margin-top:20px;color:#95a5a6;font-size:12px;">
        סה"כ נסרקו: {len(raw_posts)} פוסטים מ-{len(SUBREDDITS)} subreddits | קובץ JSON מלא מצורף
      </p>
    </body></html>"""

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with open(REPORT_PATH, "rb") as f:
        att = MIMEBase("application", "octet-stream")
        att.set_payload(f.read())
        encoders.encode_base64(att)
        att.add_header("Content-Disposition",
                       f"attachment; filename=delta_report_{today.replace('/','_')}.json")
        msg.attach(att)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as server:
        server.login(SMTP_USER, SMTP_PASSWORD)
        


# keep-alive: 2026-05-27

        server.sendmail(SMTP_USER, SMTP_TO, msg.as_string())

    email_sent = True
    print("[OK] Email sent successfully")

except Exception as e:
    print(f"[ERROR] Email delivery failed: {e}")

# ── Done ──────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("DELTA AGENT – Run Complete")
print(f"Posts scanned : {len(raw_posts)}")
print(f"Intent opportunities: {len(leads)}")
print(f"Report saved  : {REPORT_PATH}")
print("=" * 60)
sys.exit(0 if email_sent else 1)
