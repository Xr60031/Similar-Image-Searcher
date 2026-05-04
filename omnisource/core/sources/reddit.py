from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Dict, Any

import httpx

from omnisource.core.models import NormalizedResult
from omnisource.core.sources.base import SourceProvider
from omnisource.core.telemetry import logger


class RedditSource(SourceProvider):
    source_id = "reddit"

    @property
    def capabilities(self) -> Dict[str, Any]:
        return {
            "reverse_image": False,
            "text_search": True,
        }

    @property
    def rate_limit_profile(self) -> Dict[str, Any]:
        return {
            "requests_per_minute": 30,
            "burst": 10,
        }

    def should_use_browser(self) -> bool:
        return False

    BASE_URL = "https://www.reddit.com/search.json"

    async def search_by_image(self, image_path: str) -> List[NormalizedResult]:
        results: List[NormalizedResult] = []

        headers = {
            "User-Agent": "Mozilla/5.0 (OmniSourceBot)"
        }

        params = {
            "q": image_path,
            "limit": 25,
            "sort": "relevance",
        }

        try:
            logger.info("reddit_start", query=image_path)

            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self.BASE_URL, params=params, headers=headers)

            if response.status_code != 200:
                logger.warning("reddit_bad_status", status=response.status_code)
                return []

            data = response.json()
            posts = data.get("data", {}).get("children", [])

            for post in posts:
                pdata = post.get("data", {})

                url = pdata.get("url")
                title = pdata.get("title", "")
                subreddit = pdata.get("subreddit", "")

                if not url:
                    continue

                image_url = None

                if url and any(url.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    image_url = url

                if not image_url:
                    preview = pdata.get("preview", {})
                    images = preview.get("images", [])
                    if images:
                        src = images[0].get("source", {})
                        image_url = src.get("url")

                if image_url:
                    image_url = image_url.replace("&amp;", "&")

                results.append(
                    NormalizedResult(
                        url=url,
                        image_url=image_url,
                        title=title[:200],
                        source=self.source_id,
                        confidence_signals=[
                            "reddit_match",
                            f"subreddit:{subreddit}",
                        ],
                        raw_context={
                            "score": pdata.get("score"),
                        },
                        fetched_at=datetime.now(timezone.utc),
                    )
                )

            logger.info("reddit_success", count=len(results))
            return results

        except Exception as e:
            logger.error("reddit_error", error=str(e))
            return []