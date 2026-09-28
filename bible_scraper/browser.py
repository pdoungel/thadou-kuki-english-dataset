"""Playwright browser session management: headed/headless, retries, polite delays.

The browser behaves like a normal visitor. It does not bypass access controls,
CAPTCHAs, or challenges — a page that cannot be read normally is recorded as an
acquisition failure.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Optional

from playwright.sync_api import Page, sync_playwright

log = logging.getLogger("bible_scraper.browser")

# Resource types that never affect extracted text; blocking them only makes
# page loads faster and avoids storing unnecessary browser assets.
BLOCKED_RESOURCE_TYPES = ("image", "media", "font")


class BrowserError(RuntimeError):
    """Raised when navigation/extraction cannot complete after all retries."""


class BrowserSession:
    """A single browser context with one reusable page.

    Parameters
    ----------
    headed:
        True (default) shows the browser window — preferred for development.
        False runs headless for production runs.
    min_delay / max_delay:
        Polite random pause in seconds applied between chapter requests.
    max_retries:
        Number of retries after the initial attempt (exponential backoff).
    timeout_ms:
        Per-navigation timeout in milliseconds.
    block_media:
        Abort image/media/font requests (text extraction does not need them).
    """

    def __init__(
        self,
        headed: bool = True,
        min_delay: float = 0.5,
        max_delay: float = 2.0,
        max_retries: int = 3,
        timeout_ms: int = 45_000,
        selector_timeout_ms: int = 12_000,
        block_media: bool = True,
    ) -> None:
        if max_delay < min_delay or min_delay < 0:
            raise ValueError("require 0 <= min_delay <= max_delay")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self.headed = headed
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.timeout_ms = timeout_ms
        self.selector_timeout_ms = selector_timeout_ms
        self.block_media = block_media
        self._pw = None
        self._browser = None
        self._context = None
        self.page: Optional[Page] = None

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> "BrowserSession":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=not self.headed)
        self._context = self._browser.new_context(
            viewport={"width": 1440, "height": 960},
            locale="en-US",
        )
        if self.block_media:
            self._context.route("**/*", self._route_handler)
        self.page = self._context.new_page()
        self.page.set_default_timeout(self.timeout_ms)
        log.info(
            "browser started headed=%s min_delay=%.2f max_delay=%.2f max_retries=%d",
            self.headed, self.min_delay, self.max_delay, self.max_retries,
        )
        return self

    @staticmethod
    def _route_handler(route) -> None:
        try:
            if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
                route.abort()
            else:
                route.continue_()
        except Exception:  # pragma: no cover - route race on navigation
            pass

    def stop(self) -> None:
        for closer in (self._context, self._browser):
            try:
                if closer is not None:
                    closer.close()
            except Exception:
                pass
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._pw = self._browser = self._context = self.page = None
        log.info("browser stopped")

    def __enter__(self) -> "BrowserSession":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    # -- helpers -----------------------------------------------------------
    def _ensure_page(self) -> Page:
        if self.page is None or self.page.is_closed():
            self.page = self._context.new_page()
            self.page.set_default_timeout(self.timeout_ms)
            log.warning("page was closed; recreated a new page")
        return self.page

    def pause(self) -> None:
        """Polite delay between chapter requests."""
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    def evaluate(self, expression, arg=None):
        """Evaluate a JS function in the current page (structure capture)."""
        page = self._ensure_page()
        return page.evaluate(expression, arg)

    def goto(self, url: str, selector: Optional[str] = None,
             selector_timeout_ms: Optional[int] = None) -> int:
        """Navigate to *url*, optionally waiting for *selector*.

        Retries with exponential backoff (1s, 2s, 4s ... plus jitter).
        Returns the number of attempts used. Raises BrowserError after the
        initial attempt plus ``max_retries`` retries have failed.
        """
        if selector_timeout_ms is None:
            selector_timeout_ms = self.selector_timeout_ms
        last_err: Optional[BaseException] = None
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            try:
                page = self._ensure_page()
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                if selector:
                    page.wait_for_selector(selector, timeout=selector_timeout_ms)
                return attempt + 1
            except Exception as exc:  # noqa: BLE001 - any failure is retried
                last_err = exc
                log.warning(
                    "navigation failed attempt=%d/%d url=%s error=%s",
                    attempt + 1, attempts, url, exc,
                )
                if attempt < attempts - 1:
                    time.sleep((2 ** attempt) + random.random())
        raise BrowserError(f"navigation failed after {attempts} attempts: {url}: {last_err}")
