"""TuShare real-data adapter for Phase 23.
Secrets are never stored in project files; provide TUSHARE_TOKEN at runtime.
"""
from __future__ import annotations
import os, hashlib, json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

class TuShareProviderError(RuntimeError): pass

@dataclass
class ProbeResult:
    ok: bool
    message: str
    rows: int = 0

class TuShareProvider:
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv('TUSHARE_TOKEN', '').strip()
        if not self.token:
            raise TuShareProviderError('TUSHARE_TOKEN is not configured')
        self._pro = None

    def _client(self):
        if self._pro is None:
            try:
                import tushare as ts
            except ImportError as e:
                raise TuShareProviderError('tushare package is not installed; install it in a network-enabled environment') from e
            self._pro = ts.pro_api(self.token)
        return self._pro

    def probe(self) -> ProbeResult:
        try:
            df = self._client().stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
            return ProbeResult(True, 'TuShare stock_basic probe succeeded', len(df))
        except Exception as e:
            return ProbeResult(False, f'{type(e).__name__}: {e}', 0)

    def daily(self, ts_code: str, start_date: str, end_date: str):
        return self._client().daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

    @staticmethod
    def fingerprint_dataframe(df: Any) -> str:
        payload = df.to_csv(index=False).encode('utf-8')
        return hashlib.sha256(payload).hexdigest()

    def save_dataset(self, df: Any, path: str | Path, metadata: dict[str, Any]) -> dict[str, Any]:
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        record = dict(metadata)
        record.update({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'rows': len(df)})
        meta_path = path.with_suffix(path.suffix + '.metadata.json')
        meta_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        return record
