# path: omnisource/pipeline/cleaner.py
from __future__ import annotations

from typing import List, Dict
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from omnisource.core.models import NormalizedResult


TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "fbclid", "gclid", "mc_cid", "mc_eid", "source", "medium", "campaign"
}


def clean_url(url: str) -> str:
    parsed = urlparse(url)

    query = parse_qsl(parsed.query)
    filtered = [(k, v) for k, v in query if k not in TRACKING_PARAMS]

    new_query = urlencode(sorted(filtered))

    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip("/"),
        "",
        new_query,
        ""
    ))


def deduplicate(results: List[NormalizedResult]) -> List[NormalizedResult]:
    seen_exact = set()
    seen_domain_path = set()

    unique: List[NormalizedResult] = []

    for r in results:
        cleaned = clean_url(r.url)

        parsed = urlparse(cleaned)
        domain_path = f"{parsed.netloc}{parsed.path}"

        if cleaned in seen_exact:
            continue

        if domain_path in seen_domain_path:
            continue

        seen_exact.add(cleaned)
        seen_domain_path.add(domain_path)

        r.url = cleaned
        unique.append(r)

    return unique