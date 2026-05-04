# path: omnisource/core/telemetry.py
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict

import structlog


logger = structlog.get_logger()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceMetrics:
    def __init__(self) -> None:
        self.success_count = 0
        self.failure_count = 0
        self.total_latency = 0.0

    def record(self, success: bool, latency_ms: float) -> None:
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        self.total_latency += latency_ms

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return (self.success_count / total) if total > 0 else 0.0

    @property
    def avg_latency(self) -> float:
        total = self.success_count + self.failure_count
        return (self.total_latency / total) if total > 0 else 0.0


class TelemetryCollector:
    def __init__(self) -> None:
        self._metrics: Dict[str, SourceMetrics] = {}

    def record_source_attempt(self, source_id: str, success: bool, latency_ms: float) -> None:
        if source_id not in self._metrics:
            self._metrics[source_id] = SourceMetrics()

        self._metrics[source_id].record(success, latency_ms)

        logger.info(
            "source_attempt",
            timestamp=utc_now_iso(),
            source=source_id,
            status="success" if success else "failure",
            latency_ms=latency_ms,
        )

    def get_source_stats(self) -> Dict[str, Dict]:
        stats = {}
        for source_id, metrics in self._metrics.items():
            stats[source_id] = {
                "success_rate": metrics.success_rate,
                "failure_count": metrics.failure_count,
                "avg_latency_ms": metrics.avg_latency,
            }
        return stats

    def export_json(self, path: str) -> None:
        import json

        with open(path, "w") as f:
            json.dump(self.get_source_stats(), f, indent=2)