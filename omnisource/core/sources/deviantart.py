from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Dict, Any
from urllib.parse import quote
import re

import httpx
from selectolax.parser import HTMLParser

from omnisource.core.models import NormalizedResult
from omnisource.core.sources.base import SourceProvider
from omnisource.core.telemetry import logger


class DeviantArtSource(SourceProvider):
    source_id = "deviantart"

    # 🔹 REQUIRED ABSTRACT IMPLEMENTATIONS

    @property
    def capabilities(self) -> Dict[str, Any]:
        return {
            "reverse_image": False,
            "text_search": True,
        }

    @property
    def rate_limit_profile(self) -> Dict[str, Any]:
        return {
            "requests_per_minute": 20,
            "burst": 5,
        }

    def should_use_browser(self) -> bool:
        return False

    BASE_URL = "https://www.deviantart.com/search"

    def _extract_query(self, image_path: str) -> str:
        """
        Intenta reconstruir un query útil desde la URL
        """
        filename = image_path.split("/")[-1]

        name = filename.split(".")[0]

        name = re.sub(r"[-_]?pre$", "", name)
        name = re.sub(r"[^a-zA-Z0-9_\- ]", " ", name)

        name = name.replace("_", " ").replace("-", " ")

        name = re.sub(r"\s+", " ", name).strip()

        return name

    async def search_by_image(self, image_path: str) -> List[NormalizedResult]:
        results: List[NormalizedResult] = []

        query_raw = self._extract_query(image_path)
        query = quote(query_raw)

        url = f"{self.BASE_URL}?q={query}"

        headers = {
            "User-Agent": "Mozilla/5.0 (OmniSourceBot)",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            logger.info("deviantart_start", query=query_raw)

            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)

            if response.status_code != 200:
                logger.warning("deviantart_bad_status", status=response.status_code)
                return []

            tree = HTMLParser(response.text)

            nodes = tree.css("a[href*='/art/']")

            seen = set()

            for node in nodes[:50]:
                href = node.attributes.get("href")
                if not href or href in seen:
                    continue

                seen.add(href)

                title = node.text(strip=True) or ""

                signals = ["deviantart_match"]

                lowered_title = title.lower()
                lowered_query = query_raw.lower()

                if lowered_query and lowered_query in lowered_title:
                    signals.append("title_exact_match")

                if not title:
                    signals.append("low_metadata")

                results.append(
                    NormalizedResult(
                        url=href,
                        title=title[:200],
                        source=self.source_id,
                        confidence_signals=signals,
                        raw_context={
                            "query": query_raw,
                        },
                        fetched_at=datetime.now(timezone.utc),
                    )
                )

            logger.info("deviantart_success", count=len(results))
            return results

        except Exception as e:
            logger.error("deviantart_error", error=str(e))
            return []