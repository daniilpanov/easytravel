"""Allowlist blocks everything outside the policy file."""

import pytest

from backend.app.policy import BlockedDomainError, assert_allowed, is_allowed


def test_allows_listed_hotel_source():
    assert is_allowed("https://ostrovok.ru/hotel/turkey/side/")


def test_allows_subdomain():
    assert is_allowed("https://www.tophotels.ru/hotel/al123")


def test_blocks_random_site():
    assert not is_allowed("https://example-evil-shop.com/deal")
    with pytest.raises(BlockedDomainError):
        assert_allowed("https://example-evil-shop.com/deal")


def test_blocks_lookalike_domain():
    assert not is_allowed("https://ostrovok.ru.evil.com/hotel/")
