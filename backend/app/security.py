"""Authentication, HTTPS transport policy, and owner isolation helpers for MyVoice AI.

Ownership & multi-user note:
- Distinct tokens configured via MYVOICE_OWNER_TOKENS (`alice:tokA,bob:tokB`) isolate each
  user into a separate server-derived directory (`owners/alice`, `owners/bob`).
- A single MYVOICE_API_TOKEN binds all holders of that shared token to one `owner_<hash>`
  namespace; multi-user deployments MUST use distinct credentials in MYVOICE_OWNER_TOKENS.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import secrets
from typing import Mapping

from app.config import Settings

_SAFE_OWNER_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_LOCAL_DEV_HOSTS = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "::1",
        "10.0.2.2",
        "testclient",
        "testserver",
    }
)


class SecurityPolicyError(PermissionError):
    """Raised when transport security or API authentication checks fail."""

    def __init__(self, message: str, *, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


def sanitize_owner_id(raw_owner: str) -> str:
    cleaned = _SAFE_OWNER_RE.sub("_", raw_owner.strip()).strip("_")[:48]
    if not cleaned:
        raise SecurityPolicyError("Invalid authenticated owner identifier.", status_code=403)
    return cleaned


def parse_owner_tokens(raw_mapping: str | None) -> dict[str, str]:
    """Parse 'ownerA:tokenA,ownerB:tokenB' into {owner_id: token}."""
    if not raw_mapping or not raw_mapping.strip():
        return {}
    mapping: dict[str, str] = {}
    for entry in raw_mapping.split(","):
        item = entry.strip()
        if not item or ":" not in item:
            continue
        owner_raw, token = item.split(":", 1)
        token_clean = token.strip()
        if not token_clean:
            continue
        owner_clean = sanitize_owner_id(owner_raw)
        mapping[owner_clean] = token_clean
    return mapping


def has_configured_auth(settings: Settings) -> bool:
    """Return True if at least one non-empty API or per-owner credential is configured."""
    return bool(parse_owner_tokens(settings.owner_tokens_raw) or settings.api_auth_token)


def _extract_bearer_or_key(authorization: str | None, x_api_key: str | None) -> str | None:
    if authorization and authorization.strip():
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    return None


def authenticate_request_token(
    authorization: str | None,
    x_api_key: str | None,
    *,
    settings: Settings,
) -> str:
    """Validate API credentials in constant time and derive an isolated server-side owner_id."""
    owner_tokens: Mapping[str, str] = parse_owner_tokens(settings.owner_tokens_raw)
    single_token = settings.api_auth_token

    if not owner_tokens and not single_token:
        raise SecurityPolicyError(
            "Backend authentication is not configured. Set MYVOICE_API_TOKEN or MYVOICE_OWNER_TOKENS.",
            status_code=503,
        )

    presented = _extract_bearer_or_key(authorization, x_api_key)
    if not presented:
        raise SecurityPolicyError(
            "Authentication required. Provide Authorization: Bearer <token> or X-API-Key.",
            status_code=401,
        )

    matched_owner: str | None = None
    for owner_id, expected_token in owner_tokens.items():
        if secrets.compare_digest(presented, expected_token):
            matched_owner = owner_id

    if matched_owner is not None:
        return matched_owner

    if single_token and secrets.compare_digest(presented, single_token):
        digest = hashlib.sha256(presented.encode("utf-8")).hexdigest()[:16]
        return f"owner_{digest}"

    raise SecurityPolicyError("Invalid API authentication token.", status_code=401)


def verify_gradio_credentials(username: str, password: str, *, settings: Settings) -> bool:
    """Verify Gradio basic-login credentials against MYVOICE_OWNER_TOKENS / MYVOICE_API_TOKEN."""
    owner_tokens = parse_owner_tokens(settings.owner_tokens_raw)
    if owner_tokens:
        expected = owner_tokens.get(username.strip())
        if expected is not None and secrets.compare_digest(password, expected):
            return True
    if settings.api_auth_token and secrets.compare_digest(password, settings.api_auth_token):
        return True
    return False


def is_trusted_proxy(client_host: str | None, trusted_proxies_raw: str) -> bool:
    """Return True only when the TCP peer IP matches an explicit TRUSTED_PROXY_IPS entry."""
    if not client_host or not trusted_proxies_raw.strip():
        return False
    host_str = client_host.strip().strip("[]")
    try:
        peer_ip = ipaddress.ip_address(host_str)
    except ValueError:
        return False

    for entry in trusted_proxies_raw.split(","):
        token = entry.strip()
        if not token:
            continue
        try:
            if "/" in token:
                if peer_ip in ipaddress.ip_network(token, strict=False):
                    return True
            else:
                if peer_ip == ipaddress.ip_address(token):
                    return True
        except ValueError:
            continue
    return False


def enforce_https_transport(
    *,
    scheme: str,
    forwarded_proto: str | None,
    host_header: str | None,
    url_hostname: str | None,
    client_host: str | None = None,
    settings: Settings,
) -> None:
    """Require HTTPS for remote requests; only trust X-Forwarded-Proto from trusted proxies."""
    trusted = is_trusted_proxy(client_host, settings.trusted_proxy_ips_raw)
    effective_proto = (
        forwarded_proto.split(",")[0].strip().lower()
        if trusted and forwarded_proto
        else scheme.strip().lower()
    )
    if effective_proto == "https":
        return

    raw_host = (host_header or url_hostname or "").strip()
    if raw_host.startswith("["):
        hostname = raw_host[1:].split("]", 1)[0].lower()
    else:
        hostname = raw_host.split(":", 1)[0].lower()

    if settings.allow_local_http_dev and hostname in _LOCAL_DEV_HOSTS:
        return

    raise SecurityPolicyError(
        "HTTPS is required for backend communication. Plain HTTP is allowed only for explicit "
        "local development hosts (localhost, 127.0.0.1, ::1, 10.0.2.2) with ALLOW_LOCAL_HTTP_DEV=true.",
        status_code=403,
    )
