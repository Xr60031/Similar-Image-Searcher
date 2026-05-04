# path: omnisource/core/sources/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict

from omnisource.core.models import NormalizedResult


class SourceProvider(ABC):
    """Abstract base class for all reverse image search providers."""

    @abstractmethod
    async def search_by_image(self, image_path: str) -> List[NormalizedResult]:
        """
        Search for similar images given a local path or URL.

        Providers must:
        - Handle network errors internally
        - Return empty list on recoverable failures
        - Only raise on programming errors
        """
        raise NotImplementedError

    @abstractmethod
    def capabilities(self) -> Dict:
        """Return provider capabilities."""
        raise NotImplementedError

    @abstractmethod
    def rate_limit_profile(self) -> Dict:
        """Return rate limit config."""
        raise NotImplementedError

    @abstractmethod
    def should_use_browser(self) -> bool:
        """Return True only if HTTP is not viable."""
        raise NotImplementedError

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique provider identifier."""
        raise NotImplementedError