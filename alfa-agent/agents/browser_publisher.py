"""
Browser-based Publishing Engine using Playwright + PRAW hybrid.
Primary: Browser automation with proxy
Fallback: PRAW API when browser fails

Supports Residential Proxy for bypassing anti-bot detection.
"""
import asyncio
import random
import sys
import os
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, Browser, Page
except ImportError:
    print("ERROR: Playwright not installed. Run: pip install playwright && python -m playwright install chromium")
    sys.exit(1)

# Try importing PRAW for fallback
try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False
    print("WARNING: PRAW not installed. Browser-only mode active.")

from config.settings import PUBLISHING_CONFIG, REDDIT_CONFIG
from utils.logger import logger
from utils.state import state_manager


class BrowserPublisher:
    """
    Browser-based Reddit publisher using Playwright.
    Supports Residential Proxy for bypassing anti-bot detection.
    
    Requires:
    - REDDIT_USERNAME
    - REDDIT_PASSWORD
    
    Optional (for proxy):
    - REDDIT_PROXY_SERVER - Proxy URL (e.g., "http://proxy.example.com:8080")
    - REDDIT_PROXY_USERNAME - Proxy username
    - REDDIT_PROXY_PASSWORD - Proxy password
    """

    BASE_URL = "https://www.reddit.com"
    LOGIN_URL = f"{BASE_URL}/login"

    WARMUP_COMMENTS = [
        "Great point! I've been thinking about this too.",
        "This is interesting, thanks for sharing!",
        "I can relate to this. Well said!",
        "Thanks for the insight!",
        "That's a fair take. Appreciate the perspective.",
        "Interesting! Never thought about it that way.",
        "Good observation. Thanks for bringing this up!",
        "I agree with this. Well explained!",
        "Nice one! Thanks for posting this.",
        "Very true! I've had similar experiences.",
    ]

    def __init__(
        self,
        username: str,
        password: str,
        mock_mode: bool = False,
        headless: bool = True,
        comments_per_round: int = 3,
        proxy_server: str = None,
        proxy_username: str = None,
        proxy_password: str = None
    ):
        self.username = username
        self.password = password
        self.mock_mode = mock_mode
        self.headless = headless
        self.comments_per_round = comments_per_round

        # Proxy settings from args or environment variables
        self.proxy_server = proxy_server or os.environ.get("REDDIT_PROXY_SERVER")
        self.proxy_username = proxy_username or os.environ.get("REDDIT_PROXY_USERNAME")
        self.proxy_password = proxy_password or os.environ.get("REDDIT_PROXY_PASSWORD")

        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self._playwright = None
        self._logged_in = False

    def log(self, message: str, level: str = "info"):
        prefix = "[DRY-RUN]" if self.mock_mode else "[LIVE]"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"{prefix} [{timestamp}] {message}")

    def _rotate_tor_circuit(self):
        """Request a new Tor circuit to get a fresh IP."""
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect(('127.0.0.1', 9051))
            s.sendall(b'AUTHENTICATE ""\r\n')
            time.sleep(0.5)
            s.sendall(b'SIGNAL NEWNYM\r\n')
            time.sleep(0.5)
            s.sendall(b'QUIT\r\n')
            response = s.recv(1024).decode('utf-8', errors='ignore')
            s.close()
            self.log(f"Tor circuit rotated — new IP assigned (response: {response[:50]})")
            time.sleep(8)  # Wait for new circuit to establish
        except Exception as e:
            self.log(f"Could not rotate Tor circuit (ControlPort): {e} — waiting for natural rotation", "warning")
            time.sleep(10)  # Wait longer for natural IP change

    def _initialize_browser(self, use_proxy: bool = True) -> bool:
        """Initialize Playwright browser with stealth settings."""
        try:
            self.log("Launching browser with stealth settings...")
            self._playwright = sync_playwright().start()
            
            launch_options = {"headless": self.headless}
            
            # Tor proxy (only when USE_TOR=true, disabled for self-hosted runner)
            tor_proxy = os.environ.get("TOR_PROXY", "socks5://127.0.0.1:9050")
            use_tor = os.environ.get("USE_TOR", "false").lower() == "true"
            
            proxy_configured = False
            if use_tor and use_proxy:
                self.log(f"Using Tor SOCKS5 proxy: {tor_proxy}")
                proxy_configured = True
                launch_options["proxy"] = {
                    "server": tor_proxy,
                }
            elif use_proxy and self.proxy_server:
                # Fallback to paid proxy if Tor not available
                self.log(f"Using residential proxy: {self.proxy_server}")
                proxy_configured = True
                launch_options["proxy"] = {
                    "server": self.proxy_server,
                }
                if self.proxy_username and self.proxy_password:
                    launch_options["proxy"]["username"] = self.proxy_username
                    launch_options["proxy"]["password"] = self.proxy_password
            
            self.browser = self._playwright.chromium.launch(**launch_options)

            # Stealth context options to avoid detection
            context_options = {
                # Rotate user agent
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "viewport": {"width": 1920, "height": 1080},
                "locale": "en-US",
                "timezone_id": "Europe/London",
                "geolocation": {"latitude": 51.5074, "longitude": -0.1278},  # London
                "permissions": ["geolocation"],
            }
            
            if proxy_configured and self.proxy_username and self.proxy_password:
                context_options["proxy"] = {
                    "server": self.proxy_server,
                    "username": self.proxy_username,
                    "password": self.proxy_password,
                }
            
            context = self.browser.new_context(**context_options)
            
            self.page = context.new_page()
            
            # Add extra headers to appear more human-like
            self.page.set_extra_http_headers({
                "Accept-Language": "en-GB,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            })

            self.log("Browser launched successfully with stealth settings")
            return True

        except Exception as e:
            self.log(f"Failed to launch browser: {e}", "error")
            return False

    def _close_browser(self):
        if self.browser:
            try:
                self.browser.close()
            except:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except:
                pass
        self.browser = None
        self.page = None
        self._playwright = None

    def login(self, max_retries: int = 5) -> bool:
        """Log in to Reddit using browser automation with Tor retry logic."""
        last_error = None
        use_proxy = True  # Always try with Tor first

        for attempt in range(1, max_retries + 1):
            self._close_browser()

            if not self._initialize_browser(use_proxy=use_proxy):
                last_error = "Failed to initialize browser"
                continue

            if self.mock_mode:
                self.log(f"DRY-RUN: Would login as {self.username}")
                self._logged_in = True
                return True

            try:
                self.log(f"Navigating to login page (attempt {attempt}/{max_retries})...")
                
                # Navigate to Reddit main page first, then click login
                self.log("Navigating to Reddit main page...")
                self.page.goto(self.BASE_URL, timeout=90000)
                time.sleep(3)
                
                # Check if already logged in (check for username in header)
                logged_in_indicator = self.page.query_selector(f'a[href="/user/{self.username}"]')
                if logged_in_indicator:
                    self.log(f"Already logged in as {self.username}!")
                    self._logged_in = True
                    return True
                
                # Click login button if present
                login_btn = self.page.query_selector('a[href*="login"], button:has-text("Log In"), a:has-text("Log In")')
                if login_btn:
                    self.log("Clicking login button...")
                    login_btn.click()
                    time.sleep(3)
                
                # Wait for page to settle
                time.sleep(5)
                
                # Check for Cloudflare or challenge pages
                page_url = self.page.url.lower()
                if "challenge" in page_url or self.page.query_selector("#challenge-title"):
                    self.log(f"Detected Cloudflare challenge on attempt {attempt}! Rotating Tor circuit...")
                    self._rotate_tor_circuit()
                    continue  # Retry with new Tor IP
                
                self.log(f"Current URL: {self.page.url}")
                self.log(f"Page title: {self.page.title()}")
                
                # Try multiple selectors for the username field
                username_selectors = [
                    'input[name="username"]',
                    'input[id="loginUsername"]',
                    '#loginUsername',
                    'input[placeholder*="username" i]',
                    'input[data-testid="login-username"]',
                    'input[type="text"]',
                    'input.InputElement',
                ]
                
                username_field = None
                for selector in username_selectors:
                    try:
                        self.page.wait_for_selector(selector, timeout=10000, state="attached")
                        username_field = self.page.query_selector(selector)
                        if username_field:
                            self.log(f"Found username field with selector: {selector}")
                            break
                    except:
                        continue
                
                if not username_field:
                    self.log("Could not find username field — rotating Tor circuit...", "error")
                    self._rotate_tor_circuit()
                    continue
                
                self.log(f"Entering username: {self.username}")
                username_field.click()
                username_field.fill(self.username)
                time.sleep(0.5)
                
                # Try multiple selectors for password
                password_selectors = [
                    'input[name="password"]',
                    'input[id="loginPassword"]',
                    '#loginPassword',
                    'input[placeholder*="password" i]'
                ]
                
                for selector in password_selectors:
                    try:
                        password_field = self.page.query_selector(selector)
                        if password_field:
                            self.log(f"Found password field with selector: {selector}")
                            password_field.click()
                            password_field.fill(self.password)
                            break
                    except:
                        continue
                
                time.sleep(0.5)
                
                # Submit
                submit_selectors = [
                    'button[type="submit"]',
                    'button[data-testid="login-button"]',
                    'button:has-text("Log In")'
                ]
                
                for selector in submit_selectors:
                    try:
                        submit_btn = self.page.query_selector(selector)
                        if submit_btn and submit_btn.is_enabled():
                            self.log(f"Clicking submit with: {selector}")
                            submit_btn.click()
                            break
                    except:
                        continue
                
                # Wait for navigation after login
                time.sleep(5)
                
                # Check current URL
                current_url = self.page.url
                
                # Login successful if redirected away from login page
                # Check for error elements
                error_elem = self.page.query_selector('[data-testid="error-element"]')
                if error_elem:
                    error_text = error_elem.inner_text()
                    self.log(f"Login error: {error_text}", "error")
                    last_error = error_text
                elif "/login" in current_url.lower():
                    # Still on login page - check if there's an error
                    error_box = self.page.query_selector('.AnimatedForm__error')
                    if error_box:
                        error_text = error_box.inner_text()
                        self.log(f"Login error: {error_text}", "error")
                        last_error = error_text
                    else:
                        # No explicit error - check page content
                        self.log("Still on login page, waiting more...")
                        time.sleep(5)
                        current_url = self.page.url
                        if "/login" in current_url.lower():
                            last_error = "Still on login page after submission"
                else:
                    # Successfully redirected!
                    self.log(f"Login successful! Redirected to: {current_url}")
                    self._logged_in = True
                    return True

            except Exception as e:
                last_error = str(e)
                self.log(f"Login error (attempt {attempt}): {e}", "error")

        self.log(f"Login failed after {max_retries} attempts. Last error: {last_error}", "error")
        return False

    def _get_warmup_comment(self, post_title: str = "", subreddit: str = "") -> str:
        base_comment = random.choice(self.WARMUP_COMMENTS)
        if subreddit.lower() == "askreddit":
            return base_comment
        elif subreddit.lower() == "funny":
            return f"{base_comment} Funny stuff!"
        elif subreddit.lower() == "todayilearned":
            return f"{base_comment} TIL!"
        elif subreddit.lower() in ["startups", "entrepreneur", "smallbusiness"]:
            return f"{base_comment} Interesting business perspective."
        return base_comment

    def _navigate_to_post(self, post_url: str) -> bool:
        try:
            self.log(f"Navigating to post: {post_url[:50]}...")
            self.page.goto(post_url, timeout=30000)
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(2000)
            return True
        except Exception as e:
            self.log(f"Navigation error: {e}", "error")
            return False

    def _post_comment(self, comment_text: str) -> Dict[str, Any]:
        result = {
            "status": "pending",
            "timestamp": datetime.now().isoformat(),
            "comment_preview": comment_text[:200] if len(comment_text) > 200 else comment_text,
        }

        try:
            textarea = self.page.query_selector('textarea[name="comment"]')

            if not textarea:
                reply_buttons = self.page.query_selector_all('button[data-testid="reply-button"], button:has-text("Reply")')
                if reply_buttons:
                    self.log("Clicking reply button...")
                    reply_buttons[0].click()
                    self.page.wait_for_timeout(1000)
                    textarea = self.page.query_selector('textarea[name="comment"]')

            if textarea:
                self.log(f"Entering comment: {comment_text[:50]}...")
                textarea.click()
                textarea.fill(comment_text)

                submit_selectors = [
                    'button[data-testid="comment-submit-button"]',
                    'button:has-text("Comment")',
                    'button[type="submit"]',
                ]

                for selector in submit_selectors:
                    submit_btn = self.page.query_selector(selector)
                    if submit_btn and submit_btn.is_enabled():
                        self.log("Submitting comment...")
                        submit_btn.click()
                        self.page.wait_for_timeout(2000)
                        result["status"] = "success"
                        self.log("Comment posted successfully!")
                        return result

                result["status"] = "error"
                result["error"] = "Could not find submit button"
            else:
                result["status"] = "error"
                result["error"] = "Could not find comment textarea"

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            self.log(f"Error posting comment: {e}", "error")

        return result

    def _browse_and_warmup(self, subreddits: List[str]) -> Dict[str, Any]:
        results = {
            "subreddits_visited": [],
            "comments_attempted": 0,
            "comments_posted": 0,
            "posts_viewed": 0,
        }

        target_comments = self.comments_per_round
        comments_posted = 0

        for subreddit in subreddits:
            if comments_posted >= target_comments:
                break

            results["subreddits_visited"].append(subreddit)

            if self.mock_mode:
                self.log(f"DRY-RUN: Would browse r/{subreddit}")
                self.log(f"DRY-RUN: Found ~20 hot posts, would comment on {min(3, target_comments - comments_posted)}")
                comments_posted += 1
                results["comments_attempted"] += 1
                results["posts_viewed"] += 5
                continue

            try:
                self.log(f"Visiting r/{subreddit}...")
                self.page.goto(f"{self.BASE_URL}/r/{subreddit}/hot", timeout=30000)
                self.page.wait_for_load_state("networkidle")
                self.page.wait_for_timeout(1500)

                post_links = self.page.query_selector_all('a[data-click-id="body"]')

                for link in post_links[:5]:
                    if comments_posted >= target_comments:
                        break

                    try:
                        title_elem = self.page.query_selector('h2')
                        post_title = title_elem.inner_text() if title_elem else "Generic Post"

                        href = link.get_attribute("href")
                        if href and "/comments/" in href:
                            full_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

                            if self._navigate_to_post(full_url):
                                results["posts_viewed"] += 1
                                comment_text = self._get_warmup_comment(post_title, subreddit)
                                post_result = self._post_comment(comment_text)

                                if post_result["status"] == "success":
                                    comments_posted += 1
                                    results["comments_attempted"] += 1
                                    results["comments_posted"] += 1
                                    state_manager.mark_post_processed(full_url)

                                    delay = random.randint(7, 25) * 60
                                    self.log(f"Waiting {delay//60} minutes before next post...")
                                    self.page.wait_for_timeout(min(delay, 5000))

                    except Exception as e:
                        self.log(f"Error processing post: {e}", "error")
                        continue

            except Exception as e:
                self.log(f"Error browsing r/{subreddit}: {e}", "error")
                continue

        return results

    def _warmup_praw(self, subreddits: List[str]) -> Dict[str, Any]:
        """Fallback warmup using PRAW API."""
        if not PRAW_AVAILABLE:
            return {"error": "PRAW not available"}
        
        self.log("Attempting PRAW fallback for warmup...")
        
        try:
            reddit = praw.Reddit(
                client_id=REDDIT_CONFIG.get("client_id"),
                client_secret=REDDIT_CONFIG.get("client_secret"),
                user_agent=REDDIT_CONFIG.get("user_agent") or "ZetaAgent/1.0",
                username=self.username,
                password=self.password,
            )
            
            results = {
                "subreddits_visited": [],
                "comments_attempted": 0,
                "comments_posted": 0,
            }
            
            comments = self.WARMUP_COMMENTS
            
            for subreddit in subreddits[:3]:  # Limit to 3 subreddits
                if results["comments_posted"] >= self.comments_per_round:
                    break
                
                results["subreddits_visited"].append(subreddit)
                self.log(f"Visiting r/{subreddit} via PRAW...")
                
                try:
                    sub = reddit.subreddit(subreddit)
                    for submission in sub.hot(limit=5):
                        if results["comments_posted"] >= self.comments_per_round:
                            break
                        
                        comment_text = random.choice(comments)
                        submission.reply(comment_text)
                        results["comments_attempted"] += 1
                        results["comments_posted"] += 1
                        self.log(f"Posted comment on: {submission.title[:50]}...")
                        
                        # Small delay
                        time.sleep(random.randint(2, 5))
                        
                except Exception as e:
                    self.log(f"Error posting to r/{subreddit}: {e}", "error")
                    continue
            
            return results
            
        except Exception as e:
            self.log(f"PRAW fallback failed: {e}", "error")
            return {"error": str(e)}

    def warmup(self, subreddits: List[str] = None) -> Dict[str, Any]:
        default_subreddits = ["AskReddit", "funny", "pics", "todayilearned", "mildlyinteresting"]
        target_subreddits = subreddits or default_subreddits

        self.log("=" * 50)
        self.log("STARTING ZETA REDDIT WARMUP")
        self.log(f"Mode: {'DRY-RUN' if self.mock_mode else 'LIVE'}")
        if self.proxy_server:
            self.log(f"Proxy: {self.proxy_server}")
        self.log(f"Target subreddits: {target_subreddits}")
        self.log(f"Comments per round: {self.comments_per_round}")
        self.log("=" * 50)

        results = {
            "success": False,
            "login_success": False,
            "warmup_results": {},
            "mode": "dry_run" if self.mock_mode else "live",
            "username": self.username,
            "method": "browser",
        }

        try:
            # Try browser first
            if not self.mock_mode:
                results["login_success"] = self.login()
                
                if results["login_success"]:
                    results["warmup_results"] = self._browse_and_warmup(target_subreddits)
                    results["success"] = True
                elif PRAW_AVAILABLE and REDDIT_CONFIG.get("client_id"):
                    # Fallback to PRAW if browser fails
                    self.log("Browser login failed, trying PRAW fallback...", "warning")
                    results["warmup_results"] = self._warmup_praw(target_subreddits)
                    results["success"] = "error" not in results["warmup_results"]
                    results["method"] = "praw_fallback"
                else:
                    self.log("Cannot run warmup - browser login failed and PRAW not available", "error")
            else:
                results["warmup_results"] = self._browse_and_warmup(target_subreddits)
                results["success"] = True

        except Exception as e:
            self.log(f"Warmup error: {e}", "error")
            results["error"] = str(e)

        finally:
            self._close_browser()

        self.log("=" * 50)
        self.log("ZETA WARMUP COMPLETE")
        self.log(f"Success: {results['success']}")
        self.log(f"Method: {results['method']}")
        self.log(f"Comments posted: {results.get('warmup_results', {}).get('comments_posted', 0)}")
        self.log("=" * 50)

        return results

    async def post_comment(self, submission_id: str, comment_text: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        if self.mock_mode or PUBLISHING_CONFIG["dry_run"]:
            return {
                "status": "dry_run",
                "submission_id": submission_id,
                "comment_preview": comment_text[:200],
                "timestamp": datetime.now().isoformat(),
            }
        return {
            "status": "not_implemented",
            "message": "Use warmup() method for browser-based posting",
            "timestamp": datetime.now().isoformat(),
        }


def run_warmup(
    username: str,
    password: str,
    subreddits: List[str] = None,
    dry_run: bool = True,
    headless: bool = True,
    comments_per_round: int = 3,
    proxy_server: str = None,
    proxy_username: str = None,
    proxy_password: str = None
) -> Dict[str, Any]:
    publisher = BrowserPublisher(
        username=username,
        password=password,
        mock_mode=dry_run,
        headless=headless,
        comments_per_round=comments_per_round,
        proxy_server=proxy_server,
        proxy_username=proxy_username,
        proxy_password=proxy_password
    )
    return publisher.warmup(subreddits=subreddits)
