"""JS page rendering via headless browser (MVP-1.4).

Every URL goes through the allowlist first: pages outside the policy
are rejected before any browser starts.
"""

from __future__ import annotations

import re

from .policy import assert_allowed

HOTEL_PATH_RE = re.compile(r"/hotel/(turkey/[a-z_]+/mid\d+/[a-z0-9_]+/)")


def fetch_page_html(url: str, timeout_ms: int = 25000) -> dict:
    """Render a page with headless Chromium and return its HTML."""
    assert_allowed(url)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"url": url, "error": "browser unavailable"}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0")
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            html = page.content()
            final_url = page.url
            browser.close()
        return {"url": final_url, "html": html}
    except Exception as exc:  # noqa: BLE001 - browser errors become chat text
        return {"url": url, "error": str(exc)[:200]}


def discover_via_browser(listing_url: str, limit: int = 5) -> list[dict]:
    """Fallback hotel discovery for JS-only listings. Returns hotel stubs."""
    result = fetch_page_html(listing_url)
    html = result.get("html", "")
    if not html:
        return []
    paths = list(dict.fromkeys(HOTEL_PATH_RE.findall(html)))[:limit]
    hotels = []
    for path in paths:
        slug = path.strip("/").split("/")[-1]
        hotels.append(
            {
                "hotel": slug,
                "path": path,
                "name": slug.replace("_", " ").title(),
            }
        )
    return hotels
