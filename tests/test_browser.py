"""JS browser helper respects the allowlist and degrades gracefully."""

import pytest

from backend.app.browser import discover_via_browser, fetch_page_html
from backend.app.policy import BlockedDomainError


def test_browser_blocks_disallowed_domain():
    with pytest.raises(BlockedDomainError):
        fetch_page_html("https://example-evil-shop.com/deal")
    with pytest.raises(BlockedDomainError):
        discover_via_browser("https://example-evil-shop.com/list")


def test_browser_fallback_returns_list_without_crashing():
    # No browser installed in unit env: must return [] instead of raising.
    assert discover_via_browser("https://ostrovok.ru/hotel/turkey/side/") == []
