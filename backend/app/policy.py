"""Allowlist policy: the agent may fetch data only from allowed domains."""

from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import urlparse

import yaml

_POLICY_PATH = os.path.join(os.path.dirname(__file__), "..", "allowed_domains.yml")


class BlockedDomainError(ValueError):
    """Raised when the agent tries to leave the allowlist."""


@lru_cache(maxsize=1)
def allowed_domains() -> tuple[str, ...]:
    with open(_POLICY_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return tuple(d.lower() for d in data.get("allowed_domains", []))


def is_allowed(url: str) -> bool:
    """Return True if the URL host matches the allowlist (incl. subdomains)."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in allowed_domains())


def assert_allowed(url: str) -> str:
    """Return the URL if allowed, else raise BlockedDomainError (logged by caller)."""
    if not is_allowed(url):
        raise BlockedDomainError(f"domain not in allowlist: {url}")
    return url
