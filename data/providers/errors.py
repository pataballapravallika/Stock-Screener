"""Custom exceptions for NSE data access layer."""


class NSEAccessDenied(Exception):
    """Raised when NSE returns HTTP 403 (Akamai access denied).

    This is a permanent block — the request should NOT be retried
    aggressively, and NO third-party fallback (Yahoo, Trendlyne, etc.)
    should ever substitute for official NSE filing data.
    """


class NSETimeout(Exception):
    """Raised when an NSE request times out (transient network issue)."""


class NSERequestError(Exception):
    """Raised when NSE returns an unexpected HTTP status (5xx, etc.)."""
