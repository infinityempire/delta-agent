"""
High-level REST API client built on AsyncSessionHandler.
Provides a clean interface for API consumption with automatic retry,
endpoint rotation, and hardware integration hooks.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, TypeVar

from .session import (
    AsyncSessionHandler,
    BrowserFingerprint,
    Endpoint,
    HardwareIntegrationHook,
    NetworkRefreshCallback,
    RetryConfig,
    SessionConfig,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class APIClientConfig:
    """Configuration for the high-level API client."""
    base_path: str = ""
    default_timeout: float = 30.0
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    max_retries: int = 3
    retry_on_timeout: bool = True
    raise_on_error: bool = True
    error_statuses: tuple[int, ...] = (400, 401, 403, 404, 500, 502, 503, 504)


class APIClientError(Exception):
    """Base exception for API client errors."""
    def __init__(self, message: str, status_code: int | None = None, response: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class APIClient:
    """
    High-level REST API client with ergonomic interface.
    
    Built on AsyncSessionHandler with curl_cffi for TLS fingerprinting.
    Optimized for embedded/mobile Linux environments (Termux on ARM).
    
    Example:
        async with APIClient(
            endpoints=["https://api.example.com", "https://backup.example.com"],
            fingerprint=BrowserFingerprint.CHROME120,
        ) as client:
            response = await client.get("/users/123")
            data = response.json()
            
            await client.post("/users", json={"name": "John"})
    """

    def __init__(
        self,
        endpoints: list[str],
        *,
        config: APIClientConfig | None = None,
        session_config: SessionConfig | None = None,
        fingerprint: BrowserFingerprint = BrowserFingerprint.CHROME120,
        network_refresh_command: str | None = None,
        hardware_hook: HardwareIntegrationHook | None = None,
        network_callback: NetworkRefreshCallback | None = None,
        **kwargs: Any,
    ):
        """
        Initialize the API client.
        
        Args:
            endpoints: List of base endpoint URLs
            config: High-level API client configuration
            session_config: Low-level session configuration
            fingerprint: Browser TLS/JA3 fingerprint to emulate
            network_refresh_command: OS command to refresh network interface
            hardware_hook: Custom hardware integration hook
            network_callback: Callback for network refresh events
            **kwargs: Additional session configuration parameters
        """
        self.config = config or APIClientConfig()
        
        # Build endpoint objects
        endpoint_objects = [
            Endpoint(url=url.rstrip("/")) for url in endpoints
        ]
        
        # Build hardware hook if command provided
        if network_refresh_command and hardware_hook is None:
            hardware_hook = HardwareIntegrationHook(
                command=network_refresh_command,
                trigger_on_init=True,
                trigger_on_retry=True,
            )
        
        # Build session config
        retry_config = RetryConfig(
            max_retries=self.config.max_retries,
        )
        
        if session_config is None:
            session_config = SessionConfig(
                endpoints=endpoint_objects,
                default_fingerprint=fingerprint,
                timeout=self.config.default_timeout,
                hardware_hook=hardware_hook,
                retry_config=retry_config,
                default_headers={
                    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Termux) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0.0.0 Mobile Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Connection": "keep-alive",
                },
                **kwargs,
            )
        
        self._session_handler = AsyncSessionHandler(
            config=session_config,
            network_callback=network_callback,
        )
        self._closed = False

    async def initialize(self) -> None:
        """Initialize the underlying session handler."""
        if self._closed:
            raise RuntimeError("Client has been closed")
        await self._session_handler.initialize()

    async def close(self) -> None:
        """Close the client and release resources."""
        await self._session_handler.close()
        self._closed = True

    async def _request(
        self,
        method: str,
        path: str = "",
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Internal request method with error handling.
        
        Args:
            method: HTTP method
            path: API path
            headers: Additional headers
            json: JSON body
            params: Query parameters
            timeout: Request timeout override
            **kwargs: Additional arguments
        
        Returns:
            Parsed response JSON or Response object based on config
        """
        if self._closed:
            raise RuntimeError("Client has been closed")

        response = await self._session_handler.request(
            method=method,
            path=f"{self.config.base_path}/{path}".replace("//", "/"),
            headers=headers,
            json=json,
            params=params,
            **kwargs,
        )

        if self.config.raise_on_error:
            if response.status_code in self.config.error_statuses:
                raise APIClientError(
                    f"API error: {response.status_code}",
                    status_code=response.status_code,
                    response=response,
                )

        return response

    async def get(
        self,
        path: str = "",
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Make GET request."""
        return await self._request("GET", path, headers, params=params, timeout=timeout, **kwargs)

    async def post(
        self,
        path: str = "",
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Make POST request."""
        return await self._request("POST", path, headers, json=json, timeout=timeout, **kwargs)

    async def put(
        self,
        path: str = "",
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Make PUT request."""
        return await self._request("PUT", path, headers, json=json, timeout=timeout, **kwargs)

    async def patch(
        self,
        path: str = "",
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Make PATCH request."""
        return await self._request("PATCH", path, headers, json=json, timeout=timeout, **kwargs)

    async def delete(
        self,
        path: str = "",
        *,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Make DELETE request."""
        return await self._request("DELETE", path, headers, timeout=timeout, **kwargs)

    async def head(
        self,
        path: str = "",
        *,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Make HEAD request."""
        return await self._request("HEAD", path, headers, timeout=timeout, **kwargs)

    def get_stats(self) -> dict[str, Any]:
        """Get session statistics."""
        return self._session_handler.get_stats()

    async def __aenter__(self) -> "APIClient":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()


# Convenience factory functions
def create_client(
    endpoints: list[str],
    *,
    fingerprint: BrowserFingerprint = BrowserFingerprint.CHROME120,
    network_refresh_command: str | None = None,
    **kwargs: Any,
) -> APIClient:
    """
    Create an API client with common defaults.
    
    Args:
        endpoints: List of base endpoint URLs
        fingerprint: Browser TLS/JA3 fingerprint to emulate
        network_refresh_command: OS command to refresh network interface
        **kwargs: Additional APIClient parameters
    
    Returns:
        Configured APIClient instance
    """
    return APIClient(
        endpoints=endpoints,
        fingerprint=fingerprint,
        network_refresh_command=network_refresh_command,
        **kwargs,
    )
