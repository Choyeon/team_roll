"""Password hashing, opaque tokens, client IP resolution and rate limiting."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import secrets
import threading
import time
from collections import deque
from collections.abc import Iterable

from fastapi import Request

_PASSWORD_ALGORITHM = "pbkdf2_sha256"
# Deliberately modest: admins log in rarely, and this keeps login under ~100ms on weak hardware.
_PASSWORD_ITERATIONS = 210_000
_PRIVATE_PREFIXES = ("10.", "127.", "169.254.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str, *, iterations: int = _PASSWORD_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_PASSWORD_ALGORITHM}${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, digest = encoded.split("$", 3)
    except ValueError:
        return False
    if algorithm != _PASSWORD_ALGORITHM:
        return False
    try:
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), _unb64(salt), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(_b64(candidate), digest)


def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def generate_activity_id() -> str:
    return secrets.token_hex(16)


def is_private_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_private
    except ValueError:
        return value.startswith(_PRIVATE_PREFIXES)


def client_ip(request: Request | None, *, trust_proxy_headers: bool = False) -> str:
    """Best-effort client address.

    ``X-Forwarded-For`` is only trusted behind a known-good proxy; otherwise the
    socket peer is authoritative and the header is attacker controlled.
    """
    if request is None:
        return "unknown"

    direct = request.client.host if request.client else None

    if trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            candidates = [item.strip() for item in forwarded.split(",") if item.strip()]
            for candidate in candidates:
                if not is_private_ip(candidate):
                    return candidate
            if candidates:
                return candidates[0]

    return direct or "unknown"


def client_user_agent(request: Request | None) -> str:
    """Collapsible whitespace, cut to the storage width — it is display data, not a key."""
    if request is None:
        return ""
    return " ".join((request.headers.get("user-agent") or "").split())[:200]


def client_ip_from_headers(headers: Iterable[tuple[bytes, bytes]], *, trust_proxy_headers: bool, fallback: str) -> str:
    """WebSocket variant: ASGI headers are byte pairs and ``client`` may be the proxy."""
    if not trust_proxy_headers:
        return fallback
    for key, value in headers:
        if key == b"x-forwarded-for":
            candidates = [item.strip() for item in value.decode("latin-1").split(",") if item.strip()]
            for candidate in candidates:
                if not is_private_ip(candidate):
                    return candidate
            return candidates[0] if candidates else fallback
    return fallback


class SlidingWindowLimiter:
    """In-process rate limiter; per-instance storage is enough for a single-node tool."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Return ``(allowed, retry_after_seconds)``."""
        now = time.monotonic()
        with self._lock:
            bucket = self._hits.get(key)
            if bucket is None:
                bucket = deque()
                self._hits[key] = bucket
            while bucket and now - bucket[0] > window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])) + 1)
                return False, retry_after
            bucket.append(now)
            if len(self._hits) > 4096:
                self._purge_locked(now, window_seconds)
            return True, 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def _purge_locked(self, now: float, window_seconds: int) -> None:
        stale = [k for k, v in self._hits.items() if not v or now - v[-1] > window_seconds]
        for key in stale:
            self._hits.pop(key, None)


login_limiter = SlidingWindowLimiter()
roll_limiter = SlidingWindowLimiter()
