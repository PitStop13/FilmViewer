"""Thread-safe in-memory DNS cache for Python's socket.getaddrinfo.

Docker Desktop for Windows / WSL2 routes container DNS via 127.0.0.11 / 192.168.65.7.
When multiple worker threads make concurrent DNS queries simultaneously (e.g. home shelves,
segment downloads), the virtual NAT resolver frequently drops UDP queries or throttles,
resulting in 5-8s latency spikes or [Errno -5] Temporary failure in name resolution.

Caching getaddrinfo results in memory for a short TTL (3-5 minutes) reduces external DNS
traffic by >99%, makes parallel HTTP requests instant, and prevents Docker DNS throttling.
"""

import logging
import socket
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 300.0  # 5 minutes
_dns_cache: dict[tuple, tuple[float, list]] = {}
_dns_lock = threading.Lock()
_real_getaddrinfo = socket.getaddrinfo
_is_enabled = False


def _cached_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    # Only cache string hostnames (not None, and not empty)
    if not isinstance(host, str) or not host:
        return _real_getaddrinfo(host, port, family, type, proto, flags)

    key = (host.lower(), port, family, type, proto, flags)
    now = time.time()

    with _dns_lock:
        entry = _dns_cache.get(key)
        if entry is not None:
            expires_at, res = entry
            if expires_at > now:
                return res
            _dns_cache.pop(key, None)

    # Perform the actual DNS lookup outside the lock so other threads aren't blocked
    res = _real_getaddrinfo(host, port, family, type, proto, flags)

    with _dns_lock:
        if len(_dns_cache) > 200:
            # Purge expired
            expired = [k for k, (exp, _) in _dns_cache.items() if exp < now]
            for k in expired:
                _dns_cache.pop(k, None)
            if len(_dns_cache) > 200:
                _dns_cache.clear()
        _dns_cache[key] = (now + _DEFAULT_TTL, res)

    return res


def enable_dns_cache(ttl: float = _DEFAULT_TTL) -> None:
    """Enable in-memory DNS caching."""
    global _is_enabled, _DEFAULT_TTL
    with _dns_lock:
        if not _is_enabled:
            _DEFAULT_TTL = ttl
            socket.getaddrinfo = _cached_getaddrinfo
            _is_enabled = True
            logger.info("In-memory DNS cache enabled (TTL: %.0fs)", _DEFAULT_TTL)


def disable_dns_cache() -> None:
    """Disable in-memory DNS caching and restore original getaddrinfo."""
    global _is_enabled
    with _dns_lock:
        if _is_enabled:
            socket.getaddrinfo = _real_getaddrinfo
            _is_enabled = False
            _dns_cache.clear()
            logger.info("In-memory DNS cache disabled")


def clear_dns_cache() -> None:
    """Clear all cached DNS entries (e.g. after a domain change)."""
    with _dns_lock:
        _dns_cache.clear()
        logger.debug("In-memory DNS cache cleared")
