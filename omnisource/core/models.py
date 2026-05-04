# path: omnisource/core/models.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict
from urllib.parse import urlparse

from pydantic import BaseModel, field_validator, Field


class NormalizedResult(BaseModel):
    url: str
    image_url: Optional[str] = None
    title: Optional[str] = None
    source: str
    domain: str = ""
    confidence_signals: List[str] = Field(default_factory=list)
    raw_context: Dict = Field(default_factory=dict)
    fetched_at: datetime

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("URL must be http or https")
        if not parsed.netloc:
            raise ValueError("URL must have a domain")
        return v

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v

        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            return None
        if not parsed.netloc:
            return None

        return v

    @field_validator("domain", mode="before")
    @classmethod
    def extract_domain(cls, v, values):
        url = values.data.get("url")
        if not url:
            return v

        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        if domain.startswith("www."):
            domain = domain[4:]

        return domain


class RankedResult(BaseModel):
    normalized: NormalizedResult
    score: float
    reasons: List[str]
    contributing_sources: List[str]

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: float) -> float:
        if not (0.0 <= v <= 100.0):
            raise ValueError("Score must be between 0 and 100")
        return v


class SearchResult(BaseModel):
    query_image_hash: str
    results: List[RankedResult]
    sources_attempted: List[str]
    sources_succeeded: List[str]
    pipeline_version: str
    generated_at: datetime


class SourceStats(BaseModel):
    success_rate: float
    failure_count: int
    avg_latency_ms: float
    last_used_at: Optional[datetime] = None