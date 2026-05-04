# path: omnisource/core/browser.py
from __future__ import annotations

import asyncio
from typing import Optional

from playwright.async_api import async_playwright

from omnisource.core.telemetry import logger


class BrowserNotAllowedException(Exception):
    pass


class BrowserManager:
    """Playwright-based browser. Stateless per request."""

    def __init__(self, timeout: int = 45000) -> None:
        self.timeout = timeout

    async def fetch_with_browser(self, url: str, wait_for: Optional[str] = None) -> str:
        """Fetch HTML using a headless browser.

        Args:
            url: Target URL
            wait_for: Optional CSS selector to wait for

        Returns:
            HTML content
        """
        logger.info("browser_fetch_start", url=url)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            context = await browser.new_context()
            page = await context.new_page()

            try:
                await page.goto(url, timeout=self.timeout)

                if wait_for:
                    await page.wait_for_selector(wait_for, timeout=self.timeout)

                content = await page.content()

                logger.info("browser_fetch_success", url=url)

                return content

            except Exception as e:
                logger.error("browser_fetch_failed", url=url, error=str(e))
                raise

            finally:
                await context.close()
                await browser.close()