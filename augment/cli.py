# -*- coding: utf-8 -*-
"""augment 命令行入口（**E3 · 正式入口**，但不参与生产结论链）。

用法::

    python -m augment.cli explain     --date 2026-10-15          # 角色 1（P1）
    python -m augment.cli hypothesize --from reports/            # 角色 2（P2，低频）
    python -m augment.cli render      --input reports/xxx.json   # 角色 3（P3）
    python -m augment.cli self-check                             # 隔离契约自检（P0 已实现）

退出码：
- ``0`` 成功
- ``3`` 该角色在当前阶段尚未实现（P1/P2/P3 逐步落地）

⚠️ 本入口**不参与生产**：任何失败都不得影响 E1（``tdx_native.run_daily``）。
生产侧通过 ``--with-augment`` **以子进程方式**调用本入口（见 CODE_WIKI/08 篇 §八），
因此 08 篇守卫断言 1（除 augment 外无模块 import augment）天然成立。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from augment import contract

#: 角色尚未实现的退出码
EXIT_NOT_IMPLEMENTED = 3


def _warn(msg: str) -> None:
    print(msg, file=sys.stderr)


def cmd_explain(args: argparse.Namespace) -> int:
    """角色 1 · 解释层（P1 落地）。"""
    _warn("[augment] 角色 1「解释层」将在 P1 落地（需 llm_config.json，不入库）。")
    _warn(f"[augment] 预期输入: reports/daily/recommend_{args.date}.json")
    return EXIT_NOT_IMPLEMENTED


def cmd_hypothesize(args: argparse.Namespace) -> int:
    """角色 2 · 假设生成器（P2 落地，低频且须人工裁决）。"""
    _warn("[augment] 角色 2「假设生成器」将在 P2 落地。")
    _warn("[augment] 注意：它不挂每日循环，产出仅为候选，须经人工裁决后才写预注册。")
    _warn(f"[augment] 预期输入目录: {args.from_dir}")
    return EXIT_NOT_IMPLEMENTED


def cmd_render(args: argparse.Namespace) -> int:
    """角色 3 · 呈现层（P3 落地）。"""
    _warn("[augment] 角色 3「呈现层」将在 P3 落地。")
    _warn("[augment] 红线：渲染器不得改写结论，INCONCLUSIVE 不得渲染成确定表述。")
    _warn(f"[augment] 预期输入: {args.input}")
    return EXIT_NOT_IMPLEMENTED


def cmd_self_check(args: argparse.Namespace) -> int:
    """隔离契约自检 —— 不写 ``reports/``，全部在临时目录内验证。

    这些探针与 ``tests/test_augment_isolation.py`` 同源，但可在无 pytest 环境下
    独立运行，便于投产前快速确认隔离红线仍然成立。
    """
    failures: List[str] = []

    # 探针 1：claim_tier 是 ClassVar，传入即 TypeError（结构上无法冒充证据）
    try:
        contract.AugmentNote(claim_tier="evidence")      # type: ignore[call-arg]
        failures.append("探针1 失败：claim_tier 竟可被调用方传入")
    except TypeError:
        pass

    # 探针 2：路径逃逸日期被拒
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / contract.AUGMENT_SUBDIR
        try:
            contract.write_notes([], base_dir=base, date="../../escape", kind="explain")
            failures.append("探针2 失败：非法 date 竟被接受")
        except contract.AugmentWriteError:
            pass

        # 探针 3：非法 kind 被拒
        try:
            contract.write_notes([], base_dir=base, date="2026-10-15", kind="verdict")
            failures.append("探针3 失败：非法 kind 竟被接受")
        except contract.AugmentWriteError:
            pass

        # 探针 4：正常落盘且 claim_tier 恒为 non-evidence
        note = contract.AugmentNote(code="000001", trade_date="2026-10-15",
                                    role="risk", text="自检探针")
        path = contract.write_notes([note], base_dir=base, date="2026-10-15",
                                    kind="explain")
        got = json.loads(path.read_text(encoding="utf-8"))
        if got.get("claim_tier") != contract.NON_EVIDENCE:
            failures.append("探针4 失败：落盘 claim_tier 偏离")
        if path.parent.resolve() != base.resolve():
            failures.append("探针4 失败：产物未落在 base_dir 内")

    if failures:
        for f in failures:
            _warn(f"[augment] {f}")
        return 1

    print("[augment] 自检通过：隔离红线成立（claim_tier 强制 / 路径前缀 / 种类白名单）。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="augment.cli",
        description="A 线可选增强模块（E3）。只读主干产物，只产出旁注，不产出结论。")
    sub = p.add_subparsers(dest="cmd", required=True)

    help_common = "产物根目录（默认 reports/augment）"

    e = sub.add_parser("explain", help="角色 1 · 解释层（P1）")
    e.add_argument("--date", required=True, help="主干推荐日，如 2026-10-15")
    e.add_argument("--base-dir", default=contract.AUGMENT_SUBDIR, help=help_common)
    e.set_defaults(func=cmd_explain)

    h = sub.add_parser("hypothesize", help="角色 2 · 假设生成器（P2）")
    h.add_argument("--from", dest="from_dir", default="reports/",
                   help="读取的证据目录（只读）")
    h.add_argument("--base-dir", default=contract.AUGMENT_SUBDIR, help=help_common)
    h.set_defaults(func=cmd_hypothesize)

    r = sub.add_parser("render", help="角色 3 · 呈现层（P3）")
    r.add_argument("--input", required=True, help="待渲染的主干 JSON")
    r.add_argument("--base-dir", default=contract.AUGMENT_SUBDIR, help=help_common)
    r.set_defaults(func=cmd_render)

    s = sub.add_parser("self-check", help="隔离契约自检（P0 已实现）")
    s.set_defaults(func=cmd_self_check)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
