# -*- coding: utf-8 -*-
"""Phase 19: append-only paper-trading ledger."""
import json
from pathlib import Path

def append_event(path,event):
    p=Path(path); events=[]
    if p.exists():
        try: events=json.loads(p.read_text(encoding='utf-8'))
        except Exception: events=[]
    events.append(dict(event)); p.write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
    return len(events)

def load_events(path):
    p=Path(path)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else []
