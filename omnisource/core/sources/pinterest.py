from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Dict, Any
from urllib.parse import quote

from playwright.async_api import async_playwright

from omnisource.core.models import NormalizedResult
from omnisource.core.sources.base import SourceProvider
from omnisource.core.telemetry import logger


class PinterestSource(SourceProvider):
    source_id = "pinterest"

    @property
    def capabilities(self) -> Dict[str, Any]:
        return {
            "reverse_image": False,
            "text_search": True,
        }

    @property
    def rate_limit_profile(self) -> Dict[str, Any]:
        return {
            "requests_per_minute": 10,
            "burst": 3,
        }

    def should_use_browser(self) -> bool:
        return True

    BASE_URL = "https://www.pinterest.com/search/pins/"

    async def search_by_image(self, image_path: str) -> List[NormalizedResult]:
        results: List[NormalizedResult] = []

        filename = image_path.split("/")[-1]
        keyword = filename.split(".")[0].lower()

        if len(keyword) < 3:
            return []

        keyword = keyword.replace("_", " ").replace("-", " ")
        url = f"{self.BASE_URL}?q={quote(keyword)}"

        try:
            logger.info("pinterest_start", keyword=keyword)

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                await page.goto(url, timeout=60000)

                await page.wait_for_selector("a[href*='/pin/']", timeout=15000)

                nodes = await page.query_selector_all("a[href*='/pin/']")

                seen = set()

                for node in nodes[:40]:
                    href = await node.get_attribute("href")
                    if not href:
                        continue

                    full_url = (
                        href if href.startswith("http")
                        else f"https://www.pinterest.com{href}"
                    )

                    if full_url in seen:
                        continue

                    seen.add(full_url)

                    img_el = await node.query_selector("img")
                    image_url = None

                    if img_el:
                        image_url = await img_el.get_attribute("src")

                    if image_url and "236x" in image_url:
                        image_url = image_url.replace("236x", "originals")

                    results.append(
                        NormalizedResult(
                            url=full_url,
                            image_url=image_url,
                            title=keyword,
                            source=self.source_id,
                            confidence_signals=["pinterest_match"],
                            raw_context={},
                            fetched_at=datetime.now(timezone.utc),
                        )
                    )

                await context.close()
                await browser.close()

            logger.info("pinterest_success", count=len(results))
            return results

        except Exception as e:
            logger.error("pinterest_error", error=str(e))
            return []