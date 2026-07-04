#!/usr/bin/env python3
"""
Delta Agent - Pure API Integration for Social Networks

This module provides clean, token-based, non-blocking HTTP API integrations
for multiple social networks without browser automation or cookies.

Supported Networks:
- Discord (Webhook URL / POST)
- Telegram (Bot API / Bot Token)
- Tumblr (OAuth2 Client / Access Token)
- Bluesky (AT Protocol / Session Token)
- Mastodon (OAuth2 / Access Token)

All credentials are mapped strictly to environment variables.
"""

import os
import json
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ==============================================================================
# BOOLEAN TOGGLES - Enable/disable each network integration
# ==============================================================================

_DISCORD_POST = True
_TELEGRAM_POST = True
_TUMBLR_POST = True
_BLUESKY_POST = True
_MASTODON_POST = True

# ==============================================================================
# ENVIRONMENT VARIABLE MAPPING
# ==============================================================================

# Discord
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Tumblr
TUMBLR_CLIENT_KEY = os.getenv("TUMBLR_CLIENT_KEY", "")
TUMBLR_CLIENT_SECRET = os.getenv("TUMBLR_CLIENT_SECRET", "")
TUMBLR_ACCESS_TOKEN = os.getenv("TUMBLR_ACCESS_TOKEN", "")
TUMBLR_ACCESS_SECRET = os.getenv("TUMBLR_ACCESS_SECRET", "")
TUMBLR_BLOG_HOSTNAME = os.getenv("TUMBLR_BLOG_HOSTNAME", "")

# Bluesky
BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE", "")
BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD", "")

# Mastodon
MASTODON_ACCESS_TOKEN = os.getenv("MASTODON_ACCESS_TOKEN", "")
MASTODON_API_BASE_URL = os.getenv("MASTODON_API_BASE_URL", "")

# Report file
REPORT_FILE = os.getenv("DELTA_REPORT_FILE", "delta_agent_report.json")

# ==============================================================================
# LOGGING SETUP
# ==============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("delta_agent")

# ==============================================================================
# DATA CLASSES
# ==============================================================================

@dataclass
class PostResult:
    """Result of a network post operation."""
    network: str
    success: bool
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    message: str = ""
    error: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None

@dataclass
class DeltaReport:
    """Complete report from Delta Agent operations."""
    report_id: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    summary: str = ""
    results: List[PostResult] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)

# ==============================================================================
# HTTP CLIENT SETUP
# ==============================================================================

class HTTPClient:
    """Minimal HTTP client with retry logic and timeout handling."""
    
    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "DeltaAgent/1.0 (Pure API Integration)",
            "Accept": "application/json, text/plain, */*"
        })
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """POST request with retry logic."""
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("headers", {})
        
        for attempt in range(self.max_retries):
            try:
                response = self.session.post(url, **kwargs)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise
                logger.warning(f"Attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(1 * (attempt + 1))
        
        raise Exception("Max retries exceeded")

# ==============================================================================
# NETWORK INTEGRATIONS
# ==============================================================================

class DiscordPoster:
    """Discord integration using official Webhook URL / POST request."""
    
    API_URL = "https://discord.com/api/v10"
    
    def __init__(self, http_client: HTTPClient):
        self.http = http_client
        self.webhook_url = DISCORD_WEBHOOK_URL
    
    def post(self, message: str) -> PostResult:
        """Post a message to Discord via webhook."""
        try:
            if not self.webhook_url:
                return PostResult(
                    network="discord",
                    success=False,
                    error="DISCORD_WEBHOOK_URL not configured"
                )
            
            payload = {
                "content": message,
                "allowed_mentions": {"parse": []}
            }
            
            response = self.http.post(self.webhook_url, json=payload)
            
            return PostResult(
                network="discord",
                success=True,
                message="Message posted successfully",
                response_data={"status_code": response.status_code}
            )
        except Exception as e:
            logger.error(f"Discord post failed: {e}")
            return PostResult(
                network="discord",
                success=False,
                error=str(e)
            )


class TelegramPoster:
    """Telegram integration using official Bot API / Bot Token."""
    
    API_URL = "https://api.telegram.org/bot{bot_token}/{method}"
    
    def __init__(self, http_client: HTTPClient):
        self.http = http_client
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
    
    def post(self, message: str) -> PostResult:
        """Post a message to Telegram via Bot API."""
        try:
            if not self.bot_token:
                return PostResult(
                    network="telegram",
                    success=False,
                    error="TELEGRAM_BOT_TOKEN not configured"
                )
            
            if not self.chat_id:
                return PostResult(
                    network="telegram",
                    success=False,
                    error="TELEGRAM_CHAT_ID not configured"
                )
            
            url = self.API_URL.format(bot_token=self.bot_token, method="sendMessage")
            
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = self.http.post(url, json=payload)
            data = response.json()
            
            if data.get("ok"):
                return PostResult(
                    network="telegram",
                    success=True,
                    message="Message sent successfully",
                    response_data={"message_id": data.get("result", {}).get("message_id")}
                )
            else:
                return PostResult(
                    network="telegram",
                    success=False,
                    error=f"API error: {data.get('description', 'Unknown error')}"
                )
        except Exception as e:
            logger.error(f"Telegram post failed: {e}")
            return PostResult(
                network="telegram",
                success=False,
                error=str(e)
            )


class TumblrPoster:
    """Tumblr integration using official OAuth2 Client / Access Token."""
    
    API_URL = "https://api.tumblr.com/v2/blog/{blog_hostname}/posts"
    
    def __init__(self, http_client: HTTPClient):
        self.http = http_client
        self.client_key = TUMBLR_CLIENT_KEY
        self.client_secret = TUMBLR_CLIENT_SECRET
        self.access_token = TUMBLR_ACCESS_TOKEN
        self.access_secret = TUMBLR_ACCESS_SECRET
        self.blog_hostname = TUMBLR_BLOG_HOSTNAME
    
    def post(self, content: str, tags: Optional[List[str]] = None) -> PostResult:
        """Post content to Tumblr via API."""
        try:
            if not self.access_token:
                return PostResult(
                    network="tumblr",
                    success=False,
                    error="TUMBLR_ACCESS_TOKEN not configured"
                )
            
            if not self.blog_hostname:
                return PostResult(
                    network="tumblr",
                    success=False,
                    error="TUMBLR_BLOG_HOSTNAME not configured"
                )
            
            url = self.API_URL.format(blog_hostname=self.blog_hostname)
            
            payload = {
                "type": "text",
                "body": content,
                "state": "published",
                "tags": ",".join(tags) if tags else ""
            }
            
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            
            response = self.http.post(url, data=payload, headers=headers)
            data = response.json()
            
            if data.get("meta", {}).get("status") == 201:
                return PostResult(
                    network="tumblr",
                    success=True,
                    message="Post created successfully",
                    response_data={"post_id": data.get("response", {}).get("id")}
                )
            else:
                return PostResult(
                    network="tumblr",
                    success=False,
                    error=f"API error: {data.get('meta', {}).get('msg', 'Unknown error')}"
                )
        except Exception as e:
            logger.error(f"Tumblr post failed: {e}")
            return PostResult(
                network="tumblr",
                success=False,
                error=str(e)
            )


class BlueskyPoster:
    """Bluesky integration using AT Protocol / Direct API Session Token."""
    
    API_URL = "https://bsky.social"
    
    def __init__(self, http_client: HTTPClient):
        self.http = http_client
        self.handle = BLUESKY_HANDLE
        self.app_password = BLUESKY_APP_PASSWORD
        self._session_token: Optional[str] = None
    
    def _authenticate(self) -> Optional[str]:
        """Authenticate with Bluesky and get session token."""
        try:
            url = f"{self.API_URL}/xrpc/com.atproto.server.createSession"
            payload = {
                "identifier": self.handle,
                "password": self.app_password
            }
            
            response = self.http.post(url, json=payload)
            data = response.json()
            
            if "accessJwt" in data:
                self._session_token = data["accessJwt"]
                return self._session_token
            return None
        except Exception as e:
            logger.error(f"Bluesky authentication failed: {e}")
            return None
    
    def post(self, text: str) -> PostResult:
        """Post content to Bluesky via AT Protocol."""
        try:
            if not self.handle or not self.app_password:
                return PostResult(
                    network="bluesky",
                    success=False,
                    error="BLUESKY_HANDLE or BLUESKY_APP_PASSWORD not configured"
                )
            
            # Authenticate if needed
            if not self._session_token:
                if not self._authenticate():
                    return PostResult(
                        network="bluesky",
                        success=False,
                        error="Authentication failed"
                    )
            
            # Create post
            url = f"{self.API_URL}/xrpc/com.atproto.server.createSession"
            headers = {
                "Authorization": f"Bearer {self._session_token}",
                "Content-Type": "application/json"
            }
            
            # Prepare post record
            post_data = {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": datetime.utcnow().isoformat() + "Z"
            }
            
            # Use the session's did for posting
            create_url = f"{self.API_URL}/xrpc/com.atproto.repo.createRecord"
            repo_payload = {
                "repo": self.handle,
                "collection": "app.bsky.feed.post",
                "record": post_data
            }
            
            response = self.http.post(create_url, json=repo_payload, headers=headers)
            data = response.json()
            
            if "uri" in data:
                return PostResult(
                    network="bluesky",
                    success=True,
                    message="Post created successfully",
                    response_data={"uri": data.get("uri"), "cid": data.get("cid")}
                )
            else:
                return PostResult(
                    network="bluesky",
                    success=False,
                    error="Unexpected response from API"
                )
        except Exception as e:
            logger.error(f"Bluesky post failed: {e}")
            return PostResult(
                network="bluesky",
                success=False,
                error=str(e)
            )


class MastodonPoster:
    """Mastodon integration using OAuth2 / Access Token."""
    
    API_URL = "/api/v1/statuses"
    
    def __init__(self, http_client: HTTPClient, api_base_url: str):
        self.http = http_client
        self.api_base_url = api_base_url.rstrip("/") if api_base_url else ""
        self.access_token = MASTODON_ACCESS_TOKEN
    
    def post(self, message: str, visibility: str = "unlisted") -> PostResult:
        """Post a status to Mastodon."""
        try:
            if not self.access_token:
                return PostResult(
                    network="mastodon",
                    success=False,
                    error="MASTODON_ACCESS_TOKEN not configured"
                )
            
            if not self.api_base_url:
                return PostResult(
                    network="mastodon",
                    success=False,
                    error="MASTODON_API_BASE_URL not configured"
                )
            
            url = f"{self.api_base_url}{self.API_URL}"
            
            payload = {
                "status": message,
                "visibility": visibility
            }
            
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            
            response = self.http.post(url, json=payload, headers=headers)
            data = response.json()
            
            if "id" in data:
                return PostResult(
                    network="mastodon",
                    success=True,
                    message="Status posted successfully",
                    response_data={"id": data.get("id"), "url": data.get("url")}
                )
            else:
                return PostResult(
                    network="mastodon",
                    success=False,
                    error="Unexpected response from API"
                )
        except Exception as e:
            logger.error(f"Mastodon post failed: {e}")
            return PostResult(
                network="mastodon",
                success=False,
                error=str(e)
            )

# ==============================================================================
# DELTA AGENT MAIN CLASS
# ==============================================================================

class DeltaAgent:
    """
    Delta Agent - Multi-network poster with isolated error handling.
    
    Posts messages to multiple social networks concurrently using pure
    HTTP API calls. Each network call is wrapped in an isolated try-except
    block so that if one fails, others continue safely.
    """
    
    def __init__(self, config_file: str = "delta_commands.json", report_file: str = REPORT_FILE):
        self.config = self._load_config(config_file)
        self.report_file = report_file
        self.http_client = HTTPClient()
        
        # Initialize posters based on toggles
        self.posters: Dict[str, Any] = {}
        
        if _DISCORD_POST:
            self.posters["discord"] = DiscordPoster(self.http_client)
        
        if _TELEGRAM_POST:
            self.posters["telegram"] = TelegramPoster(self.http_client)
        
        if _TUMBLR_POST:
            self.posters["tumblr"] = TumblrPoster(self.http_client)
        
        if _BLUESKY_POST:
            self.posters["bluesky"] = BlueskyPoster(self.http_client)
        
        if _MASTODON_POST and MASTODON_API_BASE_URL:
            self.posters["mastodon"] = MastodonPoster(
                self.http_client, MASTODON_API_BASE_URL
            )
    
    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        try:
            with open(config_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file {config_file} not found, using defaults")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return {}
    
    def _get_message_template(self, network: str, fallback: str = "{summary}") -> str:
        """Get message template for a network."""
        if network in self.config:
            template_key = f"{network}_message_template"
            if template_key in self.config[network]:
                return self.config[network][template_key]
            if "message_template" in self.config[network]:
                return self.config[network]["message_template"]
        return fallback
    
    def _format_message(self, network: str, summary: str) -> str:
        """Format message using template."""
        template = self._get_message_template(network)
        return template.replace("{summary}", summary)
    
    def _log_error(self, network: str, error: str, details: Optional[Dict] = None):
        """Log error to report file."""
        error_entry = {
            "network": network,
            "timestamp": datetime.utcnow().isoformat(),
            "error": error,
            "details": details or {}
        }
        
        # Load existing errors
        errors = []
        if os.path.exists(self.report_file):
            try:
                with open(self.report_file, "r") as f:
                    report = json.load(f)
                    errors = report.get("errors", [])
            except (json.JSONDecodeError, IOError):
                pass
        
        errors.append(error_entry)
        
        # Save updated errors
        try:
            with open(self.report_file, "w") as f:
                json.dump({"errors": errors}, f, indent=2)
        except IOError as e:
            logger.error(f"Failed to write to report file: {e}")
    
    def _save_report(self, report: DeltaReport):
        """Save report to JSON file."""
        try:
            with open(self.report_file, "w") as f:
                json.dump(asdict(report), f, indent=2)
        except IOError as e:
            logger.error(f"Failed to save report: {e}")
    
    def _post_to_network(self, network: str, summary: str) -> PostResult:
        """Post to a single network with isolated error handling."""
        try:
            if network not in self.posters:
                return PostResult(
                    network=network,
                    success=False,
                    error=f"Poster for {network} not initialized (check toggle or config)"
                )
            
            poster = self.posters[network]
            message = self._format_message(network, summary)
            
            # Get tags for Tumblr
            tags = None
            if network == "tumblr" and "tumblr" in self.config:
                tags = self.config["tumblr"].get("tags")
            
            if network == "tumblr":
                result = poster.post(message, tags=tags)
            else:
                result = poster.post(message)
            
            # Log error if failed
            if not result.success:
                self._log_error(network, result.error or "Unknown error", result.response_data)
            
            return result
            
        except Exception as e:
            logger.error(f"Unexpected error posting to {network}: {e}")
            self._log_error(network, str(e))
            return PostResult(
                network=network,
                success=False,
                error=str(e)
            )
    
    def post_to_all(self, summary: str) -> DeltaReport:
        """
        Post message to all configured networks concurrently.
        
        Each network call is isolated - if one fails, others continue.
        
        Args:
            summary: The main message/summary to post
            
        Returns:
            DeltaReport with results from all network posts
        """
        report_id = f"delta_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        results = []
        
        def post_task(network: str) -> PostResult:
            return self._post_to_network(network, summary)
        
        # Post to all networks concurrently
        with ThreadPoolExecutor(max_workers=len(self.posters)) as executor:
            futures = {
                executor.submit(post_task, network): network 
                for network in self.posters.keys()
            }
            
            for future in as_completed(futures):
                network = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    logger.info(f"{network}: {'SUCCESS' if result.success else 'FAILED'}")
                except Exception as e:
                    logger.error(f"Future error for {network}: {e}")
                    results.append(PostResult(
                        network=network,
                        success=False,
                        error=str(e)
                    ))
        
        # Create and save report
        report = DeltaReport(
            report_id=report_id,
            summary=summary,
            results=results
        )
        
        self._save_report(report)
        
        return report

    def post_single(self, network: str, summary: str) -> PostResult:
        """
        Post message to a single specific network.
        
        Args:
            network: The network name (discord, telegram, tumblr, bluesky, mastodon)
            summary: The message to post
            
        Returns:
            PostResult with the outcome
        """
        return self._post_to_network(network, summary)


# ==============================================================================
# CLI INTERFACE
# ==============================================================================

def main():
    """Main entry point for CLI usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Delta Agent - Multi-network Poster")
    parser.add_argument(
        "--summary", "-s",
        required=True,
        help="Summary message to post"
    )
    parser.add_argument(
        "--network", "-n",
        choices=["discord", "telegram", "tumblr", "bluesky", "mastodon", "all"],
        default="all",
        help="Target network(s)"
    )
    parser.add_argument(
        "--config", "-c",
        default="delta_commands.json",
        help="Configuration file path"
    )
    parser.add_argument(
        "--report", "-r",
        default=REPORT_FILE,
        help="Report file path"
    )
    
    args = parser.parse_args()
    
    agent = DeltaAgent(config_file=args.config, report_file=args.report)
    
    if args.network == "all":
        report = agent.post_to_all(args.summary)
    else:
        result = agent.post_single(args.network, args.summary)
        report = DeltaReport(
            report_id=f"delta_single_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            summary=args.summary,
            results=[result]
        )
    
    # Print summary
    print("\n" + "=" * 50)
    print("DELTA AGENT RESULTS")
    print("=" * 50)
    print(f"Report ID: {report.report_id}")
    print(f"Timestamp: {report.timestamp}")
    print(f"Summary: {report.summary}")
    print("\nResults:")
    for result in report.results:
        status = "✓ SUCCESS" if result.success else "✗ FAILED"
        print(f"  [{result.network}] {status}")
        if result.error:
            print(f"    Error: {result.error}")
    print("=" * 50)
    
    return report


if __name__ == "__main__":
    main()
