# -*- coding: utf-8 -*-
"""生成收据（A7）：`runtime/receipt.py` 的命令行入口。

用法::

    python scripts/gen_receipt.py \
        --generator scripts/run_fundamental_factor_study.py \
        --param max_stocks=40 --param min_cross_section=5 \
        --input D:/tdx_dataset_v3/fundamentals.jsonl \
        --artifact D:/_ext_verify/receipt_demo/a/run.json \
        --root D:/ \
        --out D:/_ext_verify/receipt_demo/a/receipt.json \
        --md-out D:/_ext_verify/receipt_demo/a/receipt.md

`--root` 决定路径如何归一：收据里只有**相对 root** 的路径，
因此把同一批文件放到另一个绝对路径下重跑，摘要不变（判据 T-2）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime.receipt import (  # noqa: E402
    build_receipt, render_markdown, verify_receipt, write_receipt,
)


def _parse_scalar(text: str) -> Any:
    """``k=v`` 的 v 自动解析：int → float → true/false → 字符串。"""
    if text in ("true", "false"):
        return text == "true"
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def parse_params(items: List[str]) -> Tuple[dict, List[str]]:
    """把 ``["k=v", ...]`` 解析成 dict；返回 ``(params, 解析告警)``。"""
    params: dict = {}
    warnings: List[str] = []
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--param 必须是 k=v 形式: {item!r}")
        key, _, value = item.partition("=")
        key = key.strip()
        if not key:
            raise SystemExit(f"--param 的键为空: {item!r}")
        if key in params:
            warnings.append(f"参数重复，后者覆盖前者: {key}")
        params[key] = _parse_scalar(value.strip())
    return params, warnings


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成收据（输入+生成器+参数+产物）")
    ap.add_argument("--generator", required=True, help="生成器源码文件（版本由它算出）")
    ap.add_argument("--param", action="append", default=[], help="k=v，可重复")
    ap.add_argument("--input", action="append", default=[], help="输入文件，可重复")
    ap.add_argument("--artifact", action="append", default=[], help="产物文件，可重复")
    ap.add_argument("--root", required=True, help="路径归一基准（收据内只存相对路径）")
    ap.add_argument("--out", required=True, help="收据 JSON 落盘路径")
    ap.add_argument("--md-out", default="", help="人读表格落盘路径（哈希由产物算出）")
    ap.add_argument("--note", default=None,
                    help="自由文本（不进摘要，仅展示；如生成时刻）")
    ap.add_argument("--verify", action="store_true",
                    help="生成后立即自校验（推荐；能立刻发现路径写错）")
    args = ap.parse_args(argv)

    params, warnings = parse_params(args.param)
    for w in warnings:
        print(f"⚠️ {w}", flush=True)

    receipt = build_receipt(
        generator=args.generator,
        params=params,
        inputs=args.input,
        artifacts=args.artifact,
        root=args.root,
        notes=args.note,
    )
    write_receipt(receipt, args.out)
    print(f"已写出收据：{args.out}", flush=True)
    print(f"  receipt_sha256 = {receipt['receipt_sha256']}", flush=True)
    print(f"  生成器 {receipt['generator']['path']} "
          f"sha256={receipt['generator']['sha256'][:16]}…", flush=True)
    print(f"  输入 {len(receipt['inputs'])} 份 / 产物 {len(receipt['artifacts'])} 份",
          flush=True)

    if args.md_out:
        Path(args.md_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md_out).write_text(render_markdown(receipt), encoding="utf-8",
                                     newline="\n")
        print(f"已写人人可读表格：{args.md_out}", flush=True)

    if args.verify:
        report = verify_receipt(receipt, root=args.root)
        print(f"自校验通过：输入 {report['checked_inputs']} / "
              f"产物 {report['checked_artifacts']} 份哈希一致"
              f"（notes 未校验）", flush=True)

    if args.note:
        print("（notes 不进摘要；改动它不会改变 receipt_sha256，这是刻意的）",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
