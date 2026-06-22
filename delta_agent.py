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
import re
import xml.etree.ElementTree as ET
import requests
from urllib.parse import urljoin
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

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

# ── Rate Limiting & Retry Config ─────────────────────────────────────────────
HTTP_RETRIES     = 3
HTTP_BACKOFF     = [5, 15, 30]       # seconds for HTTP retry backoff
RATE_LIMIT_DELAY = 60                # seconds to wait on 429 before retry

# HTTP Status Codes
HTTP_OK         = 200
HTTP_BAD_REQUEST    = 400
HTTP_UNAUTHORIZED   = 401
HTTP_FORBIDDEN      = 403
HTTP_NOT_FOUND      = 404
HTTP_RATE_LIMIT     = 429
HTTP_SERVER_ERROR   = 500

HEADERS = {
    "User-Agent": "DeltaAgent/1.0 (+https://github.com/infinityempire/delta-agent) "
                  "market-intelligence; contact: configured-repo-owner",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive"
}
REQUEST_TIMEOUT = 60

HTTP = requests.Session()
HTTP.headers.update(HEADERS)
# Do not inherit runner-level HTTP(S)_PROXY values. In earlier runs, Reddit
# fallback calls were sent through an environment proxy and failed with 403.
HTTP.trust_env = False

provider_diagnostics = []

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
print(f"[INFO] SCRAPINGBEE_API_KEY injected: {'yes' if SCRAPINGBEE_API_KEY else 'no'}")
print(f"[INFO] SCRAPER_API_KEY injected: {'yes' if SCRAPER_API_KEY else 'no'}")
if not SCRAPINGBEE_API_KEY:
    print("[WARN] SCRAPINGBEE_API_KEY not set. ScraperAPI will be used as the first proxy fallback.")
if not SCRAPER_API_KEY:
    print("[WARN] SCRAPER_API_KEY not set. Direct Reddit fallbacks will be used if ScrapingBee is unavailable.")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Stage 1: Reddit Scraper ──────────────────────────────────────────────────
print("\n[STAGE 1] Scraping Reddit via ScrapingBee → ScraperAPI → Jina → Reddit JSON/RSS/HTML...")

def _strip_markup(value):
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _diagnose_provider(subreddit, provider, status, detail=""):
    safe_detail = str(detail or "")[:180]
    provider_diagnostics.append({
        "subreddit": subreddit,
        "provider": provider,
        "status": status,
        "detail": safe_detail,
    })
    suffix = f": {safe_detail}" if safe_detail else ""
    level = "OK" if status == "ok" else "WARN"
    print(f"  [{level}] r/{subreddit}: {provider} {status}{suffix}")


def _get_status_error_name(status_code):
    """Return human-readable name for HTTP status codes"""
    status_names = {
        HTTP_BAD_REQUEST: "Bad Request",
        HTTP_UNAUTHORIZED: "Unauthorized",
        HTTP_FORBIDDEN: "Forbidden",
        HTTP_NOT_FOUND: "Not Found",
        HTTP_RATE_LIMIT: "Rate Limited",
        HTTP_SERVER_ERROR: "Server Error",
    }
    return status_names.get(status_code, f"HTTP {status_code}")


def _should_retry(status_code):
    """Determine if a status code warrants a retry"""
    return status_code in (
        HTTP_RATE_LIMIT,
        HTTP_SERVER_ERROR,
        502, 503, 504,  # Gateway/Service unavailable
    )


def _handle_http_error(subreddit, provider, status_code, attempt, max_retries):
    """Handle HTTP errors with appropriate messaging and retry logic"""
    error_name = _get_status_error_name(status_code)
    is_final_attempt = attempt >= max_retries - 1
    
    if status_code == HTTP_UNAUTHORIZED:
        _diagnose_provider(
            subreddit, provider, "auth-error",
            f"{error_name} - Check API key validity"
        )
        return False  # Don't retry auth errors
    
    elif status_code == HTTP_BAD_REQUEST:
        _diagnose_provider(
            subreddit, provider, "bad-request",
            f"{error_name} - Request validation failed"
        )
        return False  # Don't retry bad requests
    
    elif status_code == HTTP_FORBIDDEN:
        _diagnose_provider(
            subreddit, provider, "forbidden",
            f"{error_name} - Access denied, check permissions"
        )
        return False  # Don't retry forbidden
    
    elif status_code == HTTP_RATE_LIMIT:
        if is_final_attempt:
            # FIX: On final attempt with 429, fail gracefully - do NOT return True
            _diagnose_provider(
                subreddit, provider, "rate-limited",
                f"{error_name} - Final attempt, giving up after {max_retries} tries"
            )
            return False
        else:
            _diagnose_provider(
                subreddit, provider, "rate-limited",
                f"{error_name} - Waiting {RATE_LIMIT_DELAY}s before retry"
            )
            return True  # Retry after delay
    
    elif status_code >= HTTP_SERVER_ERROR:
        _diagnose_provider(
            subreddit, provider, "server-error",
            f"{error_name} - Will retry" if attempt < max_retries - 1 else f"{error_name} - Max retries reached"
        )
        return attempt < max_retries - 1  # Retry if we have attempts left
    
    else:
        _diagnose_provider(
            subreddit, provider, "http-error",
            f"HTTP {status_code}"
        )
        return False


def _normalize_post(subreddit, title, body, url, author=""):
    title = _strip_markup(title)
    body = _strip_markup(body)
    if not title:
        return None
    if body in ("[deleted]", "[removed]"):
        body = ""
    if not body:
        # Many Reddit JSON/RSS entries are link or title-only posts. The old
        # scraper discarded those, which could turn a valid scrape into 0 posts.
        body = "[title-only post]"
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
    children = payload.get("data", {}).get("children", [])
    for p in children:
        d = p.get("data", {})
        permalink = d.get("permalink", "")
        if permalink.startswith("http"):
            url = permalink
        else:
            url = "https://reddit.com" + permalink if permalink else d.get("url", "")
        body = d.get("selftext") or d.get("selftext_html") or ""
        if not body and d.get("crosspost_parent_list"):
            parent = d["crosspost_parent_list"][0]
            body = parent.get("selftext") or parent.get("selftext_html") or ""
        normalized = _normalize_post(
            subreddit=subreddit,
            title=d.get("title", ""),
            body=body,
            url=url,
            author=d.get("author", ""),
        )
        if normalized:
            posts.append(normalized)
    return posts


def _json_from_response(resp, subreddit, provider):
    try:
        return resp.json()
    except ValueError as exc:
        ctype = resp.headers.get("content-type", "unknown")
        _diagnose_provider(
            subreddit,
            provider,
            "bad-json",
            f"HTTP {resp.status_code}, content-type={ctype}",
        )
        raise ValueError(f"{provider} returned non-JSON content") from exc


def _posts_from_old_reddit_html(subreddit, html_text):
    posts = []
    # old.reddit.com renders each listing as a thing with a stable title anchor.
    pattern = re.compile(
        r'<a[^>]+class="[^"]*\btitle\b[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for href, title_html in pattern.findall(html_text or ""):
        title = _strip_markup(title_html)
        if not title or title.lower() in {"next", "previous"}:
            continue
        url = urljoin("https://old.reddit.com", html.unescape(href))
        normalized = _normalize_post(
            subreddit=subreddit,
            title=title,
            body="[title-only post from Reddit listing]",
            url=url,
            author="",
        )
        if normalized:
            posts.append(normalized)
        if len(posts) >= POSTS_PER_SUB:
            break
    return posts


def _posts_from_jina_markdown(subreddit, markdown_text):
    posts = []
    pattern = re.compile(
        rf'\[([^\]]{{8,200}})\]\((https?://(?:old\.)?reddit\.com/r/{re.escape(subreddit)}/comments/[^)]+)\)',
        re.IGNORECASE,
    )
    for title, url in pattern.findall(markdown_text or ""):
        title = _strip_markup(title)
        if not title or title.lower() in {"comments", "permalink", "source"}:
            continue
        normalized = _normalize_post(
            subreddit=subreddit,
            title=title,
            body="[title-only post from Jina Reader Reddit listing]",
            url=url,
            author="",
        )
        if normalized:
            posts.append(normalized)
        if len(posts) >= POSTS_PER_SUB:
            break
    return posts


def _scrapingbee_get(subreddit, provider, target_url, render_js="false"):
    """Fetch URL via ScrapingBee with retry and backoff"""
    for attempt in range(HTTP_RETRIES):
        try:
            resp = HTTP.get(
                "https://app.scrapingbee.com/api/v1/",
                params={
                    "api_key": SCRAPINGBEE_API_KEY,
                    "url": target_url,
                    "render_js": render_js,
                    "premium_proxy": "true",
                    "country_code": "us",
                },
                timeout=REQUEST_TIMEOUT,
            )
            
            if resp.status_code == HTTP_OK:
                return resp
            
            # Handle error with retry logic
            should_retry = _handle_http_error(
                subreddit, provider, resp.status_code, attempt, HTTP_RETRIES
            )
            
            if not should_retry:
                return None
            
            # Apply backoff delay
            if resp.status_code == HTTP_RATE_LIMIT:
                wait_time = RATE_LIMIT_DELAY
            else:
                wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
            
            print(f"  [INFO] Waiting {wait_time}s before retry ({attempt + 1}/{HTTP_RETRIES})...")
            time.sleep(wait_time)
            
        except requests.exceptions.Timeout:
            _diagnose_provider(subreddit, provider, "timeout", "Request timed out")
            if attempt < HTTP_RETRIES - 1:
                wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
                print(f"  [INFO] Retrying after timeout ({attempt + 1}/{HTTP_RETRIES})...")
                time.sleep(wait_time)
            else:
                return None
        except requests.exceptions.RequestException as e:
            # FIX: Transient errors (connection reset, DNS failures) should retry
            # instead of aborting immediately
            _diagnose_provider(subreddit, provider, "connection-error", str(e)[:100])
            if attempt < HTTP_RETRIES - 1:
                wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
                print(f"  [INFO] Retrying after connection error ({attempt + 1}/{HTTP_RETRIES})...")
                time.sleep(wait_time)
            else:
                return None
    
    return None


def _scraperapi_get(subreddit, provider, target_url, render="false"):
    """Fetch URL via ScraperAPI with retry and backoff"""
    for attempt in range(HTTP_RETRIES):
        try:
            resp = HTTP.get(
                "http://api.scraperapi.com",
                params={
                    "api_key": SCRAPER_API_KEY,
                    "url": target_url,
                    "country_code": "us",
                    "render": render,
                },
                timeout=REQUEST_TIMEOUT,
            )
            
            if resp.status_code == HTTP_OK:
                return resp
            
            # Handle error with retry logic
            should_retry = _handle_http_error(
                subreddit, provider, resp.status_code, attempt, HTTP_RETRIES
            )
            
            if not should_retry:
                return None
            
            # Apply backoff delay
            if resp.status_code == HTTP_RATE_LIMIT:
                wait_time = RATE_LIMIT_DELAY
            else:
                wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
            
            print(f"  [INFO] Waiting {wait_time}s before retry ({attempt + 1}/{HTTP_RETRIES})...")
            time.sleep(wait_time)
            
        except requests.exceptions.Timeout:
            _diagnose_provider(subreddit, provider, "timeout", "Request timed out")
            if attempt < HTTP_RETRIES - 1:
                wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
                print(f"  [INFO] Retrying after timeout ({attempt + 1}/{HTTP_RETRIES})...")
                time.sleep(wait_time)
            else:
                return None
        except requests.exceptions.RequestException as e:
            # FIX: Transient errors (connection reset, DNS failures) should retry
            # instead of aborting immediately
            _diagnose_provider(subreddit, provider, "connection-error", str(e)[:100])
            if attempt < HTTP_RETRIES - 1:
                wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
                print(f"  [INFO] Retrying after connection error ({attempt + 1}/{HTTP_RETRIES})...")
                time.sleep(wait_time)
            else:
                return None
    
    return None


def _fetch_with_scrapingbee(subreddit):
    provider = "ScrapingBee JSON"
    if not SCRAPINGBEE_API_KEY:
        _diagnose_provider(subreddit, provider, "skipped", "SCRAPINGBEE_API_KEY not injected")
        return []
    reddit_url = f"https://www.reddit.com/r/{subreddit}/new.json?raw_json=1&limit={POSTS_PER_SUB}"
    resp = _scrapingbee_get(subreddit, provider, reddit_url, render_js="false")
    if resp is None:
        return []
    posts = _posts_from_reddit_json(subreddit, _json_from_response(resp, subreddit, provider))
    _diagnose_provider(subreddit, provider, "ok", f"{len(posts)} usable posts")
    return posts


def _fetch_with_scrapingbee_old_html(subreddit):
    provider = "ScrapingBee old Reddit HTML"
    if not SCRAPINGBEE_API_KEY:
        _diagnose_provider(subreddit, provider, "skipped", "SCRAPINGBEE_API_KEY not injected")
        return []
    reddit_url = f"https://old.reddit.com/r/{subreddit}/new/"
    resp = _scrapingbee_get(subreddit, provider, reddit_url, render_js="false")
    if resp is None:
        return []
    posts = _posts_from_old_reddit_html(subreddit, resp.text)
    _diagnose_provider(subreddit, provider, "ok", f"{len(posts)} usable posts")
    return posts


def _fetch_with_scrapingbee_rendered_markdown(subreddit):
    """Fetch posts via ScrapingBee rendered markdown with retry and backoff"""
    provider = "ScrapingBee rendered Reddit markdown"
    if not SCRAPINGBEE_API_KEY:
        _diagnose_provider(subreddit, provider, "skipped", "SCRAPINGBEE_API_KEY not injected")
        return []
    reddit_url = f"https://www.reddit.com/r/{subreddit}/new/"

    for attempt in range(HTTP_RETRIES):
        try:
            resp = HTTP.get(
                "https://app.scrapingbee.com/api/v1/",
                params={
                    "api_key": SCRAPINGBEE_API_KEY,
                    "url": reddit_url,
                    "render_js": "true",
                    "stealth_proxy": "true",
                    "country_code": "us",
                    "return_page_markdown": "true",
                    "wait": "5000",
                },
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code == HTTP_OK:
                posts = _posts_from_jina_markdown(subreddit, resp.text)
                if not posts:
                    posts = _posts_from_old_reddit_html(subreddit, resp.text)
                _diagnose_provider(subreddit, provider, "ok", f"{len(posts)} usable posts")
                return posts

            should_retry = _handle_http_error(
                subreddit, provider, resp.status_code, attempt, HTTP_RETRIES
            )
            if not should_retry:
                return []

            if resp.status_code == HTTP_RATE_LIMIT:
                wait_time = RATE_LIMIT_DELAY
            else:
                wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]

            print(f"  [INFO] Waiting {wait_time}s before retry ({attempt + 1}/{HTTP_RETRIES})...")
            time.sleep(wait_time)

        except requests.exceptions.Timeout:
            _diagnose_provider(subreddit, provider, "timeout", "Request timed out")
            if attempt < HTTP_RETRIES - 1:
                time.sleep(HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)])
            else:
                return []
        except requests.exceptions.RequestException as e:
            # FIX: Transient errors (connection reset, DNS failures) should retry
            # instead of aborting immediately
            _diagnose_provider(subreddit, provider, "connection-error", str(e)[:100])
            if attempt < HTTP_RETRIES - 1:
                wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
                print(f"  [INFO] Retrying after connection error ({attempt + 1}/{HTTP_RETRIES})...")
                time.sleep(wait_time)
            else:
                return []

    return []


def _fetch_with_scraperapi(subreddit):
    provider = "ScraperAPI JSON"
    if not SCRAPER_API_KEY:
        _diagnose_provider(subreddit, provider, "skipped", "SCRAPER_API_KEY not injected")
        return []
    reddit_url = f"https://www.reddit.com/r/{subreddit}/new.json?raw_json=1&limit={POSTS_PER_SUB}"
    resp = _scraperapi_get(subreddit, provider, reddit_url, render="false")
    if resp is None:
        return []
    posts = _posts_from_reddit_json(subreddit, _json_from_response(resp, subreddit, provider))
    _diagnose_provider(subreddit, provider, "ok", f"{len(posts)} usable posts")
    return posts


def _fetch_with_scraperapi_old_html(subreddit):
    provider = "ScraperAPI old Reddit HTML"
    if not SCRAPER_API_KEY:
        _diagnose_provider(subreddit, provider, "skipped", "SCRAPER_API_KEY not injected")
        return []
    reddit_url = f"https://old.reddit.com/r/{subreddit}/new/"
    resp = _scraperapi_get(subreddit, provider, reddit_url, render="false")
    if resp is None:
        return []
    posts = _posts_from_old_reddit_html(subreddit, resp.text)
    _diagnose_provider(subreddit, provider, "ok", f"{len(posts)} usable posts")
    return posts


def _fetch_with_jina_reader(subreddit):
    """Fetch posts via Jina Reader with retry and backoff"""
    provider = "Jina Reader old Reddit"
    reader_url = f"https://r.jina.ai/https://old.reddit.com/r/{subreddit}/new/"
    
    for attempt in range(HTTP_RETRIES):
        try:
            resp = HTTP.get(reader_url, timeout=REQUEST_TIMEOUT)
            
            if resp.status_code == HTTP_OK:
                posts = _posts_from_jina_markdown(subreddit, resp.text)
                _diagnose_provider(subreddit, provider, "ok", f"{len(posts)} usable posts")
                return posts
            
            should_retry = _handle_http_error(
                subreddit, provider, resp.status_code, attempt, HTTP_RETRIES
            )
            
            if not should_retry:
                return []
            
            wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
            print(f"  [INFO] Waiting {wait_time}s before retry ({attempt + 1}/{HTTP_RETRIES})...")
            time.sleep(wait_time)
            
        except requests.exceptions.Timeout:
            _diagnose_provider(subreddit, provider, "timeout", "Request timed out")
            if attempt < HTTP_RETRIES - 1:
                time.sleep(HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)])
            else:
                return []
        except requests.exceptions.RequestException as e:
            # FIX: Transient errors (connection reset, DNS failures) should retry
            # instead of aborting immediately
            _diagnose_provider(subreddit, provider, "connection-error", str(e)[:100])
            if attempt < HTTP_RETRIES - 1:
                wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
                print(f"  [INFO] Retrying after connection error ({attempt + 1}/{HTTP_RETRIES})...")
                time.sleep(wait_time)
            else:
                return []
    
    return []


def _fetch_with_reddit_json(subreddit):
    """Fetch posts via Reddit JSON API with retry and backoff"""
    provider = "Reddit JSON"
    reddit_url = f"https://www.reddit.com/r/{subreddit}/new.json?raw_json=1&limit={POSTS_PER_SUB}"
    
    for attempt in range(HTTP_RETRIES):
        try:
            resp = HTTP.get(reddit_url, timeout=REQUEST_TIMEOUT)
            
            if resp.status_code == HTTP_OK:
                posts = _posts_from_reddit_json(subreddit, _json_from_response(resp, subreddit, provider))
                _diagnose_provider(subreddit, provider, "ok", f"{len(posts)} usable posts")
                return posts
            
            should_retry = _handle_http_error(
                subreddit, provider, resp.status_code, attempt, HTTP_RETRIES
            )
            
            if not should_retry:
                return []
            
            wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
            print(f"  [INFO] Waiting {wait_time}s before retry ({attempt + 1}/{HTTP_RETRIES})...")
            time.sleep(wait_time)
            
        except requests.exceptions.Timeout:
            _diagnose_provider(subreddit, provider, "timeout", "Request timed out")
            if attempt < HTTP_RETRIES - 1:
                time.sleep(HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)])
            else:
                return []
        except requests.exceptions.RequestException as e:
            # FIX: Transient errors (connection reset, DNS failures) should retry
            # instead of aborting immediately
            _diagnose_provider(subreddit, provider, "connection-error", str(e)[:100])
            if attempt < HTTP_RETRIES - 1:
                wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
                print(f"  [INFO] Retrying after connection error ({attempt + 1}/{HTTP_RETRIES})...")
                time.sleep(wait_time)
            else:
                return []
    
    return []


def _fetch_with_reddit_rss(subreddit):
    """Fetch posts via Reddit RSS with retry and backoff"""
    provider = "Reddit RSS"
    rss_url = f"https://www.reddit.com/r/{subreddit}/new/.rss?limit={POSTS_PER_SUB}"
    
    for attempt in range(HTTP_RETRIES):
        try:
            resp = HTTP.get(rss_url, timeout=REQUEST_TIMEOUT)
            
            if resp.status_code == HTTP_OK:
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
                        title=title,
                        body=body,
                        url=url,
                        author=author,
                    )
                    if normalized:
                        posts.append(normalized)
                _diagnose_provider(subreddit, provider, "ok", f"{len(posts)} usable posts")
                return posts
            
            should_retry = _handle_http_error(
                subreddit, provider, resp.status_code, attempt, HTTP_RETRIES
            )
            
            if not should_retry:
                return []
            
            wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
            print(f"  [INFO] Waiting {wait_time}s before retry ({attempt + 1}/{HTTP_RETRIES})...")
            time.sleep(wait_time)
            
        except requests.exceptions.Timeout:
            _diagnose_provider(subreddit, provider, "timeout", "Request timed out")
            if attempt < HTTP_RETRIES - 1:
                time.sleep(HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)])
            else:
                return []
        except requests.exceptions.RequestException as e:
            # FIX: Transient errors (connection reset, DNS failures) should retry
            # instead of aborting immediately
            _diagnose_provider(subreddit, provider, "connection-error", str(e)[:100])
            if attempt < HTTP_RETRIES - 1:
                wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
                print(f"  [INFO] Retrying after connection error ({attempt + 1}/{HTTP_RETRIES})...")
                time.sleep(wait_time)
            else:
                return []
        except ET.ParseError as e:
            _diagnose_provider(subreddit, provider, "parse-error", f"RSS parse error: {str(e)[:50]}")
            return []
    
    return []


def _fetch_with_old_reddit_html(subreddit):
    """Fetch posts via old Reddit HTML with retry and backoff"""
    provider = "Old Reddit HTML"
    reddit_url = f"https://old.reddit.com/r/{subreddit}/new/"
    
    for attempt in range(HTTP_RETRIES):
        try:
            resp = HTTP.get(reddit_url, timeout=REQUEST_TIMEOUT)
            
            if resp.status_code == HTTP_OK:
                posts = _posts_from_old_reddit_html(subreddit, resp.text)
                _diagnose_provider(subreddit, provider, "ok", f"{len(posts)} usable posts")
                return posts
            
            should_retry = _handle_http_error(
                subreddit, provider, resp.status_code, attempt, HTTP_RETRIES
            )
            
            if not should_retry:
                return []
            
            wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
            print(f"  [INFO] Waiting {wait_time}s before retry ({attempt + 1}/{HTTP_RETRIES})...")
            time.sleep(wait_time)
            
        except requests.exceptions.Timeout:
            _diagnose_provider(subreddit, provider, "timeout", "Request timed out")
            if attempt < HTTP_RETRIES - 1:
                time.sleep(HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)])
            else:
                return []
        except requests.exceptions.RequestException as e:
            # FIX: Transient errors (connection reset, DNS failures) should retry
            # instead of aborting immediately
            _diagnose_provider(subreddit, provider, "connection-error", str(e)[:100])
            if attempt < HTTP_RETRIES - 1:
                wait_time = HTTP_BACKOFF[min(attempt, len(HTTP_BACKOFF) - 1)]
                print(f"  [INFO] Retrying after connection error ({attempt + 1}/{HTTP_RETRIES})...")
                time.sleep(wait_time)
            else:
                return []
    
    return []


raw_posts = []
seen_urls = set()
for sub in SUBREDDITS:
    providers = (
        ("ScrapingBee JSON", _fetch_with_scrapingbee),
        ("ScrapingBee old Reddit HTML", _fetch_with_scrapingbee_old_html),
        ("ScrapingBee rendered Reddit markdown", _fetch_with_scrapingbee_rendered_markdown),
        ("ScraperAPI JSON", _fetch_with_scraperapi),
        ("ScraperAPI old Reddit HTML", _fetch_with_scraperapi_old_html),
        ("Jina Reader old Reddit", _fetch_with_jina_reader),
        ("Reddit JSON", _fetch_with_reddit_json),
        ("Reddit RSS", _fetch_with_reddit_rss),
        ("Old Reddit HTML", _fetch_with_old_reddit_html),
    )
    collected = []
    for provider_name, fetch_posts in providers:
        try:
            collected = fetch_posts(sub)
            if collected:
                for post in collected:
                    key = post.get("url") or f"{post['subreddit']}::{post['title']}"
                    if key not in seen_urls:
                        seen_urls.add(key)
                        raw_posts.append(post)
                print(f"  [OK] r/{sub}: {len(collected)} posts collected via {provider_name}")
                break
        except Exception as e:
            _diagnose_provider(sub, provider_name, "exception", f"{type(e).__name__}: {e}")
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
- Always include the following link as a call-to-action to support the Tal HaTil Empire: https://www.paypal.me/talderie

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
        "leads_identified": len(leads),
        "scrapingbee_key_injected": bool(SCRAPINGBEE_API_KEY),
        "scraperapi_key_injected": bool(SCRAPER_API_KEY),
    },
    "provider_diagnostics": provider_diagnostics,
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
        server.sendmail(SMTP_USER, SMTP_TO, msg.as_string())

    email_sent = True
    print("[OK] Email sent successfully")

except Exception as e:
    print(f"[ERROR] Email delivery failed: {e}")
    # Write failure marker to output for notification tracking
    with open(f"{OUTPUT_DIR}/email_failure.json", "w") as f:
        json.dump({
            "error": str(e),
            "type": "email_delivery_failed",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, f)

# ── Done ──────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("DELTA AGENT – Run Complete")
print(f"Posts scanned : {len(raw_posts)}")
print(f"Intent opportunities: {len(leads)}")
print(f"Report saved  : {REPORT_PATH}")
print(f"Email sent    : {email_sent}")
print("=" * 60)

# Provide diagnostic summary for debugging
if provider_diagnostics:
    failed_providers = [p for p in provider_diagnostics if p["status"] != "ok"]
    if failed_providers:
        print(f"\n[DIAGNOSTIC] {len(failed_providers)} provider(s) had issues:")
        for p in failed_providers[:5]:  # Show first 5
            print(f"  - {p['provider']} on r/{p['subreddit']}: {p['status']} - {p['detail']}")

# Exit with failure only if critical components failed
if not email_sent:
    print("\n[CRITICAL] Email delivery failed - workflow will be marked as failed")
    sys.exit(1)
sys.exit(0)
