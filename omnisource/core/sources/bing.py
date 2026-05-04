from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Dict, Any

import httpx
from selectolax.parser import HTMLParser

from omnisource.core.models import NormalizedResult
from omnisource.core.sources.base import SourceProvider
from omnisource.core.telemetry import logger


class BingSource(SourceProvider):
    source_id = "bing"

    # -------------------------
    # REQUIRED ABSTRACT PROPERTIES
    # -------------------------
    @property
    def capabilities(self) -> Dict[str, Any]:
        return {
            "reverse_image": True,
            "text_search": False,
        }

    @property
    def rate_limit_profile(self) -> Dict[str, Any]:
        return {
            "requests_per_minute": 30,
            "burst": 5,
        }

    def should_use_browser(self) -> bool:
        return False

    # -------------------------
    # MAIN LOGIC
    # -------------------------
    BASE_URL = "https://www.bing.com/images/searchbyimage"

    async def search_by_image(self, image_path: str) -> List[NormalizedResult]:
        results: List[NormalizedResult] = []

        params = {
            "cbir": "sbi",
            "imgurl": image_path,
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (OmniSourceBot)",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            logger.info("bing_start", image=image_path)

            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                response = await client.get(self.BASE_URL, params=params, headers=headers)

            if response.status_code != 200:
                logger.warning("bing_bad_status", status=response.status_code)
                return []

            tree = HTMLParser(response.text)
            nodes = tree.css("a.iusc")

            seen_images = set()

            import json

            for node in nodes[:50]:
                raw = node.attributes.get("m")
                if not raw:
                    continue

                try:
                    data = json.loads(raw)
                except Exception:
                    continue

                page_url = data.get("purl")
                image_url = data.get("murl")

                if not image_url or image_url in seen_images:
                    continue

                seen_images.add(image_url)

                results.append(
                    NormalizedResult(
                        url=page_url or image_url,
                        image_url=image_url,
                        title=data.get("t") or "",
                        source=self.source_id,
                        confidence_signals=["bing_visual_match"],
                        raw_context=data,
                        fetched_at=datetime.now(timezone.utc),
                    )
                )

            logger.info("bing_success", count=len(results))
            return results

        except Exception as e:
            logger.error("bing_error", error=str(e))
            return []