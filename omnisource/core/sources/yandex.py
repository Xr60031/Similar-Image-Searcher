from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Dict, Any

from playwright.async_api import async_playwright

from omnisource.core.models import NormalizedResult
from omnisource.core.sources.base import SourceProvider
from omnisource.core.telemetry import logger


class YandexSource(SourceProvider):
    source_id = "yandex"

    @property
    def capabilities(self) -> Dict[str, Any]:
        return {
            "reverse_image": True,
            "text_search": False,
        }

    @property
    def rate_limit_profile(self) -> Dict[str, Any]:
        return {
            "requests_per_minute": 10,
            "burst": 2,
        }

    def should_use_browser(self) -> bool:
        return True

    async def search_by_image(self, image_path: str) -> List[NormalizedResult]:
        results: List[NormalizedResult] = []

        try:
            logger.info("yandex_start", image=image_path)

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                await page.goto("https://yandex.com/images/", timeout=60000)

                await page.click('button[aria-label="Search by image"]', timeout=10000)

                await page.fill('input[name="url"]', image_path)
                await page.keyboard.press("Enter")

                await page.wait_for_selector("a.serp-item__link", timeout=15000)

                nodes = await page.query_selector_all("a.serp-item__link")

                seen = set()

                for node in nodes[:30]:
                    href = await node.get_attribute("href")

                    if not href or href in seen:
                        continue

                    seen.add(href)

                    image_url = None

                    img = await node.query_selector("img")
                    if img:
                        image_url = await img.get_attribute("src")

                    if not image_url:
                        data_bem = await node.get_attribute("data-bem")
                        if data_bem and "img_href" in data_bem:
                            image_url = data_bem

                    if image_url:
                        image_url = image_url.replace("&amp;", "&")

                    results.append(
                        NormalizedResult(
                            url=href,
                            image_url=image_url,
                            title="",
                            source=self.source_id,
                            confidence_signals=["yandex_match"],
                            raw_context={},
                            fetched_at=datetime.now(timezone.utc),
                        )
                    )

                await context.close()
                await browser.close()

            logger.info("yandex_success", count=len(results))
            return results

        except Exception as e:
            logger.error("yandex_error", error=str(e))
            return []