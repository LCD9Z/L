"""Fast inventory helpers for the TDX daily dataset.

The production inventory for the supplied 9.8M-row archive was computed with
streaming shell tools to avoid loading the raw CSV into memory.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Inventory:
    rows: int
    stock_rows: int
    unique_codes: int
    stock_codes: int
    unique_stock_keys: int
    duplicate_stock_code_date: int
    malformed_rows: int
    min_date: str
    max_date: str

    @property
    def stock_duplicate_free(self) -> bool:
        return self.duplicate_stock_code_date == 0
