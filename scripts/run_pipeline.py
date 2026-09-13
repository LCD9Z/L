# -*- coding: utf-8 -*-
"""V3.4 market-wide runner.

Examples:
  python run_pipeline.py --universe universe.jsonl --mode overnight --profile lite
  python run_pipeline.py --universe universe.jsonl --resume

The input universe is JSONL so a 5k+ market can be streamed with low RAM.
Each row may contain quote/factors prepared by an approved provider.
"""

from __future__ import annotations

# 脚本位于 scripts/ 下，需把项目根目录加入导入路径。
# 必须整体放在 from __future__ 之后 —— __future__ 导入只能是文件首条语句。
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import argparse, os
from datetime import datetime
from log_utils import get_logger
from market_universe_provider import iter_jsonl
from runtime.runtime_profile import get_profile
from screen_pipeline import ScreenConfig, run_screen
from stage2_enrichment import enrich_candidate

log = get_logger("pipeline")


def main():
    p = argparse.ArgumentParser(description="AI Stock God V3.4 A-share screening")
    p.add_argument("--universe", required=True, help="as-of JSONL universe snapshot")
    p.add_argument("--out", default=None, help="output/checkpoint directory")
    p.add_argument("--mode", choices=("once", "overnight"), default="once")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--profile", choices=("lite", "balanced", "full"), default="lite")
    p.add_argument("--stage1", type=int, default=300)
    p.add_argument("--stage2", type=int, default=50)
    p.add_argument("--ai", type=int, default=20)
    p.add_argument("--min-amount", type=float, default=None)
    p.add_argument("--cutoff", default=None, help="PIT cutoff for verified events/news; ISO date/time")
    p.add_argument("--no-stage2-enrich", action="store_true", help="disable deterministic flow/event/microstructure enrichment")
    args = p.parse_args()
    rp = get_profile(args.profile)
    out = args.out or os.path.join("reports", "market_screen_" + datetime.now().strftime("%Y%m%d"))
    cfg = ScreenConfig(stage1_keep=args.stage1, stage2_keep=args.stage2,
                       ai_keep=args.ai, min_amount=args.min_amount,
                       checkpoint_every=250 if args.mode == "overnight" else 1000)
    log.info(f"V3.4 {args.mode} | profile={rp.name} | workers={rp.max_workers} | out={out}")
    enrich = None if args.no_stage2_enrich else (lambda row: enrich_candidate(row, cutoff=args.cutoff or row.get("asof")))
    result = run_screen(iter_jsonl(args.universe), out, cfg, enrich=enrich, resume=args.resume)
    log.info(f"完成：seen={result['counts']['seen']} eligible={result['counts']['eligible']} "
             f"stage1={len(result['stage1'])} stage2={len(result['stage2'])} ai={len(result['ai_candidates'])}")
    log.info(f"快照：{os.path.join(out, 'screen_snapshot.json')}")


if __name__ == "__main__":
    main()
