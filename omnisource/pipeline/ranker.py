# path: omnisource/pipeline/ranker.py
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict

from omnisource.core.models import NormalizedResult, RankedResult


DOMAIN_REPUTATION = {
    "artstation.com": 0.9,
    "deviantart.com": 0.9,
    "behance.net": 0.9,
    "reddit.com": 0.6,
    "pinterest.com": 0.6,
}


SOURCE_INDEPENDENCE = {
    "yandex": 1.0,
    "duckduckgo": 0.7,
    "reddit": 0.8,
    "artstation": 1.0,
}


@dataclass
class ScoringBreakdown:
    total_score: float
    consensus_score: float
    reputation_score: float
    independence_score: float
    recency_score: float
    reasons: List[str]
    contributing_sources: List[str]


class Ranker:

    def rank(self, results: List[NormalizedResult], total_sources: int) -> List[RankedResult]:
        grouped: Dict[str, List[NormalizedResult]] = defaultdict(list)

        for r in results:
            grouped[r.url].append(r)

        ranked: List[RankedResult] = []

        now = datetime.now(timezone.utc)

        for url, group in grouped.items():
            sources = list({r.source for r in group})
            n_sources = len(sources)

            # --- CONSENSUS (40)
            consensus_score = (n_sources / total_sources) * 40

            # --- REPUTATION (30)
            domain = group[0].domain
            rep = DOMAIN_REPUTATION.get(domain, 0.2)
            reputation_score = rep * 30

            # --- INDEPENDENCE (20)
            independence = sum(SOURCE_INDEPENDENCE.get(s, 0.5) for s in sources) / n_sources
            independence_score = independence * 20

            # --- RECENCY (10)
            age_seconds = (now - group[0].fetched_at).total_seconds()
            if age_seconds < 3600:
                recency_score = 10
            elif age_seconds < 86400:
                recency_score = 7
            else:
                recency_score = 3

            total = consensus_score + reputation_score + independence_score + recency_score

            reasons = [
                f"{n_sources} sources matched",
                f"domain reputation: {rep}",
                f"independence avg: {round(independence, 2)}",
                f"recency: {round(age_seconds)}s old",
            ]

            ranked.append(
                RankedResult(
                    normalized=group[0],
                    score=min(100.0, total),
                    reasons=reasons,
                    contributing_sources=sources,
                )
            )

        ranked.sort(key=lambda x: x.score, reverse=True)
        return ranked