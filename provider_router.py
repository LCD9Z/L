# -*- coding: utf-8 -*-
"""V3 provider routing and graceful degradation.

This module does not hard-depend on any external data package. It exposes a
small provider registry so a-stock-data/easy-tdx/Tushare adapters can be added
without contaminating the research layer with source-specific APIs.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List


@dataclass
class Provider:
    name: str
    priority: int
    available: Callable[[], bool]
    fetch: Callable[..., Any]


class ProviderRouter:
    def __init__(self):
        self._providers: Dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        self._providers[provider.name] = provider

    def available(self) -> list:
        return [
            p.name for p in sorted(self._providers.values(), key=lambda x: x.priority)
            if p.available()
        ]

    def fetch_first(self, *args, **kwargs):
        errors: List[Dict[str, str]] = []
        for p in sorted(self._providers.values(), key=lambda x: x.priority):
            if not p.available():
                continue
            try:
                result = p.fetch(*args, **kwargs)
                if result is not None:
                    return result, p.name, errors
            except Exception as exc:  # provider isolation by design
                errors.append({"provider": p.name, "error": str(exc)})
        return None, None, errors


def module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False
