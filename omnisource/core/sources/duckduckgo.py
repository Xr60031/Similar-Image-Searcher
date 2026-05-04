# path: omnisource/core/sources/duckduckgo.py
from __future__ import annotations

import time
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from omnisource.core.models import NormalizedResult
from omnisource.core.sources.base import SourceProvider
from omnisource.core.telemetry import logger


class DuckDuckGoSource(SourceProvider):
    source_id = "duckduckgo"

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
            "burst": 5,
        }

    def should_use_browser(self) -> bool:
        return False

    # -------------------------
    # INTERNAL
    # -------------------------

    def _extract_query(self, image_path: str) -> str:
        filename = image_path.split("/")[-1]
        name = filename.split(".")[0]

        name = re.sub(r"[^a-zA-Z0-9_\- ]", " ", name)
        name = name.replace("_", " ").replace("-", " ")
        name = re.sub(r"\s+", " ", name).strip()

        return name

    async def _get_vqd(self, client: httpx.AsyncClient, query: str) -> str:
        resp = await client.get(
            "https://duckduckgo.com/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
        )

        match = re.search(r"vqd='(\d+-\d+)'", resp.text)
        if not match:
            raise RuntimeError("Failed to extract vqd")

        return match.group(1)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    async def search_by_image(self, image_path: str) -> List[NormalizedResult]:
        start = time.time()

        results: List[NormalizedResult] = []

        query = self._extract_query(image_path)

        try:
            logger.info("duckduckgo_start", query=query)

            async with httpx.AsyncClient(timeout=15) as client:
                vqd = await self._get_vqd(client, query)

                resp = await client.get(
                    "https://duckduckgo.com/i.js",
                    params={
                        "l": "us-en",
                        "o": "json",
                        "q": query,
                        "vqd": vqd,
                        "f": ",,,",
                        "p": "1",
                    },
                    headers={"User-Agent": "Mozilla/5.0"},
                )

            data = resp.json()

            seen = set()

            for item in data.get("results", [])[:40]:
                url = item.get("image")
                title = item.get("title", "")

                if not url or url in seen:
                    continue

                seen.add(url)

                signals = ["ddg_image_result"]

                if query.lower() in title.lower():
                    signals.append("title_match")

                results.append(
                    NormalizedResult(
                        url=url,
                        title=title[:200],
                        source=self.source_id,
                        confidence_signals=signals,
                        raw_context={},
                        fetched_at=datetime.now(timezone.utc),
                    )
                )

            latency = (time.time() - start) * 1000

            logger.info(
                "duckduckgo_success",
                latency_ms=latency,
                count=len(results),
            )

            return results

        except Exception as e:
            latency = (time.time() - start) * 1000

            logger.warning(
                "duckduckgo_failed",
                error=str(e),
                latency_ms=latency,
            )

            return []