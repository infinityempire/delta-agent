"""
Async HTTP session handler with curl_cffi for TLS/JA3 fingerprinting.
Designed for embedded/mobile Linux environments (Termux on ARM).
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, TypeVar

import curl_cffi
from curl_cffi.requests import AsyncSession, Response

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BrowserFingerprint(Enum):
    """Supported browser TLS/JA3 fingerprints."""
    CHROME120 = "chrome120"
    CHROME119 = "chrome119"
    CHROME116 = "chrome116"
    FIREFOX120 = "firefox120"
    FIREFOX119 = "firefox119"
    SAFARI15 = "safari15"


class ConnectionState(Enum):
    """Session connection state."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"
    OFFLINE = "offline"


@dataclass
class Endpoint:
    """Represents an API endpoint/gateway."""
    url: str
    weight: int = 1
    is_backup: bool = False
    latency_ms: float | None = None
    failure_count: int = 0
    last_success: datetime | None = None
    last_attempt: datetime | None = None

    @property
    def is_available(self) -> bool:
        """Check if endpoint is considered available."""
        if self.failure_count >= 5:
            return False
        if self.last_success is not None:
            cooldown = timedelta(minutes=5) if self.is_backup else timedelta(minutes=2)
            if datetime.now() - self.last_success > cooldown:
                return True
        return True


@dataclass
class HardwareIntegrationHook:
    """Hook for hardware/OS integration commands."""
    command: str
    timeout_seconds: int = 10
    enabled: bool = True
    trigger_on_init: bool = True
    trigger_on_retry: bool = True
    trigger_on_failure: bool = False


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on_status: tuple[int, ...] = (408, 429, 500, 502, 503, 504)


@dataclass
class SessionConfig:
    """Main configuration for the async session handler."""
    endpoints: list[Endpoint] = field(default_factory=list)
    default_fingerprint: BrowserFingerprint = BrowserFingerprint.CHROME120
    timeout: float = 30.0
    max_connections: int = 10
    keepalive: bool = True
    verify_ssl: bool = True
    hardware_hook: HardwareIntegrationHook | None = None
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 60.0
    default_headers: dict[str, str] = field(default_factory=lambda: {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; Termux) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    })


class NetworkRefreshCallback(ABC):
    """Abstract base for network refresh callbacks."""

    @abstractmethod
    def on_network_refresh(self, success: bool, message: str) -> None:
        """Called when network refresh completes."""
        pass


class DefaultNetworkRefreshCallback(NetworkRefreshCallback):
    """Default implementation that executes OS commands."""

    def __init__(self, hook: HardwareIntegrationHook | None = None):
        self.hook = hook

    def on_network_refresh(self, success: bool, message: str) -> None:
        logger.info(f"Network refresh: {message}")
        if self.hook and self.hook.enabled:
            try:
                result = subprocess.run(
                    self.hook.command,
                    shell=True,
                    capture_output=True,
                    timeout=self.hook.timeout_seconds,
                )
                if result.returncode == 0:
                    logger.info("Network refresh command succeeded")
                else:
                    logger.warning(f"Network refresh command failed: {result.stderr.decode()}")
            except subprocess.TimeoutExpired:
                logger.warning("Network refresh command timed out")
            except Exception as e:
                logger.error(f"Network refresh command error: {e}")


class AsyncSessionHandler:
    """
    Asynchronous session handler with curl_cffi for REST API consumption.
    
    Features:
    - TLS/JA3 fingerprint emulation (Chrome/Firefox)
    - Endpoint rotation with weighted failover
    - Automatic retry with exponential backoff
    - Circuit breaker pattern for fault tolerance
    - Hardware integration hooks for OS commands
    - ARM/Termux optimized
    """

    def __init__(
        self,
        config: SessionConfig | None = None,
        network_callback: NetworkRefreshCallback | None = None,
    ):
        self.config = config or SessionConfig()
        self.network_callback = network_callback or DefaultNetworkRefreshCallback(
            self.config.hardware_hook
        )
        self._session: AsyncSession | None = None
        self._circuit_state = ConnectionState.HEALTHY
        self._circuit_failures = 0
        self._circuit_opened_at: datetime | None = None
        self._current_endpoint_index = 0
        self._lock = asyncio.Lock()
        self._initialized = False

    @property
    def current_endpoint(self) -> Endpoint | None:
        """Get the current active endpoint."""
        available = [ep for ep in self.config.endpoints if ep.is_available]
        if not available:
            return None
        idx = self._current_endpoint_index % len(available)
        return available[idx]

    def _select_next_endpoint(self) -> Endpoint | None:
        """Select next endpoint using weighted rotation."""
        available = [ep for ep in self.config.endpoints if ep.is_available]
        if not available:
            return None
        
        # Sort by weight (higher weight = more likely to be selected)
        weighted = []
        for ep in available:
            weighted.extend([ep] * ep.weight)
        
        if not weighted:
            return available[0]
        
        idx = self._current_endpoint_index % len(weighted)
        selected = weighted[idx]
        self._current_endpoint_index += 1
        return selected

    async def initialize(self) -> None:
        """Initialize the session with hardware hook if configured."""
        if self._initialized:
            return

        # Trigger hardware hook on initialization if enabled
        if (
            self.config.hardware_hook
            and self.config.hardware_hook.trigger_on_init
            and self.config.hardware_hook.enabled
        ):
            await self._execute_network_refresh()

        # Create curl_cffi session with fingerprint
        impersonate = self.config.default_fingerprint.value
        self._session = AsyncSession(
            impersonate=impersonate,
            timeout=self.config.timeout,
            verify=self.config.verify_ssl,
            headers=self.config.default_headers,
        )
        self._initialized = True
        logger.info(f"Session initialized with {impersonate} fingerprint")

    async def _execute_network_refresh(self) -> None:
        """Execute the network refresh command."""
        if not self.config.hardware_hook:
            return

        hook = self.config.hardware_hook
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    hook.command,
                    shell=True,
                    capture_output=True,
                    timeout=hook.timeout_seconds,
                ),
            )
            success = result.returncode == 0
            message = (
                "Network refresh succeeded"
                if success
                else f"Network refresh failed: {result.stderr.decode()}"
            )
            self.network_callback.on_network_refresh(success, message)
        except subprocess.TimeoutExpired:
            self.network_callback.on_network_refresh(False, "Network refresh timed out")
        except Exception as e:
            self.network_callback.on_network_refresh(False, str(e))

    async def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows requests."""
        if self._circuit_state == ConnectionState.HEALTHY:
            return True

        if self._circuit_opened_at is None:
            return False

        elapsed = (datetime.now() - self._circuit_opened_at).total_seconds()
        if elapsed >= self.config.circuit_breaker_timeout:
            logger.info("Circuit breaker timeout elapsed, attempting reset")
            self._circuit_state = ConnectionState.DEGRADED
            return True

        return False

    def _trip_circuit_breaker(self) -> None:
        """Trip the circuit breaker."""
        self._circuit_failures += 1
        if self._circuit_failures >= self.config.circuit_breaker_threshold:
            if self._circuit_state != ConnectionState.OFFLINE:
                logger.warning(
                    f"Circuit breaker tripped after {self._circuit_failures} failures"
                )
                self._circuit_state = ConnectionState.FAILING
                self._circuit_opened_at = datetime.now()

    async def _reset_circuit_breaker(self) -> None:
        """Reset circuit breaker on successful request."""
        if self._circuit_failures > 0:
            self._circuit_failures = 0
        if self._circuit_state in (ConnectionState.FAILING, ConnectionState.DEGRADED):
            self._circuit_state = ConnectionState.HEALTHY
            logger.info("Circuit breaker reset")

    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and optional jitter."""
        delay = self.config.retry_config.base_delay * (
            self.config.retry_config.exponential_base ** attempt
        )
        delay = min(delay, self.config.retry_config.max_delay)
        
        if self.config.retry_config.jitter:
            import random
            delay *= 0.5 + random.random()

        return delay

    async def _execute_request_with_retry(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Execute request with retry logic."""
        last_error: Exception | None = None

        for attempt in range(self.config.retry_config.max_retries + 1):
            try:
                if self._session is None:
                    raise RuntimeError("Session not initialized")

                start_time = datetime.now()
                response = await self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json,
                    params=params,
                    **kwargs,
                )
                elapsed = (datetime.now() - start_time).total_seconds() * 1000

                # Update endpoint latency
                endpoint = self.current_endpoint
                if endpoint:
                    endpoint.latency_ms = elapsed
                    endpoint.last_success = datetime.now()
                    endpoint.failure_count = 0

                await self._reset_circuit_breaker()
                return response

            except (curl_cffi.requests.errors.RequestsError, 
                    ConnectionError, asyncio.TimeoutError) as e:
                last_error = e
                logger.warning(
                    f"Request failed (attempt {attempt + 1}): {type(e).__name__}: {e}"
                )

                # Trigger hardware hook on retry if configured
                if (
                    attempt < self.config.retry_config.max_retries
                    and self.config.hardware_hook
                    and self.config.hardware_hook.trigger_on_retry
                    and self.config.hardware_hook.enabled
                ):
                    await self._execute_network_refresh()

                # Update endpoint failure count
                endpoint = self.current_endpoint
                if endpoint:
                    endpoint.failure_count += 1
                    endpoint.last_attempt = datetime.now()

                self._trip_circuit_breaker()

                if attempt < self.config.retry_config.max_retries:
                    delay = self._calculate_retry_delay(attempt)
                    logger.info(f"Retrying in {delay:.2f} seconds...")
                    await asyncio.sleep(delay)
                else:
                    break

        raise last_error or RuntimeError("Request failed after all retries")

    async def request(
        self,
        method: str,
        path: str = "",
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        use_backup: bool = False,
        **kwargs: Any,
    ) -> Response:
        """
        Make an HTTP request with endpoint rotation and retry logic.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            path: API path (appended to endpoint base URL)
            headers: Optional headers to merge with defaults
            json: JSON request body
            params: URL query parameters
            use_backup: If True, prefer backup endpoints
            **kwargs: Additional arguments passed to curl_cffi
        
        Returns:
            Response object from curl_cffi
        """
        if not self._initialized:
            await self.initialize()

        if not await self._check_circuit_breaker():
            raise RuntimeError(
                f"Circuit breaker open: {self._circuit_state.value}. "
                f"Try again later."
            )

        # Merge headers with defaults
        request_headers = dict(self.config.default_headers)
        if headers:
            request_headers.update(headers)

        # Select endpoint
        endpoints = (
            [ep for ep in self.config.endpoints if ep.is_backup]
            if use_backup
            else self.config.endpoints
        )
        
        # Try endpoints in rotation
        last_error: Exception | None = None
        tried_endpoints: set[str] = set()

        while len(tried_endpoints) < len(endpoints):
            endpoint = self._select_next_endpoint()
            if endpoint is None or endpoint.url in tried_endpoints:
                break

            tried_endpoints.add(endpoint.url)
            url = f"{endpoint.url.rstrip('/')}/{path.lstrip('/')}"

            try:
                return await self._execute_request_with_retry(
                    method=method,
                    url=url,
                    headers=request_headers,
                    json=json,
                    params=params,
                    **kwargs,
                )
            except Exception as e:
                last_error = e
                logger.warning(f"Endpoint {endpoint.url} failed: {e}")
                continue

        raise last_error or RuntimeError("All endpoints exhausted")

    async def get(
        self,
        path: str = "",
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        use_backup: bool = False,
        **kwargs: Any,
    ) -> Response:
        """Make GET request."""
        return await self.request("GET", path, headers, params=params, use_backup=use_backup, **kwargs)

    async def post(
        self,
        path: str = "",
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        use_backup: bool = False,
        **kwargs: Any,
    ) -> Response:
        """Make POST request."""
        return await self.request("POST", path, headers, json=json, use_backup=use_backup, **kwargs)

    async def put(
        self,
        path: str = "",
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        use_backup: bool = False,
        **kwargs: Any,
    ) -> Response:
        """Make PUT request."""
        return await self.request("PUT", path, headers, json=json, use_backup=use_backup, **kwargs)

    async def delete(
        self,
        path: str = "",
        headers: dict[str, str] | None = None,
        use_backup: bool = False,
        **kwargs: Any,
    ) -> Response:
        """Make DELETE request."""
        return await self.request("DELETE", path, headers, use_backup=use_backup, **kwargs)

    async def close(self) -> None:
        """Close the session and cleanup resources."""
        if self._session:
            await self._session.close()
            self._session = None
            self._initialized = False
            logger.info("Session closed")

    def get_stats(self) -> dict[str, Any]:
        """Get session statistics."""
        return {
            "state": self._circuit_state.value,
            "failures": self._circuit_failures,
            "initialized": self._initialized,
            "endpoints": [
                {
                    "url": ep.url,
                    "is_backup": ep.is_backup,
                    "latency_ms": ep.latency_ms,
                    "failure_count": ep.failure_count,
                    "is_available": ep.is_available,
                }
                for ep in self.config.endpoints
            ],
        }

    async def __aenter__(self) -> "AsyncSessionHandler":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()


# Convenience function for quick setup
def create_session_handler(
    endpoints: list[str],
    fingerprint: BrowserFingerprint = BrowserFingerprint.CHROME120,
    network_refresh_command: str | None = None,
    **kwargs: Any,
) -> AsyncSessionHandler:
    """
    Create a session handler with common defaults.
    
    Args:
        endpoints: List of endpoint URLs
        fingerprint: Browser fingerprint to emulate
        network_refresh_command: Command to refresh network interface
        **kwargs: Additional SessionConfig parameters
    
    Returns:
        Configured AsyncSessionHandler instance
    """
    endpoint_objects = [Endpoint(url=url) for url in endpoints]
    
    hardware_hook = None
    if network_refresh_command:
        hardware_hook = HardwareIntegrationHook(command=network_refresh_command)
    
    config = SessionConfig(
        endpoints=endpoint_objects,
        default_fingerprint=fingerprint,
        hardware_hook=hardware_hook,
        **kwargs,
    )
    
    return AsyncSessionHandler(config=config)
