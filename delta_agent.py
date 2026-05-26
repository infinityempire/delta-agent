"""
Delta Agent – Automated Lead Hunter for Tal HaTil
==================================================
Stage 1: Live Reddit Scraper
Stage 2: Gemini AI Analysis
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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SMTP_HOST      = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER      = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD  = os.environ.get("SMTP_PASSWORD", "")
SMTP_TO        = os.environ.get("SMTP_TO", "")

# ── Config ───────────────────────────────────────────────────────────────────
SUBREDDITS = ["entrepreneur", "startups", "smallbusiness", "forhire", "freelance"]
POSTS_PER_SUB = 25
MAX_BODY_CHARS = 1500
TOP_LEADS = 10
OUTPUT_DIR = "output"
REPORT_PATH = f"{OUTPUT_DIR}/execution_report.json"

HEADERS = {
    "User-Agent": "DeltaAgent/1.0 (lead-hunter bot; contact: tal.derie.td@gmail.com)"
}

# ── Startup Checks ───────────────────────────────────────────────────────────
print("=" * 60)
print("DELTA AGENT – Starting Up")
print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
print("=" * 60)

missing = []
if not GEMINI_API_KEY: missing.append("GEMINI_API_KEY")
if not SMTP_USER:      missing.append("SMTP_USER")
if not SMTP_PASSWORD:  missing.append("SMTP_PASSWORD")
if not SMTP_TO:        missing.append("SMTP_TO")

if missing:
    print(f"[CRITICAL] Missing environment variables: {missing}")
    print("[CRITICAL] Cannot proceed without required secrets. Exiting.")
    sys.exit(1)

print(f"[OK] All required env vars present")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Stage 1: Reddit Scraper ──────────────────────────────────────────────────
print("\n[STAGE 1] Scraping Reddit...")

raw_posts = []
for sub in SUBREDDITS:
    url = f"https://www.reddit.com/r/{sub}/new.json?limit={POSTS_PER_SUB}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"  [WARN] r/{sub}: HTTP {resp.status_code}")
            continue
        data = resp.json()
        posts = data.get("data", {}).get("children", [])
        count = 0
        for p in posts:
            d = p.get("data", {})
            title = d.get("title", "").strip()
            body  = d.get("selftext", "").strip()
            url_p = "https://reddit.com" + d.get("permalink", "")
            author = d.get("author", "")
            score  = d.get("score", 0)
            # Filter: skip empty, deleted, or too-long posts
            if not title or body in ("", "[deleted]", "[removed]"):
                continue
            if len(body) > MAX_BODY_CHARS:
                body = body[:MAX_BODY_CHARS] + "..."
            raw_posts.append({
                "subreddit": sub,
                "title": title,
                "body": body,
                "url": url_p,
                "author": author,
                "score": score
            })
            count += 1
        print(f"  [OK] r/{sub}: {count} posts collected")
        time.sleep(1)  # Be polite to Reddit
    except Exception as e:
        print(f"  [ERROR] r/{sub}: {e}")

print(f"\n[STAGE 1] Total posts collected: {len(raw_posts)}")

if not raw_posts:
    print("[CRITICAL] No posts collected from Reddit. Exiting.")
    sys.exit(1)

# ── Stage 2: Gemini AI Analysis ──────────────────────────────────────────────
print("\n[STAGE 2] Analyzing with Gemini AI...")

# Build the prompt
posts_text = ""
for i, p in enumerate(raw_posts):
    posts_text += f"\n--- Post {i+1} ---\n"
    posts_text += f"Subreddit: r/{p['subreddit']}\n"
    posts_text += f"Title: {p['title']}\n"
    posts_text += f"Body: {p['body']}\n"
    posts_text += f"URL: {p['url']}\n"
    posts_text += f"Author: {p['author']}\n"

prompt = f"""You are an expert sales analyst for a digital marketing and automation agency.
Your client, Tal HaTil, sells 40 courses and services in web development, marketing automation, and lead generation.

Analyze the following {len(raw_posts)} Reddit posts and identify the TOP {TOP_LEADS} best potential leads.
A good lead is someone who:
- Needs help with: website building, digital marketing, automation, lead generation, online business growth
- Is actively asking for help or expressing frustration with their current situation
- Seems like a business owner, entrepreneur, or freelancer (not a student doing homework)

For each of the top {TOP_LEADS} leads, return a JSON array with this exact structure:
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
Score = how likely this person needs Tal HaTil's services (1-10)

POSTS TO ANALYZE:
{posts_text}

Return ONLY valid JSON, no markdown, no explanation outside the JSON."""

try:
    # Use the new google-genai SDK
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    raw_response = response.text.strip()
    # Strip markdown code blocks if present
    if raw_response.startswith("```"):
        raw_response = raw_response.split("```")[1]
        if raw_response.startswith("json"):
            raw_response = raw_response[4:]
    analysis = json.loads(raw_response)
    leads = analysis.get("leads", [])
    summary_he = analysis.get("summary", "")
    print(f"[OK] Gemini returned {len(leads)} leads")
    print(f"[OK] Summary: {summary_he}")
except Exception as e:
    print(f"[ERROR] Gemini analysis failed: {e}")
    leads = []
    summary_he = "ניתוח ה-AI נכשל. ראה לוגים לפרטים."

# ── Stage 3: JSON Report ─────────────────────────────────────────────────────
print("\n[STAGE 3] Generating execution report...")

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
    msg = MIMEMultipart("mixed")
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    msg["Subject"] = f"🎯 Delta Agent – {len(leads)} לידים חדשים | {today}"
    msg["From"]    = SMTP_USER
    msg["To"]      = SMTP_TO

    # Build HTML body
    leads_html = ""
    for lead in leads:
        priority_color = {"HIGH": "#e74c3c", "MEDIUM": "#f39c12", "LOW": "#27ae60"}.get(lead.get("priority", "LOW"), "#888")
        leads_html += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee;font-weight:bold;">{lead.get('rank','')}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;">
            <a href="{lead.get('url','')}" style="color:#2980b9;">{lead.get('title','')}</a><br>
            <small>r/{lead.get('subreddit','')} · u/{lead.get('author','')}</small>
          </td>
          <td style="padding:8px;border-bottom:1px solid #eee;text-align:center;">
            <span style="background:{priority_color};color:white;padding:2px 8px;border-radius:4px;font-size:12px;">{lead.get('priority','')}</span>
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
        סה"כ נסרקו: {len(raw_posts)} פוסטים מ-{len(SUBREDDITS)} subreddits | 
        קובץ JSON מלא מצורף
      </p>
    </body></html>"""

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Attach JSON report
    with open(REPORT_PATH, "rb") as f:
        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(f.read())
        encoders.encode_base64(attachment)
        attachment.add_header("Content-Disposition", f"attachment; filename=delta_report_{today.replace('/','_')}.json")
        msg.attach(attachment)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, SMTP_TO, msg.as_string())

    print(f"[OK] Email sent to {SMTP_TO}")

except Exception as e:
    print(f"[ERROR] Email delivery failed: {e}")
    # Don't exit with error – report was still generated

# ── Done ─────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"DELTA AGENT – Run Complete")
print(f"Posts scanned : {len(raw_posts)}")
print(f"Leads found   : {len(leads)}")
print(f"Report saved  : {REPORT_PATH}")
print("=" * 60)
sys.exit(0)
