"""
Web Panel Security — DDoS protection, rate limiting, IP banning, security headers.
"""

import time
import logging
from collections import defaultdict

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("web.security")

# ── In-memory stores ──────────────────────────────────────────────────────────
_request_counts: dict[str, list[float]] = defaultdict(list)
_banned_ips: dict[str, float] = {}  # ip -> ban_expiry_timestamp
_login_attempts: dict[str, list[float]] = defaultdict(list)

# ── Config ────────────────────────────────────────────────────────────────────
RATE_LIMIT_REQUESTS = 60        # requests per window
RATE_LIMIT_WINDOW   = 60        # seconds
BAN_THRESHOLD       = 300       # requests per window before ban
BAN_DURATION        = 3600      # 1 hour ban
LOGIN_RATE_LIMIT    = 10        # max login attempts per 10 minutes per IP


def _get_real_ip(request: Request) -> str:
    """Get real IP, respecting X-Forwarded-For if behind proxy."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class SecurityMiddleware(BaseHTTPMiddleware):
    """Combined DDoS protection, rate limiting, and security headers."""

    async def dispatch(self, request: Request, call_next):
        client_ip = _get_real_ip(request)

        # 1. Check if IP is banned
        if client_ip in _banned_ips:
            if time.time() < _banned_ips[client_ip]:
                logger.warning("Banned IP attempted access: %s", client_ip)
                return JSONResponse({"error": "Forbidden"}, status_code=403)
            else:
                del _banned_ips[client_ip]

        # 2. Rate limit check
        now = time.monotonic()
        bucket = _request_counts[client_ip]
        _request_counts[client_ip] = [t for t in bucket if now - t < RATE_LIMIT_WINDOW]
        _request_counts[client_ip].append(now)
        count = len(_request_counts[client_ip])

        if count >= BAN_THRESHOLD:
            _banned_ips[client_ip] = time.time() + BAN_DURATION
            logger.warning("DDoS detected - IP banned: %s (%d requests)", client_ip, count)
            return JSONResponse({"error": "Forbidden"}, status_code=403)

        if count >= RATE_LIMIT_REQUESTS:
            return JSONResponse(
                {"error": "Too many requests"},
                status_code=429,
                headers={"Retry-After": str(RATE_LIMIT_WINDOW)},
            )

        # 3. Process request
        response = await call_next(request)

        # 4. Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )

        return response


def check_login_rate_limit(ip: str) -> None:
    """Raise 429 if too many login attempts from this IP."""
    now = time.monotonic()
    attempts = _login_attempts[ip]
    _login_attempts[ip] = [t for t in attempts if now - t < 600]  # 10-min window
    if len(_login_attempts[ip]) >= LOGIN_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    _login_attempts[ip].append(now)
