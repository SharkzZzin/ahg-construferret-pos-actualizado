from __future__ import annotations

from urllib.parse import urlparse


SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "script-src 'self' https://cdn.jsdelivr.net https://www.paypal.com https://www.paypalobjects.com; connect-src 'self' https:; "
        "frame-src https://www.paypal.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    ),
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def request_is_same_origin(headers) -> bool:
    """Validate browser writes without requiring a JavaScript-readable CSRF token."""
    source = headers.get("Origin") or headers.get("Referer")
    if not source:
        # Non-browser clients do not automatically attach cookies cross-origin.
        return not headers.get("Sec-Fetch-Site") or headers.get("Sec-Fetch-Site") in {"same-origin", "none"}
    parsed = urlparse(source)
    forwarded_host = (headers.get("X-Forwarded-Host") or headers.get("Host") or "").split(",", 1)[0].strip()
    return bool(parsed.netloc and parsed.netloc.lower() == forwarded_host.lower())


def client_address(headers, fallback: str = "") -> str:
    forwarded = headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    return forwarded or fallback or "unknown"
