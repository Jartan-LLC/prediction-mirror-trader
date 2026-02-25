from __future__ import annotations


class PlatformError(Exception):
    """Base for all platform adapter errors."""


class TransientError(PlatformError):
    """Retryable: network timeout, 429 rate limit, 5xx server error."""


class FatalError(PlatformError):
    """Not retryable: invalid order, insufficient funds, auth failure, 4xx."""
