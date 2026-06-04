#!/usr/bin/env python3
"""
Reddit Browser Automation - Advanced Anti-Bot Evasion Script
============================================================
Playwright-based Reddit automation with human-mimicking capabilities.

Features:
- Anti-fingerprinting with stealth plugins and randomized profiles
- Human-like delays (jitter) for typing, clicking, and page transitions
- Realistic mouse movements, scrolling, and element interactions
- Session management with secure cookie persistence
- Robust error handling for Reddit pop-ups and layout changes

Usage:
    python3 scripts/reddit_automation.py [--dry-run] [--headless]
    python3 scripts/reddit_automation.py --post "Title" "Body" [--subreddit=r/startups]
"""

import argparse
import json
import os
import random
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Playwright imports
try:
    from playwright.sync_api import (
        sync_playwright,
        Browser,
        BrowserContext,
        Page,
        Playwright,
        TimeoutError as PlaywrightTimeout,
    )
except ImportError:
    print("[ERROR] Playwright not installed. Run: pip install playwright && playwright install")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

class Config:
    """Central configuration for Reddit automation."""

    # Browser fingerprint settings
    SCREEN_RESOLUTIONS = [
        (1920, 1080), (1366, 768), (1440, 900), (1536, 864),
        (1600, 900), (1280, 720), (2560, 1440), (3840, 2160)
    ]

    VIEWPORT_SIZES = [
        {"width": 1920, "height": 1080},
        {"width": 1366, "height": 768},
        {"width": 1440, "height": 900},
        {"width": 1280, "height": 800},
    ]

    # User agent pool - realistic desktop browsers
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0",
    ]

    # Language settings
    ACCEPT_LANGUAGES = [
        "en-US,en;q=0.9",
        "en-GB,en;q=0.9",
        "en-CA,en;q=0.9",
        "en-AU,en;q=0.9",
        "en;q=0.9",
        "en-US,en;q=0.9,es;q=0.8",
    ]

    # Timing configurations (in seconds)
    TIMING = {
        "min_keystroke_delay": 0.05,
        "max_keystroke_delay": 0.15,
        "min_click_delay": 0.3,
        "max_click_delay": 1.0,
        "min_page_load_delay": 1.5,
        "max_page_load_delay": 4.0,
        "min_scroll_pause": 0.2,
        "max_scroll_pause": 0.8,
        "min_think_time": 2.0,
        "max_think_time": 8.0,
    }

    # Anti-fingerprint tweaks
    DISABLE_WEBRTC = True
    DISABLE_BATTERY_API = True
    DISABLE_GEOLOCATION_API = True
    BLOCK_CHROME_LOADER = True
    HOOK_FUNCTIONS = True

    # Session storage
    SESSION_DIR = Path("~/.config/reddit-automation").expanduser()
    SESSION_FILE = "session.json"

    # Reddit selectors (updated regularly - may need maintenance)
    SELECTORS = {
        "login_username": 'input[name="username"]',
        "login_password": 'input[name="password"]',
        "login_button": 'button[type="submit"]',
        "post_title": '[data-testid="post-title-input"]',
        "post_title_alt": 'textarea[name="title"]',
        "post_body": '[data-testid="comment-submit-button"] + * textarea, [data-testid="post-content-input"]',
        "post_body_alt": 'div[role="textbox"][aria-label*="body"]',
        "post_button": '[data-testid="submit-post-button"]',
        "subreddit_select": 'button[data-testid="subreddit-picker-button"]',
        "subreddit_search": 'input[name="subreddit"]',
        "captcha": '.captcha-container, [data-testid="captcha-container"]',
        "popup_close": '[data-testid="popup-close-button"], button[aria-label="Close"]',
        "cookie_consent": 'button[data-testid="cookie-consent-accept"]',
        "error_message": '[data-testid="error-message"], .error, .form-field-errors',
    }


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def generate_uuid() -> str:
    """Generate a random UUID for fingerprinting."""
    return str(uuid.uuid4())


def random_float(min_val: float, max_val: float) -> float:
    """Return a random float between min and max."""
    return random.uniform(min_val, max_val)


def random_int(min_val: int, max_val: int) -> int:
    """Return a random integer between min and max."""
    return random.randint(min_val, max_val)


def jitter_delay(timing_key: str):
    """Apply a randomized delay based on timing configuration."""
    timing = Config.TIMING
    min_val = timing.get(f"min_{timing_key}", 0.5)
    max_val = timing.get(f"max_{timing_key}", 1.5)
    delay = random_float(min_val, max_val)
    # Add micro-jitter (0.9-1.1 multiplier)
    delay *= random.uniform(0.9, 1.1)
    time.sleep(delay)


def human_typing(page: Page, selector: str, text: str, clear_first: bool = True):
    """Simulate human-like typing with randomized keystroke delays."""
    element = page.locator(selector).first

    if clear_first:
        element.click()
        time.sleep(random_float(0.1, 0.3))
        element.select_all()
        time.sleep(random_float(0.05, 0.15))

    element.click()
    jitter_delay("click_delay")

    for char in text:
        element.type(char, delay=random_float(
            Config.TIMING["min_keystroke_delay"],
            Config.TIMING["max_keystroke_delay"]
        ))
        # Occasional micro-pause (like a human might take to think)
        if random.random() < 0.05:  # 5% chance of extra pause
            time.sleep(random_float(0.1, 0.3))


def human_click(page: Page, selector: str, simulate_hover: bool = True):
    """Simulate human-like click with optional hover and jitter."""
    if simulate_hover:
        element = page.locator(selector).first
        element.hover()
        # Small movement variation
        page.mouse.move(
            random.randint(-5, 5),
            random.randint(-5, 5)
        )
        jitter_delay("click_delay")

    page.locator(selector).first.click()
    jitter_delay("click_delay")


def smooth_scroll(page: Page, direction: str = "down", amount: int = 300):
    """Simulate smooth scrolling with randomized pauses."""
    if direction == "down":
        page.mouse.wheel(0, random_int(amount - 50, amount + 50))
    else:
        page.mouse.wheel(0, random_int(-(amount + 50), -(amount - 50)))

    jitter_delay("scroll_pause")


def random_mouse_movement(page: Page):
    """Generate random mouse movements to simulate human behavior."""
    current_pos = page.mouse.position()
    offset_x = random_int(-100, 100)
    offset_y = random_int(-50, 50)

    # Move in small increments with varying speeds
    steps = random_int(5, 15)
    for _ in range(steps):
        new_x = current_pos.x + random_int(offset_x // steps - 10, offset_x // steps + 10)
        new_y = current_pos.y + random_int(offset_y // steps - 5, offset_y // steps + 5)
        page.mouse.move(new_x, new_y)
        time.sleep(random_float(0.01, 0.05))


# ─────────────────────────────────────────────────────────────────────────────
# SESSION MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

class SessionManager:
    """Manages browser sessions with secure storage."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Config.SESSION_DIR / Config.SESSION_FILE
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def save_session(self, context: BrowserContext, metadata: dict = None):
        """Save browser context state including cookies and localStorage."""
        storage_state = context.storage_state()

        session_data = {
            "timestamp": datetime.now().isoformat(),
            "cookies": storage_state.get("cookies", []),
            "origins": storage_state.get("origins", []),
            "metadata": metadata or {},
        }

        with open(self.storage_path, "w") as f:
            json.dump(session_data, f, indent=2)

        print(f"[OK] Session saved to {self.storage_path}")

    def load_session(self) -> Optional[dict]:
        """Load saved session data if valid."""
        if not self.storage_path.exists():
            return None

        try:
            with open(self.storage_path, "r") as f:
                session_data = json.load(f)

            # Check if session is less than 7 days old
            session_time = datetime.fromisoformat(session_data["timestamp"])
            if datetime.now() - session_time > timedelta(days=7):
                print("[WARN] Session expired (>7 days old), clearing...")
                self.clear_session()
                return None

            print(f"[OK] Loaded session from {self.storage_path}")
            return session_data

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[WARN] Failed to load session: {e}, clearing...")
            self.clear_session()
            return None

    def clear_session(self):
        """Remove saved session data."""
        if self.storage_path.exists():
            self.storage_path.unlink()
            print("[OK] Session cleared")

    def get_storage_state(self) -> Optional[dict]:
        """Get the storage_state dict for Playwright context creation."""
        session = self.load_session()
        if session:
            return {"cookies": session.get("cookies", []), "origins": session.get("origins", [])}
        return None


# ─────────────────────────────────────────────────────────────────────────────
# BROWSER CONTEXT FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def create_stealth_browser_context(
    playwright: Playwright,
    session_manager: SessionManager,
    headless: bool = True,
    browser_type: str = "chromium"
) -> BrowserContext:
    """Create a stealth browser context with anti-fingerprinting measures."""

    # Select random fingerprint values
    resolution = random.choice(Config.SCREEN_RESOLUTIONS)
    viewport = random.choice(Config.VIEWPORT_SIZES)
    user_agent = random.choice(Config.USER_AGENTS)
    accept_language = random.choice(Config.ACCEPT_LANGUAGES)

    # Browser launch arguments for stealth
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=Automation",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-accelerated-2d-canvas",
        "--disable-gpu",
        "--window-size=1920,1080",
        f"--window-position={random.randint(0, 100)},{random.randint(0, 100)}",
    ]

    if Config.DISABLE_WEBRTC:
        launch_args.extend([
            "--disable-webrtc",
            "--disable-media-router",
            "--disable-cast-streaming",
        ])

    # Create browser
    browser_map = {
        "chromium": playwright.chromium,
        "firefox": playwright.firefox,
        "webkit": playwright.webkit,
    }

    browser = browser_map.get(browser_type, playwright.chromium).launch(
        headless=headless,
        args=launch_args
    )

    # Get existing session or create new storage state
    storage_state = session_manager.get_storage_state()

    # Context creation with anti-fingerprint headers
    context = browser.new_context(
        viewport=viewport,
        user_agent=user_agent,
        locale="en-US",
        timezone_id="America/New_York",
        permissions=["geolocation"],
        ignore_https_errors=True,
        storage_state=storage_state,
        extra_http_headers={
            "Accept-Language": accept_language,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        },
    )

    # Inject anti-fingerprinting scripts
    _inject_stealth_scripts(context)

    return context


def _inject_stealth_scripts(context: BrowserContext):
    """Inject JavaScript to mask automation fingerprints."""

    # Remove webdriver property
    webdriver_navigator_script = """
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });
    """

    # Randomize canvas fingerprint
    canvas_script = """
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;

    Hooks.canvas = function() {
        // Add noise to canvas to prevent fingerprinting
        const originalFillText = CanvasRenderingContext2D.prototype.fillText;
        CanvasRenderingContext2D.prototype.fillText = function(...args) {
            this.save();
            this.translate(Math.random() * 0.001, Math.random() * 0.001);
            const result = originalFillText.apply(this, args);
            this.restore();
            return result;
        };

        // Hook toDataURL
        HTMLCanvasElement.prototype.toDataURL = function(...args) {
            const ctx = this.getContext('2d');
            if (ctx) {
                const imageData = originalGetImageData.call(ctx, 0, 0, this.width, this.height);
                // Add random noise
                for (let i = 0; i < imageData.data.length; i += 4) {
                    imageData.data[i] += Math.floor(Math.random() * 2);
                    imageData.data[i + 1] += Math.floor(Math.random() * 2);
                    imageData.data[i + 2] += Math.floor(Math.random() * 2);
                }
                ctx.putImageData(imageData, 0, 0);
            }
            return originalToDataURL.apply(this, args);
        };
    };
    """

    # Remove automation detection
    permissions_script = """
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
    """

    # Override plugins
    plugins_script = """
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
        configurable: true
    });
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en', 'es'],
        configurable: true
    });
    """

    # Chrome runtime detection
    chrome_script = """
    window.chrome = { app: { runtime: {} }, runtime: {} };
    """

    # Generate random client rect
    fingerprint_script = f"""
    // Randomize values that can be used for fingerprinting
    const randomSeed = {random.randint(1000000, 9999999)};
    const seededRandom = () => {{
        randomSeed = (randomSeed * 9301 + 49297) % 233280;
        return randomSeed / 233280;
    }};

    // Override functions that expose automation
    const elementProto = Element.prototype;
    const getBoundingClientRectOriginal = elementProto.getBoundingClientRect;
    elementProto.getBoundingClientRect = function() {{
        const rect = getBoundingClientRectOriginal.call(this);
        return {{
            ...rect,
            top: rect.top + Math.floor(seededRandom() * 2),
            left: rect.left + Math.floor(seededRandom() * 2),
        }};
    }};
    """

    # Inject all scripts
    scripts = [
        webdriver_navigator_script,
        canvas_script,
        permissions_script,
        plugins_script,
        chrome_script,
        fingerprint_script,
    ]

    for script in scripts:
        context.add_init_script(script)


# ─────────────────────────────────────────────────────────────────────────────
# REDDIT AUTOMATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class RedditAutomation:
    """Main Reddit automation engine with anti-bot evasion."""

    def __init__(
        self,
        headless: bool = True,
        dry_run: bool = False,
        browser_type: str = "chromium"
    ):
        self.headless = headless
        self.dry_run = dry_run
        self.browser_type = browser_type
        self.session_manager = SessionManager()
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def __enter__(self):
        """Context manager entry."""
        self._start_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup()

    def _start_browser(self):
        """Initialize Playwright and create stealth browser context."""
        print("[INFO] Starting browser automation...")

        self.playwright = sync_playwright().start()
        self.context = create_stealth_browser_context(
            self.playwright,
            self.session_manager,
            headless=self.headless,
            browser_type=self.browser_type
        )
        self.browser = self.context.browser
        self.page = self.context.new_page()

        print(f"[OK] Browser started (headless={self.headless})")

    def cleanup(self):
        """Clean up browser resources."""
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

        print("[OK] Browser automation stopped")

    def save_session(self):
        """Save current session for future use."""
        if self.context:
            self.session_manager.save_session(
                self.context,
                {"last_post": datetime.now().isoformat()}
            )

    # ─────────────────────────────────────────────────────────────────────────
    # AUTHENTICATION
    # ─────────────────────────────────────────────────────────────────────────

    def login(self, username: str, password: str) -> bool:
        """Login to Reddit with human-like interactions."""
        if self.dry_run:
            print("[DRY-RUN] Would login to Reddit")
            return True

        print(f"[INFO] Logging in to Reddit as {username}...")

        try:
            self.page.goto("https://www.reddit.com/login", wait_until="domcontentloaded")
            jitter_delay("page_load_delay")

            # Wait for login form to be visible
            self.page.wait_for_selector(Config.SELECTORS["login_username"], timeout=15000)

            # Random mouse movement before interaction
            random_mouse_movement(self.page)

            # Fill in credentials with human typing
            human_typing(self.page, Config.SELECTORS["login_username"], username)
            jitter_delay("click_delay")
            jitter_delay("think_time")

            human_typing(self.page, Config.SELECTORS["login_password"], password)
            jitter_delay("click_delay")

            # Click login button
            human_click(self.page, Config.SELECTORS["login_button"])

            # Wait for redirect
            self.page.wait_for_load_state("networkidle", timeout=30000)

            # Check for errors
            error_selectors = Config.SELECTORS["error_message"]
            if self.page.locator(error_selectors).count() > 0:
                error_text = self.page.locator(error_selectors).first.text_content()
                print(f"[ERROR] Login failed: {error_text}")
                return False

            # Check if we're logged in (look for user menu)
            self.page.wait_for_selector('[aria-label="Account"]', timeout=15000)

            print("[OK] Successfully logged in")
            self.save_session()
            return True

        except PlaywrightTimeout:
            print("[ERROR] Login timeout - page took too long to load")
            return False
        except Exception as e:
            print(f"[ERROR] Login failed: {e}")
            return False

    def is_logged_in(self) -> bool:
        """Check if current session is authenticated."""
        try:
            self.page.goto("https://www.reddit.com/", wait_until="domcontentloaded")
            self.page.wait_for_selector('[aria-label="Account"]', timeout=5000)
            return True
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # POPUP HANDLING
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_popups(self):
        """Handle common Reddit popups (cookies, notifications, etc.)."""
        selectors_to_try = [
            Config.SELECTORS["cookie_consent"],
            Config.SELECTORS["popup_close"],
            'button[aria-label="No thanks"]',
            'button:has-text("Accept")',
            'button:has-text("Got it")',
        ]

        for selector in selectors_to_try:
            try:
                if self.page.locator(selector).count() > 0:
                    self.page.locator(selector).first.click()
                    jitter_delay("click_delay")
                    print(f"[OK] Handled popup: {selector}")
                    break
            except Exception:
                continue

    # ─────────────────────────────────────────────────────────────────────────
    # POST CREATION
    # ─────────────────────────────────────────────────────────────────────────

    def create_post(
        self,
        title: str,
        body: str = "",
        subreddit: str = None,
        link: str = None
    ) -> Optional[str]:
        """Create a Reddit post with human-like interactions."""
        if self.dry_run:
            print(f"[DRY-RUN] Would create post: {title[:50]}...")
            return "dry-run-post-id"

        print(f"[INFO] Creating post in r/{subreddit or 'reddit'}...")

        try:
            # Navigate to post creation page
            self.page.goto("https://www.reddit.com/r/ask/submit", wait_until="domcontentloaded")
            jitter_delay("page_load_delay")

            # Handle any popups
            self._handle_popups()

            # Random scroll to simulate human behavior
            for _ in range(random_int(1, 3)):
                smooth_scroll(self.page, "down", random_int(100, 300))
                time.sleep(random_float(0.3, 0.8))

            # Select subreddit if provided
            if subreddit:
                self._select_subreddit(subreddit)

            # Wait for post form to be ready
            self.page.wait_for_selector(Config.SELECTORS["post_title"], timeout=10000)

            # Random mouse movement before typing
            random_mouse_movement(self.page)

            # Type the title
            human_typing(self.page, Config.SELECTORS["post_title"], title)
            jitter_delay("think_time")

            # Type the body if provided
            if body:
                body_selectors = [Config.SELECTORS["post_body"], Config.SELECTORS["post_body_alt"]]
                for selector in body_selectors:
                    if self.page.locator(selector).count() > 0:
                        human_typing(self.page, selector, body)
                        break

                jitter_delay("think_time")

            # Scroll down to reveal submit button
            for _ in range(random_int(2, 4)):
                smooth_scroll(self.page, "down", random_int(200, 400))
                time.sleep(random_float(0.2, 0.5))

            # Random mouse movement before submit
            random_mouse_movement(self.page)

            # Click submit button
            submit_selectors = [Config.SELECTORS["post_button"], 'button:has-text("Submit")']
            for selector in submit_selectors:
                if self.page.locator(selector).count() > 0:
                    human_click(self.page, selector)
                    break

            # Wait for post to be created
            time.sleep(random_float(2, 4))

            # Get the post URL
            post_url = self.page.url
            if "submit" not in post_url and "/comments/" in post_url:
                print(f"[OK] Post created successfully: {post_url}")
                self.save_session()
                return post_url

            # Check for errors
            if self.page.locator(Config.SELECTORS["error_message"]).count() > 0:
                error_text = self.page.locator(Config.SELECTORS["error_message"]).first.text_content()
                print(f"[ERROR] Post creation failed: {error_text}")
                return None

            print(f"[OK] Post created: {post_url}")
            return post_url

        except PlaywrightTimeout:
            print("[ERROR] Post creation timeout")
            return None
        except Exception as e:
            print(f"[ERROR] Post creation failed: {e}")
            return None

    def _select_subreddit(self, subreddit: str):
        """Select a subreddit for posting."""
        try:
            # Click subreddit selector
            selector_buttons = [
                Config.SELECTORS["subreddit_select"],
                'button:has-text("Choose a community")',
                'button:has-text("r/")',
            ]

            for selector in selector_buttons:
                if self.page.locator(selector).count() > 0:
                    human_click(self.page, selector)
                    break

            time.sleep(random_float(0.5, 1.0))

            # Search for subreddit
            search_input = self.page.locator(Config.SELECTORS["subreddit_search"])
            if search_input.count() > 0:
                human_typing(self.page, Config.SELECTORS["subreddit_search"], subreddit)
                time.sleep(random_float(0.8, 1.5))

                # Select from dropdown
                self.page.keyboard.press("Enter")
                time.sleep(random_float(0.3, 0.8))

            print(f"[OK] Selected subreddit: r/{subreddit}")

        except Exception as e:
            print(f"[WARN] Subreddit selection failed: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # COMMENT INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def post_comment(self, post_url: str, comment: str) -> bool:
        """Post a comment on a Reddit post."""
        if self.dry_run:
            print(f"[DRY-RUN] Would comment on: {post_url}")
            return True

        print(f"[INFO] Posting comment on: {post_url}")

        try:
            self.page.goto(post_url, wait_until="domcontentloaded")
            jitter_delay("page_load_delay")

            # Scroll to comment box
            for _ in range(random_int(3, 5)):
                smooth_scroll(self.page, "down", random_int(150, 350))
                time.sleep(random_float(0.2, 0.5))

            # Find and fill comment box
            comment_selectors = [
                '[data-testid="comment-submit-button"] + * textarea',
                'textarea[name="comment"]',
                'div[role="textbox"][aria-label*="Comment"]',
            ]

            comment_filled = False
            for selector in comment_selectors:
                if self.page.locator(selector).count() > 0:
                    human_typing(self.page, selector, comment)
                    comment_filled = True
                    break

            if not comment_filled:
                print("[ERROR] Could not find comment box")
                return False

            jitter_delay("think_time")

            # Click submit
            submit_selectors = [
                '[data-testid="comment-submit-button"]',
                'button:has-text("Comment")',
            ]

            for selector in submit_selectors:
                if self.page.locator(selector).count() > 0:
                    human_click(self.page, selector)
                    break

            time.sleep(random_float(1.5, 3.0))
            print("[OK] Comment posted successfully")
            self.save_session()
            return True

        except Exception as e:
            print(f"[ERROR] Comment posting failed: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # BROWSING BEHAVIOR
    # ─────────────────────────────────────────────────────────────────────────

    def browse_subreddit(self, subreddit: str, posts_to_check: int = 5) -> list:
        """Browse a subreddit with human-like behavior and extract post data."""
        print(f"[INFO] Browsing r/{subreddit}...")

        posts_data = []

        try:
            self.page.goto(f"https://www.reddit.com/r/{subreddit}/", wait_until="domcontentloaded")
            jitter_delay("page_load_delay")

            # Scroll through posts with random behavior
            for i in range(posts_to_check):
                # Random scroll pattern
                for _ in range(random_int(2, 4)):
                    smooth_scroll(self.page, "down", random_int(200, 400))
                    time.sleep(random_float(0.3, 1.0))

                # Try to extract post info
                post_selectors = [
                    '[data-testid="post"]',
                    'article[data-testid="post-preview"]',
                    '[class*="Post"]',
                ]

                for selector in post_selectors:
                    if self.page.locator(selector).count() > i:
                        try:
                            post_element = self.page.locator(selector).nth(i)

                            # Get post title
                            title_selector = '[data-testid="post-title"], a[data-testid="post-title"]'
                            title = post_element.locator(title_selector).text_content(timeout=2000)

                            # Get post URL
                            link = post_element.locator(f'a[href*="/r/{subreddit}/comments/"]').get_attribute("href")

                            if title:
                                posts_data.append({
                                    "title": title.strip(),
                                    "url": link,
                                    "subreddit": subreddit,
                                })
                                print(f"[OK] Found post: {title[:50]}...")
                        except Exception:
                            continue

                jitter_delay("think_time")

            print(f"[OK] Found {len(posts_data)} posts in r/{subreddit}")

        except Exception as e:
            print(f"[ERROR] Browsing failed: {e}")

        return posts_data


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Reddit Browser Automation with Advanced Anti-Bot Evasion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --login --username myuser --password mypass
  %(prog)s --post "My Title" "My body text" --subreddit startups
  %(prog)s --browse --subreddit entrepreneur --posts 10
  %(prog)s --dry-run --post "Test" "Body" --subreddit test
        """
    )

    # Authentication
    auth_group = parser.add_argument_group("Authentication")
    auth_group.add_argument("--login", action="store_true", help="Login to Reddit")
    auth_group.add_argument("--username", type=str, help="Reddit username")
    auth_group.add_argument("--password", type=str, help="Reddit password")

    # Actions
    action_group = parser.add_argument_group("Actions")
    action_group.add_argument("--post", nargs=2, metavar=("TITLE", "BODY"),
                              help="Create a post (provide title and body)")
    action_group.add_argument("--comment", type=str, help="Comment on a post (use with --url)")
    action_group.add_argument("--browse", action="store_true", help="Browse subreddit")
    action_group.add_argument("--subreddit", type=str, default="ask", help="Subreddit name")
    action_group.add_argument("--url", type=str, help="Post URL for commenting")

    # Configuration
    config_group = parser.add_argument_group("Configuration")
    config_group.add_argument("--headless", action="store_true", default=True,
                              help="Run browser in headless mode (default: true)")
    config_group.add_argument("--visible", action="store_true",
                              help="Run browser in visible mode (overrides --headless)")
    config_group.add_argument("--dry-run", action="store_true",
                              help="Simulate actions without executing")
    config_group.add_argument("--browser", choices=["chromium", "firefox", "webkit"],
                              default="chromium", help="Browser type")
    config_group.add_argument("--posts", type=int, default=5,
                              help="Number of posts to browse (default: 5)")
    config_group.add_argument("--clear-session", action="store_true",
                              help="Clear saved session before starting")

    args = parser.parse_args()

    # Determine headless mode
    headless = not args.visible

    # Clear session if requested
    if args.clear_session:
        SessionManager().clear_session()

    # Environment variable fallback for credentials
    username = args.username or os.environ.get("REDDIT_USERNAME", "")
    password = args.password or os.environ.get("REDDIT_PASSWORD", "")

    try:
        with RedditAutomation(headless=headless, dry_run=args.dry_run,
                               browser_type=args.browser) as automation:

            # Login if requested
            if args.login:
                if not username or not password:
                    print("[ERROR] Username and password required for login")
                    print("        Set REDDIT_USERNAME and REDDIT_PASSWORD environment variables")
                    sys.exit(1)

                if not automation.login(username, password):
                    print("[ERROR] Login failed")
                    sys.exit(1)

            # Perform actions
            if args.post:
                title, body = args.post
                result = automation.create_post(
                    title=title,
                    body=body,
                    subreddit=args.subreddit
                )
                if result:
                    print(f"[OK] Post created: {result}")
                else:
                    print("[ERROR] Post creation failed")
                    sys.exit(1)

            elif args.comment and args.url:
                if automation.post_comment(args.url, args.comment):
                    print("[OK] Comment posted successfully")
                else:
                    print("[ERROR] Comment posting failed")
                    sys.exit(1)

            elif args.browse:
                posts = automation.browse_subreddit(args.subreddit, posts_to_check=args.posts)
                print(f"\n[INFO] Found {len(posts)} posts:")
                for i, post in enumerate(posts, 1):
                    print(f"  {i}. {post['title']}")
                    print(f"     {post['url']}")

            elif args.login:
                # Login was successful, no further action needed
                print("[OK] Login completed successfully")

            else:
                parser.print_help()

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()