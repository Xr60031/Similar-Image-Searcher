# path: omnisource/core/sources/__init__.py
from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, Type

from omnisource.core.sources.base import SourceProvider


def discover_sources() -> Dict[str, SourceProvider]:
    """Dynamically discover all SourceProvider implementations."""
    sources: Dict[str, SourceProvider] = {}

    package = __name__

    for _, module_name, _ in pkgutil.iter_modules(__path__):
        if module_name == "base":
            continue

        module = importlib.import_module(f"{package}.{module_name}")

        for attr in dir(module):
            obj = getattr(module, attr)
            if (
                isinstance(obj, type)
                and issubclass(obj, SourceProvider)
                and obj is not SourceProvider
            ):
                instance = obj()
                sources[instance.source_id] = instance

    return sources