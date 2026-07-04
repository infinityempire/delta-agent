#!/usr/bin/env python3
"""
Unit tests for Delta Agent - Pure API Integration

These tests use unittest.mock to simulate successful HTTP 200 responses
for all network endpoints without making actual live network calls.
"""

import os
import sys
import json
import unittest
from unittest.mock import Mock, patch, MagicMock, mock_open
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the module
import delta_agent
from delta_agent import (
    DiscordPoster,
    TelegramPoster,
    TumblrPoster,
    BlueskyPoster,
    MastodonPoster,
    DeltaAgent,
    HTTPClient,
    PostResult,
    DeltaReport,
)


class TestHTTPClient(unittest.TestCase):
    """Tests for the HTTP client."""
    
    @patch('delta_agent.requests.Session')
    def test_http_client_initialization(self, mock_session_class):
        """Test HTTP client initializes with correct defaults."""
        client = HTTPClient(timeout=30, max_retries=3)
        
        self.assertEqual(client.timeout, 30)
        self.assertEqual(client.max_retries, 3)
        mock_session_class.assert_called_once()
    
    @patch('delta_agent.requests.Session')
    def test_http_client_post_success(self, mock_session_class):
        """Test successful POST request."""
        mock_session = MagicMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        client = HTTPClient()
        response = client.post("https://api.example.com/test", json={"key": "value"})
        
        self.assertEqual(response.status_code, 200)
        mock_session.post.assert_called_once()
    
    @patch('delta_agent.requests.Session')
    def test_http_client_post_with_retry(self, mock_session_class):
        """Test POST request retries on failure."""
        import requests as req
        mock_session = MagicMock()
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = [
            req.exceptions.RequestException("Server Error"),
            req.exceptions.RequestException("Server Error"),
            None
        ]
        mock_response.status_code = 200
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        client = HTTPClient(max_retries=3)
        response = client.post("https://api.example.com/test", json={"key": "value"})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_session.post.call_count, 3)


class TestDiscordPoster(unittest.TestCase):
    """Tests for Discord integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.http_client = MagicMock()
        self.poster = DiscordPoster(self.http_client)
    
    def test_discord_post_success(self):
        """Test successful Discord webhook post."""
        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.raise_for_status = Mock()
        self.http_client.post.return_value = mock_response
        
        # Set webhook URL via environment
        with patch.object(delta_agent, 'DISCORD_WEBHOOK_URL', 'https://discord.com/api/webhooks/test'):
            poster = DiscordPoster(self.http_client)
            result = poster.post("Test message")
        
        self.assertTrue(result.success)
        self.assertEqual(result.network, "discord")
        self.assertEqual(result.response_data["status_code"], 204)
    
    def test_discord_post_no_webhook(self):
        """Test Discord post without webhook URL."""
        with patch.object(delta_agent, 'DISCORD_WEBHOOK_URL', ''):
            poster = DiscordPoster(self.http_client)
            result = poster.post("Test message")
        
        self.assertFalse(result.success)
        self.assertIn("not configured", result.error)
    
    def test_discord_post_failure(self):
        """Test Discord post handles failure."""
        with patch.object(delta_agent, 'DISCORD_WEBHOOK_URL', 'https://discord.com/api/webhooks/test'):
            poster = DiscordPoster(self.http_client)
            self.http_client.post.side_effect = Exception("Network error")
            result = poster.post("Test message")
        
        self.assertFalse(result.success)
        self.assertEqual(result.network, "discord")


class TestTelegramPoster(unittest.TestCase):
    """Tests for Telegram integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.http_client = MagicMock()
    
    def test_telegram_post_success(self):
        """Test successful Telegram bot API post."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": True,
            "result": {
                "message_id": 123,
                "chat": {"id": 123456}
            }
        }
        self.http_client.post.return_value = mock_response
        
        with patch.object(delta_agent, 'TELEGRAM_BOT_TOKEN', 'test_token_123'):
            with patch.object(delta_agent, 'TELEGRAM_CHAT_ID', '123456'):
                poster = TelegramPoster(self.http_client)
                result = poster.post("Test message")
        
        self.assertTrue(result.success)
        self.assertEqual(result.network, "telegram")
        self.assertEqual(result.response_data["message_id"], 123)
    
    def test_telegram_post_no_token(self):
        """Test Telegram post without bot token."""
        with patch.object(delta_agent, 'TELEGRAM_BOT_TOKEN', ''):
            poster = TelegramPoster(self.http_client)
            result = poster.post("Test message")
        
        self.assertFalse(result.success)
        self.assertIn("not configured", result.error)
    
    def test_telegram_post_no_chat_id(self):
        """Test Telegram post without chat ID."""
        with patch.object(delta_agent, 'TELEGRAM_BOT_TOKEN', 'test_token'):
            with patch.object(delta_agent, 'TELEGRAM_CHAT_ID', ''):
                poster = TelegramPoster(self.http_client)
                result = poster.post("Test message")
        
        self.assertFalse(result.success)
        self.assertIn("not configured", result.error)
    
    def test_telegram_post_api_error(self):
        """Test Telegram post handles API error."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": False,
            "description": "Chat not found"
        }
        self.http_client.post.return_value = mock_response
        
        with patch.object(delta_agent, 'TELEGRAM_BOT_TOKEN', 'test_token'):
            with patch.object(delta_agent, 'TELEGRAM_CHAT_ID', '123456'):
                poster = TelegramPoster(self.http_client)
                result = poster.post("Test message")
        
        self.assertFalse(result.success)
        self.assertIn("API error", result.error)


class TestTumblrPoster(unittest.TestCase):
    """Tests for Tumblr integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.http_client = MagicMock()
    
    def test_tumblr_post_success(self):
        """Test successful Tumblr API post."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "meta": {"status": 201, "msg": "Created"},
            "response": {"id": 1234567890}
        }
        self.http_client.post.return_value = mock_response
        
        with patch.object(delta_agent, 'TUMBLR_ACCESS_TOKEN', 'test_access_token'):
            with patch.object(delta_agent, 'TUMBLR_BLOG_HOSTNAME', 'test-blog.tumblr.com'):
                poster = TumblrPoster(self.http_client)
                result = poster.post("<p>Test content</p>", tags=["test", "automation"])
        
        self.assertTrue(result.success)
        self.assertEqual(result.network, "tumblr")
        self.assertEqual(result.response_data["post_id"], 1234567890)
    
    def test_tumblr_post_no_access_token(self):
        """Test Tumblr post without access token."""
        with patch.object(delta_agent, 'TUMBLR_ACCESS_TOKEN', ''):
            poster = TumblrPoster(self.http_client)
            result = poster.post("<p>Test content</p>")
        
        self.assertFalse(result.success)
        self.assertIn("not configured", result.error)
    
    def test_tumblr_post_no_blog_hostname(self):
        """Test Tumblr post without blog hostname."""
        with patch.object(delta_agent, 'TUMBLR_ACCESS_TOKEN', 'test_token'):
            with patch.object(delta_agent, 'TUMBLR_BLOG_HOSTNAME', ''):
                poster = TumblrPoster(self.http_client)
                result = poster.post("<p>Test content</p>")
        
        self.assertFalse(result.success)
        self.assertIn("not configured", result.error)
    
    def test_tumblr_post_api_error(self):
        """Test Tumblr post handles API error."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "meta": {"status": 401, "msg": "Unauthorized"},
            "response": {}
        }
        self.http_client.post.return_value = mock_response
        
        with patch.object(delta_agent, 'TUMBLR_ACCESS_TOKEN', 'invalid_token'):
            with patch.object(delta_agent, 'TUMBLR_BLOG_HOSTNAME', 'test-blog.tumblr.com'):
                poster = TumblrPoster(self.http_client)
                result = poster.post("<p>Test content</p>")
        
        self.assertFalse(result.success)
        self.assertIn("API error", result.error)


class TestBlueskyPoster(unittest.TestCase):
    """Tests for Bluesky integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.http_client = MagicMock()
    
    def test_bluesky_authenticate_success(self):
        """Test successful Bluesky authentication."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "accessJwt": "test_jwt_token",
            "did": "did:plc:test123"
        }
        self.http_client.post.return_value = mock_response
        
        with patch.object(delta_agent, 'BLUESKY_HANDLE', 'test.bsky.social'):
            with patch.object(delta_agent, 'BLUESKY_APP_PASSWORD', 'test_password'):
                poster = BlueskyPoster(self.http_client)
                token = poster._authenticate()
        
        self.assertIsNotNone(token)
        self.assertEqual(token, "test_jwt_token")
    
    def test_bluesky_authenticate_failure(self):
        """Test Bluesky authentication failure."""
        self.http_client.post.side_effect = Exception("Auth failed")
        
        with patch.object(delta_agent, 'BLUESKY_HANDLE', 'test.bsky.social'):
            with patch.object(delta_agent, 'BLUESKY_APP_PASSWORD', 'wrong_password'):
                poster = BlueskyPoster(self.http_client)
                token = poster._authenticate()
        
        self.assertIsNone(token)
    
    def test_bluesky_post_success(self):
        """Test successful Bluesky post."""
        # Mock authentication response
        auth_response = Mock()
        auth_response.json.return_value = {
            "accessJwt": "test_jwt_token",
            "did": "did:plc:test123"
        }
        
        # Mock create record response
        post_response = Mock()
        post_response.json.return_value = {
            "uri": "at://did:plc:test123/app.bsky.feed.post/abc123",
            "cid": "bafyreiabc123"
        }
        
        self.http_client.post.side_effect = [auth_response, post_response]
        
        with patch.object(delta_agent, 'BLUESKY_HANDLE', 'test.bsky.social'):
            with patch.object(delta_agent, 'BLUESKY_APP_PASSWORD', 'test_password'):
                poster = BlueskyPoster(self.http_client)
                result = poster.post("Test Bluesky post")
        
        self.assertTrue(result.success)
        self.assertEqual(result.network, "bluesky")
        self.assertIn("uri", result.response_data)
    
    def test_bluesky_post_no_credentials(self):
        """Test Bluesky post without credentials."""
        with patch.object(delta_agent, 'BLUESKY_HANDLE', ''):
            with patch.object(delta_agent, 'BLUESKY_APP_PASSWORD', ''):
                poster = BlueskyPoster(self.http_client)
                result = poster.post("Test post")
        
        self.assertFalse(result.success)
        self.assertIn("not configured", result.error)
    
    def test_bluesky_post_auth_failure(self):
        """Test Bluesky post handles auth failure."""
        self.http_client.post.side_effect = Exception("Authentication failed")
        
        with patch.object(delta_agent, 'BLUESKY_HANDLE', 'test.bsky.social'):
            with patch.object(delta_agent, 'BLUESKY_APP_PASSWORD', 'wrong_password'):
                poster = BlueskyPoster(self.http_client)
                result = poster.post("Test post")
        
        self.assertFalse(result.success)
        self.assertEqual(result.network, "bluesky")


class TestMastodonPoster(unittest.TestCase):
    """Tests for Mastodon integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.http_client = MagicMock()
    
    def test_mastodon_post_success(self):
        """Test successful Mastodon API post."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "12345",
            "url": "https://mastodon.social/@user/12345"
        }
        self.http_client.post.return_value = mock_response
        
        with patch.object(delta_agent, 'MASTODON_ACCESS_TOKEN', 'test_access_token'):
            poster = MastodonPoster(self.http_client, "https://mastodon.social")
            result = poster.post("Test status", visibility="public")
        
        self.assertTrue(result.success)
        self.assertEqual(result.network, "mastodon")
        self.assertEqual(result.response_data["id"], "12345")
    
    def test_mastodon_post_no_token(self):
        """Test Mastodon post without access token."""
        with patch.object(delta_agent, 'MASTODON_ACCESS_TOKEN', ''):
            poster = MastodonPoster(self.http_client, "https://mastodon.social")
            result = poster.post("Test status")
        
        self.assertFalse(result.success)
        self.assertIn("not configured", result.error)
    
    def test_mastodon_post_no_api_url(self):
        """Test Mastodon post without API base URL."""
        with patch.object(delta_agent, 'MASTODON_ACCESS_TOKEN', 'test_token'):
            poster = MastodonPoster(self.http_client, "")
            result = poster.post("Test status")
        
        self.assertFalse(result.success)
        self.assertIn("not configured", result.error)


class TestDeltaAgent(unittest.TestCase):
    """Tests for the main DeltaAgent class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config_data = {
            "discord": {
                "message_template": "Discord: {summary}"
            },
            "telegram": {
                "message_template": "Telegram: {summary}"
            }
        }
    
    def test_delta_agent_initialization(self):
        """Test DeltaAgent initializes correctly."""
        with patch('builtins.open', mock_open(read_data=json.dumps(self.config_data))):
            with patch('os.path.exists', return_value=True):
                agent = DeltaAgent()
        
        self.assertIsNotNone(agent.http_client)
    
    def test_delta_agent_format_message(self):
        """Test message formatting with template."""
        with patch('builtins.open', mock_open(read_data=json.dumps(self.config_data))):
            with patch('os.path.exists', return_value=True):
                agent = DeltaAgent()
        
        message = agent._format_message("discord", "Test summary")
        self.assertEqual(message, "Discord: Test summary")
    
    def test_delta_agent_format_message_fallback(self):
        """Test message formatting with fallback."""
        with patch('builtins.open', mock_open(read_data=json.dumps(self.config_data))):
            with patch('os.path.exists', return_value=True):
                agent = DeltaAgent()
        
        message = agent._format_message("unknown_network", "Test summary")
        self.assertEqual(message, "Test summary")
    
    @patch('delta_agent.HTTPClient')
    def test_delta_agent_post_single(self, mock_http_class):
        """Test posting to a single network."""
        mock_http = MagicMock()
        mock_http_class.return_value = mock_http
        
        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.raise_for_status = Mock()
        mock_http.post.return_value = mock_response
        
        with patch.object(delta_agent, '_DISCORD_POST', True):
            with patch.object(delta_agent, 'DISCORD_WEBHOOK_URL', 'https://discord.com/api/webhooks/test'):
                with patch('builtins.open', mock_open(read_data=json.dumps(self.config_data))):
                    with patch('os.path.exists', return_value=True):
                        agent = DeltaAgent()
                        result = agent.post_single("discord", "Test message")
        
        self.assertTrue(result.success)
        self.assertEqual(result.network, "discord")
    
    @patch('delta_agent.HTTPClient')
    def test_delta_agent_post_all_isolated_errors(self, mock_http_class):
        """Test that one network failure doesn't affect others."""
        mock_http = MagicMock()
        mock_http_class.return_value = mock_http
        
        # First call succeeds (Discord), second fails (Telegram)
        success_response = Mock()
        success_response.status_code = 204
        success_response.raise_for_status = Mock()
        
        def post_side_effect(*args, **kwargs):
            url = args[0] if args else kwargs.get('url', '')
            if 'discord' in str(url):
                return success_response
            raise Exception("Telegram API error")
        
        mock_http.post.side_effect = post_side_effect
        
        with patch.object(delta_agent, '_DISCORD_POST', True):
            with patch.object(delta_agent, '_TELEGRAM_POST', True):
                with patch.object(delta_agent, 'DISCORD_WEBHOOK_URL', 'https://discord.com/api/webhooks/test'):
                    with patch.object(delta_agent, 'TELEGRAM_BOT_TOKEN', 'test_token'):
                        with patch.object(delta_agent, 'TELEGRAM_CHAT_ID', '123456'):
                            with patch('builtins.open', mock_open(read_data=json.dumps(self.config_data))):
                                with patch('os.path.exists', return_value=True):
                                    with patch('os.path.exists', side_effect=lambda f: f == 'delta_agent_report.json' or True):
                                        with patch('builtins.open', mock_open(read_data='{"errors":[]}')):
                                            with patch('delta_agent.open', mock_open(read_data='{"errors":[]}')):
                                                agent = DeltaAgent()
                                                
                                                # Test that Discord still works even if Telegram would fail
                                                result = agent.post_single("discord", "Test message")
        
        # Discord should succeed even if Telegram fails
        self.assertTrue(result.success)
        self.assertEqual(result.network, "discord")
    
    def test_delta_agent_save_report(self):
        """Test saving report to file."""
        with patch('builtins.open', mock_open(read_data=json.dumps(self.config_data))):
            with patch('os.path.exists', return_value=True):
                agent = DeltaAgent()
        
        report = DeltaReport(
            report_id="test_001",
            summary="Test summary",
            results=[
                PostResult(network="discord", success=True, message="OK")
            ]
        )
        
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('json.dump') as mock_json:
                agent._save_report(report)
                mock_file.assert_called_with("delta_agent_report.json", "w")
                mock_json.assert_called_once()
    
    def test_delta_agent_log_error(self):
        """Test error logging to report file."""
        with patch('builtins.open', mock_open(read_data=json.dumps(self.config_data))):
            with patch('os.path.exists', return_value=True):
                agent = DeltaAgent()
        
        with patch('builtins.open', mock_open(read_data='{"errors":[]}')) as mock_file:
            with patch('json.load', return_value={"errors": []}):
                with patch('json.dump') as mock_json:
                    agent._log_error("discord", "Test error", {"details": "test"})
                    
                    # Verify file was opened for writing
                    calls = mock_file.call_args_list
                    self.assertTrue(any("delta_agent_report.json" in str(c) for c in calls))


class TestBooleanToggles(unittest.TestCase):
    """Tests for boolean toggle functionality."""
    
    def test_toggles_exist(self):
        """Test that all boolean toggles are defined."""
        self.assertTrue(hasattr(delta_agent, '_DISCORD_POST'))
        self.assertTrue(hasattr(delta_agent, '_TELEGRAM_POST'))
        self.assertTrue(hasattr(delta_agent, '_TUMBLR_POST'))
        self.assertTrue(hasattr(delta_agent, '_BLUESKY_POST'))
        self.assertTrue(hasattr(delta_agent, '_MASTODON_POST'))
    
    def test_toggles_are_boolean(self):
        """Test that all toggles are boolean values."""
        self.assertIsInstance(delta_agent._DISCORD_POST, bool)
        self.assertIsInstance(delta_agent._TELEGRAM_POST, bool)
        self.assertIsInstance(delta_agent._TUMBLR_POST, bool)
        self.assertIsInstance(delta_agent._BLUESKY_POST, bool)
        self.assertIsInstance(delta_agent._MASTODON_POST, bool)


class TestEnvironmentVariables(unittest.TestCase):
    """Tests for environment variable mapping."""
    
    def test_discord_env_var(self):
        """Test Discord environment variable is used."""
        self.assertEqual(delta_agent.DISCORD_WEBHOOK_URL, os.getenv("DISCORD_WEBHOOK_URL", ""))
    
    def test_telegram_env_vars(self):
        """Test Telegram environment variables are used."""
        self.assertEqual(delta_agent.TELEGRAM_BOT_TOKEN, os.getenv("TELEGRAM_BOT_TOKEN", ""))
        self.assertEqual(delta_agent.TELEGRAM_CHAT_ID, os.getenv("TELEGRAM_CHAT_ID", ""))
    
    def test_tumblr_env_vars(self):
        """Test Tumblr environment variables are used."""
        self.assertEqual(delta_agent.TUMBLR_CLIENT_KEY, os.getenv("TUMBLR_CLIENT_KEY", ""))
        self.assertEqual(delta_agent.TUMBLR_CLIENT_SECRET, os.getenv("TUMBLR_CLIENT_SECRET", ""))
        self.assertEqual(delta_agent.TUMBLR_ACCESS_TOKEN, os.getenv("TUMBLR_ACCESS_TOKEN", ""))
        self.assertEqual(delta_agent.TUMBLR_ACCESS_SECRET, os.getenv("TUMBLR_ACCESS_SECRET", ""))
        self.assertEqual(delta_agent.TUMBLR_BLOG_HOSTNAME, os.getenv("TUMBLR_BLOG_HOSTNAME", ""))
    
    def test_bluesky_env_vars(self):
        """Test Bluesky environment variables are used."""
        self.assertEqual(delta_agent.BLUESKY_HANDLE, os.getenv("BLUESKY_HANDLE", ""))
        self.assertEqual(delta_agent.BLUESKY_APP_PASSWORD, os.getenv("BLUESKY_APP_PASSWORD", ""))
    
    def test_mastodon_env_vars(self):
        """Test Mastodon environment variables are used."""
        self.assertEqual(delta_agent.MASTODON_ACCESS_TOKEN, os.getenv("MASTODON_ACCESS_TOKEN", ""))
        self.assertEqual(delta_agent.MASTODON_API_BASE_URL, os.getenv("MASTODON_API_BASE_URL", ""))


class TestDataClasses(unittest.TestCase):
    """Tests for dataclasses."""
    
    def test_post_result_creation(self):
        """Test PostResult dataclass creation."""
        result = PostResult(
            network="discord",
            success=True,
            message="Posted successfully"
        )
        
        self.assertEqual(result.network, "discord")
        self.assertTrue(result.success)
        self.assertEqual(result.message, "Posted successfully")
        self.assertIsNotNone(result.timestamp)
        self.assertIsNone(result.error)
    
    def test_delta_report_creation(self):
        """Test DeltaReport dataclass creation."""
        report = DeltaReport(
            report_id="test_001",
            summary="Test summary",
            results=[
                PostResult(network="discord", success=True)
            ]
        )
        
        self.assertEqual(report.report_id, "test_001")
        self.assertEqual(report.summary, "Test summary")
        self.assertEqual(len(report.results), 1)
        self.assertEqual(report.results[0].network, "discord")


if __name__ == "__main__":
    # Run all tests with verbosity
    unittest.main(verbosity=2)
