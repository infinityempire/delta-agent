"""
Delta Agent – Automated Lead Hunter for Tal HaTil
==================================================
Stage 1: Live Reddit Scraper (via ScraperAPI)
Stage 2: Gemini AI Analysis (gemini-2.0-flash, with retry/backoff)
Stage 3: JSON Report Generation
Stage 4: SMTP Email Delivery
"""

import os
import sys
import json
import time
import smtplib
import ssl
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
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")

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
if not SCRAPER_API_KEY: missing.append("SCRAPER_API_KEY")

if missing:
    print(f"[CRITICAL] Missing environment variables: {missing}")
    sys.exit(1)

print("[OK] All required env vars present")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Stage 1: Reddit Scraper ──────────────────────────────────────────────────
print("\n[STAGE 1] Scraping Reddit via ScraperAPI...")

raw_posts = []
for sub in SUBREDDITS:
    reddit_url = f"https://www.reddit.com/r/{sub}/new.json?limit={POSTS_PER_SUB}"
    proxy_url  = (
        f"http://api.scraperapi.com"
        f"?api_key={SCRAPER_API_KEY}"
        f"&url={requests.utils.quote(reddit_url, safe='')}"
    )
    try:
        resp = requests.get(proxy_url, headers=HEADERS, timeout=60)
        if resp.status_code != 200:
            print(f"  [WARN] r/{sub}: HTTP {resp.status_code}")
            continue
        posts = resp.json().get("data", {}).get("children", [])
        count = 0
        for p in posts:
            d      = p.get("data", {})
            title  = d.get("title", "").strip()
            body   = d.get("selftext", "").strip()
            url_p  = "https://reddit.com" + d.get("permalink", "")
            author = d.get("author", "")
            if not title or body in ("", "[deleted]", "[removed]"):
                continue
            if len(body) > MAX_BODY_CHARS:
                body = body[:MAX_BODY_CHARS] + "..."
            raw_posts.append({
                "subreddit": sub, "title": title, "body": body,
                "url": url_p, "author": author
            })
            count += 1
        print(f"  [OK] r/{sub}: {count} posts collected")
        time.sleep(1)
    except Exception as e:
        print(f"  [ERROR] r/{sub}: {e}")

print(f"\n[STAGE 1] Total posts collected: {len(raw_posts)}")

if not raw_posts:
    print("[CRITICAL] No posts collected. Exiting.")
    sys.exit(1)

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

prompt = f"""You are an expert sales analyst for a digital marketing and automation agency.
Your client, Tal HaTil, sells 40 courses and services in web development, marketing automation, and lead generation.

Analyze the following {len(raw_posts)} Reddit posts and identify the TOP {TOP_LEADS} best potential leads.
A good lead is someone who:
- Needs help with: website building, digital marketing, automation, lead generation, online business growth
- Is actively asking for help or expressing frustration with their current situation
- Seems like a business owner, entrepreneur, or freelancer (not a student doing homework)

Return a JSON object with this exact structure (no markdown, no explanation outside the JSON):
{{
  "leads": [
    {{
      "rank": 1,
      "subreddit": "subreddit_name",
      "title": "post title",
      "url": "https://reddit.com/...",
      "author": "username",
      "score": 8,
      "priority": "HIGH",
      "reason": "One sentence explaining why this is a good lead"
    }}
  ],
  "summary": "2-3 sentence summary of today's scan results in Hebrew"
}}

Priority levels: HIGH (score 8-10), MEDIUM (score 5-7), LOW (score 1-4)

POSTS TO ANALYZE:
{posts_text}"""

from google import genai as genai_new
_gclient = genai_new.Client(api_key=GEMINI_API_KEY)

leads      = []
summary_he = "ניתוח ה-AI לא הצליח להשלים."
gemini_ok  = False

for attempt in range(GEMINI_RETRIES):
    try:
        print(f"  [INFO] Gemini attempt {attempt + 1}/{GEMINI_RETRIES}...")
        response = _gclient.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        raw_resp = response.text.strip()
        # Strip markdown code fences if present
        if raw_resp.startswith("```"):
            parts    = raw_resp.split("```")
            raw_resp = parts[1] if len(parts) > 1 else raw_resp
            if raw_resp.startswith("json"):
                raw_resp = raw_resp[4:]
        analysis   = json.loads(raw_resp)
        leads      = analysis.get("leads", [])
        summary_he = analysis.get("summary", "")
        print(f"[OK] Gemini returned {len(leads)} leads")
        print(f"[OK] Summary: {summary_he}")
        gemini_ok = True
        break
    except Exception as e:
        err_str = str(e)
        print(f"  [ERROR] Attempt {attempt + 1} failed: {type(e).__name__}: {err_str[:200]}")
        if attempt < GEMINI_RETRIES - 1:
            wait = GEMINI_BACKOFF[attempt]
            print(f"  [INFO] Waiting {wait}s before retry...")
            time.sleep(wait)

if not gemini_ok:
    print("[WARN] All Gemini attempts failed. Sending empty report.")
    summary_he = "ניתוח ה-AI נכשל לאחר מספר ניסיונות. ראה לוגים לפרטים."

# ── Stage 3: JSON Report ─────────────────────────────────────────────────────
print("\n[STAGE 3] Generating report...")

report = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "scan_stats": {
        "subreddits_scanned": SUBREDDITS,
        "total_posts_collected": len(raw_posts),
        "leads_identified": len(leads)
    },
    "ai_summary": summary_he,
    "leads": leads
}

with open(REPORT_PATH, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f"[OK] Report saved to {REPORT_PATH}")

# ── Stage 4: SMTP Email Delivery ─────────────────────────────────────────────
print("\n[STAGE 4] Sending email report...")

try:
    msg   = MIMEMultipart("mixed")
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    msg["Subject"] = f"🎯 Delta Agent – {len(leads)} לידים חדשים | {today}"
    msg["From"]    = SMTP_USER
    msg["To"]      = SMTP_TO

    leads_html = ""
    for lead in leads:
        color = {"HIGH": "#e74c3c", "MEDIUM": "#f39c12", "LOW": "#27ae60"}.get(
            lead.get("priority", "LOW"), "#888")
        leads_html += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee;font-weight:bold;">{lead.get('rank','')}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;">
            <a href="{lead.get('url','')}" style="color:#2980b9;">{lead.get('title','')}</a><br>
            <small>r/{lead.get('subreddit','')} · u/{lead.get('author','')}</small>
          </td>
          <td style="padding:8px;border-bottom:1px solid #eee;text-align:center;">
            <span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:12px;">
              {lead.get('priority','')}
            </span>
          </td>
          <td style="padding:8px;border-bottom:1px solid #eee;font-size:13px;">{lead.get('reason','')}</td>
        </tr>"""

    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;direction:rtl;text-align:right;">
      <h2 style="color:#2c3e50;">🎯 Delta Agent – דוח לידים יומי</h2>
      <p style="color:#7f8c8d;">{today} | {datetime.now(timezone.utc).strftime('%H:%M')} UTC</p>
      <div style="background:#ecf0f1;padding:15px;border-radius:8px;margin-bottom:20px;">
        <strong>סיכום:</strong> {summary_he}
      </div>
      <table style="width:100%;border-collapse:collapse;direction:ltr;text-align:left;">
        <thead>
          <tr style="background:#2c3e50;color:white;">
            <th style="padding:10px;">#</th>
            <th style="padding:10px;">פוסט</th>
            <th style="padding:10px;">עדיפות</th>
            <th style="padding:10px;">סיבה</th>
          </tr>
        </thead>
        <tbody>{leads_html}</tbody>
      </table>
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
        server.sendmail(SMTP_USER, SMTP_TO, msg.as_string())

    print("[OK] Email sent successfully")

except Exception as e:
    print(f"[ERROR] Email delivery failed: {e}")

# ── Done ──────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("DELTA AGENT – Run Complete")
print(f"Posts scanned : {len(raw_posts)}")
print(f"Leads found   : {len(leads)}")
print(f"Report saved  : {REPORT_PATH}")
print("=" * 60)
sys.exit(0)
