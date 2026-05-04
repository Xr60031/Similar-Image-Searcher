from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import aiosqlite

from omnisource.core.models import (
    NormalizedResult,
    SearchResult,
    SourceStats,
)
from omnisource.core.sources import discover_sources
from omnisource.core.cache import ResultCache, PIPELINE_VERSION
from omnisource.core.telemetry import TelemetryCollector, logger
from omnisource.pipeline.cleaner import deduplicate
from omnisource.pipeline.ranker import Ranker

from omnisource.core.utils.image_resolver import resolve_image_url
from omnisource.core.utils.image_hash import compute_image_hash

MIN_SOURCE_SUCCESS_RATE = 0.40
DEFAULT_TIMEOUT = 30


class SearchOrchestrator:
    def __init__(self, db_path: str = "omnisource_stats.db") -> None:
        self.sources = discover_sources()
        self.cache = ResultCache()
        self.telemetry = TelemetryCollector()
        self.ranker = Ranker()
        self.db_path = db_path

    # -------------------------
    # DB
    # -------------------------
    async def _init_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS source_stats (
                source_id TEXT PRIMARY KEY,
                success_rate REAL,
                failure_count INTEGER,
                avg_latency_ms REAL,
                last_used_at INTEGER
            )
            """)
            await db.commit()

    async def _load_stats(self) -> Dict[str, SourceStats]:
        await self._init_db()

        stats: Dict[str, SourceStats] = {}

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM source_stats")
            rows = await cursor.fetchall()

            for row in rows:
                source_id, success_rate, failure_count, avg_latency, last_used = row
                stats[source_id] = SourceStats(
                    success_rate=success_rate,
                    failure_count=failure_count,
                    avg_latency_ms=avg_latency,
                    last_used_at=datetime.fromtimestamp(last_used, tz=timezone.utc)
                    if last_used else None,
                )

        return stats

    async def _update_stats(self) -> None:
        stats = self.telemetry.get_source_stats()

        async with aiosqlite.connect(self.db_path) as db:
            for source_id, data in stats.items():
                await db.execute("""
                INSERT INTO source_stats (source_id, success_rate, failure_count, avg_latency_ms, last_used_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    success_rate=excluded.success_rate,
                    failure_count=excluded.failure_count,
                    avg_latency_ms=excluded.avg_latency_ms,
                    last_used_at=excluded.last_used_at
                """, (
                    source_id,
                    data["success_rate"],
                    data["failure_count"],
                    data["avg_latency_ms"],
                    int(time.time()),
                ))
            await db.commit()

    # -------------------------
    # UTILS
    # -------------------------
    def _hash_image(self, image_path: str) -> str:
        return hashlib.sha256(image_path.encode()).hexdigest()

    def _order_sources(self, stats: Dict[str, SourceStats]) -> List[str]:
        def key(sid: str):
            stat = stats.get(sid)
            if not stat:
                return (0, float("inf"))
            return (-stat.success_rate, stat.avg_latency_ms)

        return sorted(self.sources.keys(), key=key)

    # -------------------------
    # SOURCE EXECUTION
    # -------------------------
    async def _run_source(self, source_id: str, image_path: str):
        source = self.sources[source_id]

        start = time.time()
        try:
            results = await asyncio.wait_for(
                source.search_by_image(image_path),
                timeout=DEFAULT_TIMEOUT
            )

            latency = (time.time() - start) * 1000
            self.telemetry.record_source_attempt(source_id, True, latency)

            return source_id, results

        except Exception as e:
            latency = (time.time() - start) * 1000
            logger.warning("source_execution_failed", source=source_id, error=str(e))
            self.telemetry.record_source_attempt(source_id, False, latency)
            return source_id, []

    # -------------------------
    # MAIN SEARCH
    # -------------------------
    async def search(
        self,
        image_path: str,
        sources: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> SearchResult:

        await self.cache.init_db()

        image_path = await resolve_image_url(image_path)
        cache_key = image_path

        original_hash = await compute_image_hash(image_path)

        # ---- CACHE
        if use_cache:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info("cache_hit", image=image_path)
                return cached

        stats = await self._load_stats()

        selected_sources = sources or list(self.sources.keys())
        ordered_sources = self._order_sources(stats)
        selected_sources = [s for s in ordered_sources if s in selected_sources]

        tasks = [self._run_source(sid, image_path) for sid in selected_sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: List[NormalizedResult] = []
        succeeded: List[str] = []

        for res in results:
            if isinstance(res, Exception):
                continue
            sid, data = res
            if data:
                succeeded.append(sid)
                all_results.extend(data)

        success_rate = len(succeeded) / len(selected_sources) if selected_sources else 0

        if success_rate < MIN_SOURCE_SUCCESS_RATE:
            logger.warning("source_degradation", success_rate=success_rate)

        cleaned = deduplicate(all_results)[:25]

        # -------------------------
        # VISUAL FILTER (NO MUTATION)
        # -------------------------
        visual_matches: List[NormalizedResult] = []
        fallback: List[NormalizedResult] = []

        for r in cleaned:
            try:
                if not getattr(r, "image_url", None):
                    fallback.append(r)
                    continue

                result_hash = await compute_image_hash(r.image_url)
                distance = original_hash - result_hash

                if distance < 6:
                    visual_matches.append(r)
                else:
                    fallback.append(r)

            except Exception:
                fallback.append(r)

        final_results = visual_matches if visual_matches else fallback

        # -------------------------
        # RANKING (FIX SAFE)
        # -------------------------
        ranked = self.ranker.rank(
            final_results,
            total_sources=len(selected_sources)
        )

        result = SearchResult(
            query_image_hash=self._hash_image(image_path),
            results=ranked,
            sources_attempted=selected_sources,
            sources_succeeded=succeeded,
            pipeline_version=PIPELINE_VERSION,
            generated_at=datetime.now(timezone.utc),
        )

        if use_cache:
            await self.cache.set(cache_key, result)

        await self._update_stats()

        return result

    async def get_source_stats(self) -> Dict[str, SourceStats]:
        return await self._load_stats()