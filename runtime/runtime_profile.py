# -*- coding: utf-8 -*-
"""8GB-friendly runtime profile.

The heavy part of the system is remote LLM calls, not Python factor math.  This
module keeps concurrency bounded and caps output tokens so a normal 8GB machine
can run the pipeline without creating a large local working set.
"""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class RuntimeProfile:
    name: str
    max_workers: int
    analyst_tokens: int
    research_tokens: int
    committee_tokens: int
    decision_tokens: int
    news_limit: int
    factor_window: int


PROFILES = {
    # Default for the user's 8GB class machine: 4 concurrent HTTP calls, small
    # structured outputs, and only 60 bars for the factor layer.
    "lite": RuntimeProfile("lite", 3, 1400, 1300, 1800, 1500, 3, 40),
    "balanced": RuntimeProfile("balanced", 4, 1800, 1600, 2200, 1800, 5, 60),
    "full": RuntimeProfile("full", 4, 2600, 2200, 3000, 2400, 8, 120),
}


def get_profile(name=None):
    name = (name or os.getenv("AI_STOCK_PROFILE", "balanced")).lower()
    if name not in PROFILES:
        name = "balanced"
    p = PROFILES[name]
    # Environment override is deliberately capped: don't let an accidental
    # setting create dozens of concurrent model requests on an 8GB machine.
    env_workers = os.getenv("AI_STOCK_MAX_WORKERS")
    if env_workers:
        try:
            workers = max(1, min(int(env_workers), 4))
            p = RuntimeProfile(p.name, workers, p.analyst_tokens, p.research_tokens,
                               p.committee_tokens, p.decision_tokens,
                               p.news_limit, p.factor_window)
        except ValueError:
            pass
    return p
