"""
Delta Agent - Async REST API Client for Embedded/Mobile Linux

A robust Python client for REST API consumption optimized for
embedded/mobile Linux environments (Termux on ARM architecture).

Features:
- TLS/JA3 fingerprint emulation using curl_cffi
- Async endpoint rotation with weighted failover
- Automatic retry with exponential backoff
- Circuit breaker pattern for fault tolerance
- Hardware integration hooks for OS commands
- ARM/Termux optimized for low memory footprint

Example:
    from delta_agent import APIClient, BrowserFingerprint
    
    async with APIClient(
        endpoints=["https://api.example.com", "https://backup.example.com"],
        fingerprint=BrowserFingerprint.CHROME120,
    ) as client:
        response = await client.get("/users/123")
        data = response.json()
"""

__version__ = "0.1.0"

from .session import (
    AsyncSessionHandler,
    BrowserFingerprint,
    ConnectionState,
    DefaultNetworkRefreshCallback,
    Endpoint,
    HardwareIntegrationHook,
    NetworkRefreshCallback,
    RetryConfig,
    SessionConfig,
    create_session_handler,
)
from .client import (
    APIClient,
    APIClientConfig,
    APIClientError,
    create_client,
)

__all__ = [
    # Session layer
    "AsyncSessionHandler",
    "BrowserFingerprint",
    "ConnectionState",
    "Endpoint",
    "HardwareIntegrationHook",
    "NetworkRefreshCallback",
    "DefaultNetworkRefreshCallback",
    "RetryConfig",
    "SessionConfig",
    "create_session_handler",
    # Client layer
    "APIClient",
    "APIClientConfig",
    "APIClientError",
    "create_client",
    # Version
    "__version__",
]