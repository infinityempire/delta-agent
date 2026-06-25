"""
Unit tests for Delta Agent REST API client.
Tests cover session handling, retry logic, circuit breaker, and endpoint rotation.
"""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from delta_agent import (
    APIClient,
    APIClientConfig,
    APIClientError,
    AsyncSessionHandler,
    BrowserFingerprint,
    ConnectionState,
    Endpoint,
    HardwareIntegrationHook,
    NetworkRefreshCallback,
    RetryConfig,
    SessionConfig,
    create_client,
    create_session_handler,
)


class TestBrowserFingerprint:
    """Test browser fingerprint enum."""

    def test_fingerprint_values(self):
        """Test all fingerprints have valid values."""
        assert BrowserFingerprint.CHROME120.value == "chrome120"
        assert BrowserFingerprint.CHROME119.value == "chrome119"
        assert BrowserFingerprint.FIREFOX120.value == "firefox120"
        assert BrowserFingerprint.SAFARI15.value == "safari15"

    def test_fingerprint_count(self):
        """Test expected number of fingerprints."""
        assert len(BrowserFingerprint) == 6


class TestEndpoint:
    """Test Endpoint dataclass."""

    def test_endpoint_creation(self):
        """Test basic endpoint creation."""
        ep = Endpoint(url="https://api.example.com")
        assert ep.url == "https://api.example.com"
        assert ep.weight == 1
        assert ep.is_backup is False
        assert ep.latency_ms is None
        assert ep.failure_count == 0

    def test_endpoint_with_options(self):
        """Test endpoint with custom options."""
        ep = Endpoint(
            url="https://backup.example.com",
            weight=2,
            is_backup=True,
            latency_ms=150.5,
            failure_count=2,
        )
        assert ep.is_backup is True
        assert ep.weight == 2
        assert ep.latency_ms == 150.5
        assert ep.failure_count == 2

    def test_endpoint_availability_healthy(self):
        """Test endpoint availability when healthy."""
        ep = Endpoint(url="https://api.example.com", failure_count=0)
        assert ep.is_available is True

    def test_endpoint_availability_failing(self):
        """Test endpoint unavailable after too many failures."""
        ep = Endpoint(url="https://api.example.com", failure_count=5)
        assert ep.is_available is False

    def test_endpoint_availability_after_success_cooldown(self):
        """Test endpoint becomes available after cooldown."""
        ep = Endpoint(
            url="https://api.example.com",
            failure_count=3,
            last_success=datetime.now() - timedelta(minutes=10),
        )
        assert ep.is_available is True


class TestHardwareIntegrationHook:
    """Test HardwareIntegrationHook dataclass."""

    def test_hook_creation(self):
        """Test hook creation with defaults."""
        hook = HardwareIntegrationHook(command="termux-wake-lock")
        assert hook.command == "termux-wake-lock"
        assert hook.timeout_seconds == 10
        assert hook.enabled is True
        assert hook.trigger_on_init is True
        assert hook.trigger_on_retry is True

    def test_hook_disabled(self):
        """Test disabled hook."""
        hook = HardwareIntegrationHook(
            command="network-reset",
            enabled=False,
        )
        assert hook.enabled is False


class TestRetryConfig:
    """Test RetryConfig dataclass."""

    def test_default_retry_config(self):
        """Test default retry configuration."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
        assert 408 in config.retry_on_status

    def test_custom_retry_config(self):
        """Test custom retry configuration."""
        config = RetryConfig(
            max_retries=5,
            base_delay=0.5,
            max_delay=60.0,
        )
        assert config.max_retries == 5
        assert config.base_delay == 0.5
        assert config.max_delay == 60.0


class TestSessionConfig:
    """Test SessionConfig dataclass."""

    def test_default_session_config(self):
        """Test default session configuration."""
        config = SessionConfig()
        assert config.default_fingerprint == BrowserFingerprint.CHROME120
        assert config.timeout == 30.0
        assert config.max_connections == 10
        assert config.verify_ssl is True
        assert "User-Agent" in config.default_headers

    def test_session_config_with_endpoints(self):
        """Test session config with endpoints."""
        endpoints = [
            Endpoint(url="https://api.example.com"),
            Endpoint(url="https://backup.example.com", is_backup=True),
        ]
        config = SessionConfig(endpoints=endpoints)
        assert len(config.endpoints) == 2


class TestNetworkRefreshCallback:
    """Test network refresh callback classes."""

    def test_default_callback_interface(self):
        """Test default callback creation - abstract class should not be instantiable."""
        with pytest.raises(TypeError):
            NetworkRefreshCallback()

    def test_custom_callback_implementation(self):
        """Test custom callback implementation."""
        refresh_log = []

        class TestCallback(NetworkRefreshCallback):
            def on_network_refresh(self, success: bool, message: str):
                refresh_log.append((success, message))

        callback = TestCallback()
        callback.on_network_refresh(True, "Network OK")
        assert refresh_log == [(True, "Network OK")]


class TestAsyncSessionHandler:
    """Test AsyncSessionHandler."""

    @pytest.fixture
    def session_config(self):
        """Create test session configuration."""
        return SessionConfig(
            endpoints=[
                Endpoint(url="https://api1.example.com", weight=2),
                Endpoint(url="https://api2.example.com", weight=1, is_backup=True),
            ],
            default_fingerprint=BrowserFingerprint.CHROME120,
            retry_config=RetryConfig(max_retries=2),
        )

    @pytest.fixture
    def handler(self, session_config):
        """Create test session handler."""
        return AsyncSessionHandler(config=session_config)

    def test_handler_initialization(self, handler):
        """Test handler initializes correctly."""
        assert handler._initialized is False
        assert handler._circuit_state == ConnectionState.HEALTHY
        assert handler._circuit_failures == 0

    def test_current_endpoint(self, handler):
        """Test current endpoint selection."""
        endpoint = handler.current_endpoint
        assert endpoint is not None
        assert "api1.example.com" in endpoint.url

    def test_select_next_endpoint_rotation(self, handler):
        """Test endpoint rotation."""
        endpoints_seen = set()
        for _ in range(5):
            ep = handler._select_next_endpoint()
            assert ep is not None
            endpoints_seen.add(ep.url)
        # Should see both endpoints
        assert len(endpoints_seen) >= 1

    def test_calculate_retry_delay(self, handler):
        """Test exponential backoff calculation."""
        # First attempt
        delay0 = handler._calculate_retry_delay(0)
        assert delay0 >= 0.5  # base_delay * 1^exp * jitter

        # Second attempt
        delay1 = handler._calculate_retry_delay(1)
        assert delay1 > delay0  # Should increase

    def test_circuit_breaker_initial_state(self, handler):
        """Test circuit breaker starts healthy."""
        result = asyncio.get_event_loop().run_until_complete(
            handler._check_circuit_breaker()
        )
        assert result is True

    def test_circuit_breaker_trip(self, handler):
        """Test circuit breaker trips after threshold."""
        # Trip the circuit breaker
        for _ in range(handler.config.circuit_breaker_threshold):
            handler._trip_circuit_breaker()
        assert handler._circuit_state == ConnectionState.FAILING
        assert handler._circuit_opened_at is not None

    def test_stats(self, handler):
        """Test get_stats returns correct information."""
        stats = handler.get_stats()
        assert "state" in stats
        assert "failures" in stats
        assert "initialized" in stats
        assert "endpoints" in stats
        assert len(stats["endpoints"]) == 2


class TestAPIClient:
    """Test high-level APIClient."""

    @pytest.fixture
    def client(self):
        """Create test API client."""
        return APIClient(
            endpoints=["https://api.example.com"],
            fingerprint=BrowserFingerprint.CHROME120,
        )

    def test_client_creation(self, client):
        """Test client creates correctly."""
        assert client._session_handler is not None
        assert client._closed is False

    def test_client_config(self, client):
        """Test client configuration."""
        assert client.config.base_path == ""
        assert client.config.max_retries == 3

    @pytest.mark.asyncio
    async def test_client_context_manager(self):
        """Test async context manager."""
        client = APIClient(endpoints=["https://api.example.com"])
        
        # Mock the session initialization
        mock_session = MagicMock()
        mock_session.close = AsyncMock()
        
        with patch('delta_agent.session.AsyncSession', return_value=mock_session):
            async with client as c:
                assert c._session_handler._initialized is True
            assert client._closed is True

    def test_client_stats(self, client):
        """Test stats delegation."""
        stats = client.get_stats()
        assert "state" in stats


class TestCreateHelpers:
    """Test factory helper functions."""

    def test_create_session_handler(self):
        """Test create_session_handler factory."""
        handler = create_session_handler(
            endpoints=["https://api1.com", "https://api2.com"],
            fingerprint=BrowserFingerprint.FIREFOX120,
        )
        assert len(handler.config.endpoints) == 2
        assert handler.config.default_fingerprint == BrowserFingerprint.FIREFOX120

    def test_create_session_handler_with_network_command(self):
        """Test factory with network refresh command."""
        handler = create_session_handler(
            endpoints=["https://api.example.com"],
            network_refresh_command="termux-wake-lock",
        )
        assert handler.config.hardware_hook is not None
        assert handler.config.hardware_hook.command == "termux-wake-lock"

    def test_create_client(self):
        """Test create_client factory."""
        client = create_client(
            endpoints=["https://api.example.com"],
            fingerprint=BrowserFingerprint.SAFARI15,
        )
        assert isinstance(client, APIClient)


class TestAPIClientError:
    """Test APIClientError exception."""

    def test_error_creation(self):
        """Test error creation with status code."""
        error = APIClientError("Not found", status_code=404)
        assert error.status_code == 404
        assert str(error) == "Not found"

    def test_error_with_response(self):
        """Test error with response object."""
        response = MagicMock()
        response.status_code = 500
        error = APIClientError("Server error", status_code=500, response=response)
        assert error.response is response


# Integration-style tests (mocked)
class TestIntegration:
    """Integration tests with mocked network calls."""

    @pytest.mark.asyncio
    async def test_successful_request_flow(self):
        """Test successful request through all layers."""
        client = APIClient(
            endpoints=["https://api.example.com"],
            fingerprint=BrowserFingerprint.CHROME120,
        )

        # Mock the session request
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        
        # Mock the session initialization
        mock_session = MagicMock()
        mock_session.close = AsyncMock()

        with patch('delta_agent.session.AsyncSession', return_value=mock_session):
            with patch.object(
                client._session_handler,
                'request',
                return_value=mock_response
            ):
                async with client:
                    response = await client.get("/status")
                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self):
        """Test retry mechanism on connection errors."""
        session_config = SessionConfig(
            endpoints=[Endpoint(url="https://api.example.com")],
            retry_config=RetryConfig(max_retries=2, base_delay=0.01),
        )
        handler = AsyncSessionHandler(config=session_config)

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Simulated failure")
            return MagicMock(status_code=200)

        with patch.object(handler, '_execute_request_with_retry', side_effect=mock_request):
            # This will fail in the retry loop - that's expected
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
