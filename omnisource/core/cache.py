from __future__ import annotations

import json
import time
import hashlib
from typing import Optional, List

import aiosqlite

from omnisource.core.models import SearchResult, NormalizedResult


DEFAULT_TTL = 86400  # 24h
PIPELINE_VERSION = "1.0"


class ResultCache:
    """SQLite cache with TTL + validation guardrails (FIXED)."""

    def __init__(self, db_path: str = "omnisource_cache.db") -> None:
        self.db_path = db_path

    async def _connect(self):
        return await aiosqlite.connect(self.db_path)

    async def init_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
            CREATE TABLE IF NOT EXISTS cache_entries (
                image_hash TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                pipeline_version TEXT NOT NULL,
                sources_version TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS source_contributions (
                image_hash TEXT NOT NULL,
                source_id TEXT NOT NULL,
                result_json TEXT NOT NULL,
                fetched_at INTEGER NOT NULL,
                PRIMARY KEY (image_hash, source_id)
            );
            """)
            await db.commit()

    def _hash_image(self, image_path: str) -> str:
        return hashlib.sha256(image_path.encode()).hexdigest()

    # -------------------------
    # SAFE DESERIALIZATION
    # -------------------------
    def _deserialize_search_result(self, data: dict) -> SearchResult:
        """
        FIX:
        Ensures malformed / empty cache does NOT break pipeline.
        """

        # 🔴 HARD GUARD: empty results = invalid cache
        if not data.get("results"):
            return None

        try:
            return SearchResult(**data)
        except Exception:
            return None

    # -------------------------
    # GET CACHE
    # -------------------------
    async def get(self, image_path: str) -> Optional[SearchResult]:
        image_hash = self._hash_image(image_path)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT result_json, pipeline_version, expires_at
                FROM cache_entries
                WHERE image_hash=?
                """,
                (image_hash,)
            )

            row = await cursor.fetchone()

            if not row:
                return None

            result_json, pipeline_version, expires_at = row

            # 🔴 VERSION CHECK
            if pipeline_version != PIPELINE_VERSION:
                return None

            # 🔴 TTL CHECK
            if time.time() > expires_at:
                return None

            # 🔴 SAFE PARSE
            try:
                data = json.loads(result_json)
            except Exception:
                return None

            result = self._deserialize_search_result(data)

            # 🔴 CRITICAL FIX: block empty cache
            if not result or not getattr(result, "results", None):
                return None

            return result

    # -------------------------
    # SET CACHE
    # -------------------------
    async def set(self, image_path: str, result: SearchResult) -> None:
        image_hash = self._hash_image(image_path)

        # 🔴 DO NOT CACHE EMPTY RESULTS
        if not result.results or len(result.results) == 0:
            return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO cache_entries
                (image_hash, result_json, pipeline_version, sources_version, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    image_hash,
                    result.model_dump_json(),
                    PIPELINE_VERSION,
                    ",".join(result.sources_succeeded),
                    int(time.time()),
                    int(time.time() + DEFAULT_TTL),
                ),
            )
            await db.commit()

    # -------------------------
    # INVALIDATION
    # -------------------------
    async def invalidate(self, image_path: str) -> None:
        image_hash = self._hash_image(image_path)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM cache_entries WHERE image_hash=?",
                (image_hash,)
            )
            await db.commit()

    # -------------------------
    # PARTIAL RESULTS (optional system)
    # -------------------------
    async def get_partial(
        self,
        image_path: str,
        source_ids: List[str]
    ) -> List[NormalizedResult]:
        image_hash = self._hash_image(image_path)

        if not source_ids:
            return []

        placeholders = ",".join("?" * len(source_ids))

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"""
                SELECT result_json FROM source_contributions
                WHERE image_hash=? AND source_id IN ({placeholders})
                """,
                (image_hash, *source_ids)
            )

            rows = await cursor.fetchall()

            results: List[NormalizedResult] = []

            for (json_data,) in rows:
                try:
                    data = json.loads(json_data)
                    results.append(NormalizedResult(**data))
                except Exception:
                    continue

            return results