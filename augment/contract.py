# -*- coding: utf-8 -*-
"""augment 数据契约：``AugmentNote`` 与受隔离约束的落盘函数。

⚠️ 本模块是 CODE_WIKI/08 篇 §二「类型级隔离」的落地实现：
边界不靠"约定"，靠**结构**挡住。

- ``AugmentNote.claim_tier`` 是 ``ClassVar``，**不是** dataclass 字段 ——
  调用方写 ``AugmentNote(claim_tier="evidence")`` 会因参数不被接受而 ``TypeError``，
  从结构上杜绝「旁注冒充证据」。
- ``write_notes`` 落盘前校验目标路径**必须在 base_dir 内**（§六 红线 1 / 守卫断言 5），
  且逐条复核 ``claim_tier``（守卫断言 3）。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional

#: 产物根目录（相对项目根）。本包只允许写这个目录（08 篇 §六 红线 1）。
AUGMENT_SUBDIR = "reports/augment"

#: 非证据层的唯一合法取值。全局只此一处，任何产物都不得偏离。
NON_EVIDENCE = "non-evidence"

#: 允许的产物种类（同时决定文件名前缀）
ALLOWED_KINDS = ("explain", "hypotheses", "render")


class AugmentWriteError(RuntimeError):
    """写盘被隔离红线拒绝。"""


@dataclass
class AugmentNote:
    """一条旁注（非证据层）。

    字段刻意保持最小：只记「谁在哪个标的哪一天说了什么」+ 可追溯指纹，
    不引入任何可被误读为「结论」的字段。
    """

    claim_tier: ClassVar[str] = NON_EVIDENCE

    code: str = ""
    trade_date: str = ""
    role: str = ""
    text: str = ""
    input_digest: str = ""
    model: Optional[str] = None
    prompt_digest: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化。``ClassVar`` 不进 ``asdict``，故显式补回 ``claim_tier``。"""
        d: Dict[str, Any] = asdict(self)
        d["claim_tier"] = self.claim_tier
        return d


def digest_bytes(payload: bytes) -> str:
    """返回字节内容的 sha256（十六进制）。"""
    return hashlib.sha256(payload).hexdigest()


def digest_of(path: Path) -> str:
    """返回文件内容的 sha256 —— 用于 ``input_digest``（纪律 2.4「数字须可追」）。"""
    return digest_bytes(Path(path).read_bytes())


def _reject_unsafe_token(value: str, field_name: str) -> None:
    """拒绝可逃出 base_dir 的路径片段（外部输入边界校验）。"""
    if not value:
        raise AugmentWriteError(f"{field_name} 不可为空")
    if "/" in value or "\\" in value or ".." in value or ":" in value:
        raise AugmentWriteError(f"{field_name} 含非法路径字符: {value!r}")


def write_notes(
    notes: List[AugmentNote],
    *,
    base_dir: Path,
    date: str,
    kind: str,
) -> Path:
    """原子写入 ``<base_dir>/{kind}_{date}.json``，并强制复核隔离红线。

    ``base_dir`` 可注入（守卫测试用 ``tmp_path``），默认调用方应传
    ``Path(AUGMENT_SUBDIR)`` —— 本函数**不猜测**调用方的目录，
    而是校验最终路径的父目录必须等于 ``base_dir``（守卫断言 5）。
    """
    if kind not in ALLOWED_KINDS:
        raise AugmentWriteError(f"非法的产物种类 {kind!r}，只允许 {ALLOWED_KINDS}")
    _reject_unsafe_token(date, "date")

    base = Path(base_dir)
    base_resolved = base.resolve()
    target = base / f"{kind}_{date}.json"

    # 红线 1：产物路径必须落在 base_dir 内（防 ../ 逃逸）
    if target.resolve().parent != base_resolved:
        raise AugmentWriteError(f"产物路径越界，拒绝写入: {target}")

    payload_notes: List[Dict[str, Any]] = []
    for note in notes:
        d = note.to_dict()
        # 红线 2 / 断言 3：逐条复核 claim_tier
        if d.get("claim_tier") != NON_EVIDENCE:
            raise AugmentWriteError(
                f"claim_tier 必须为 {NON_EVIDENCE!r}，实测 {d.get('claim_tier')!r}")
        payload_notes.append(d)

    payload: Dict[str, Any] = {
        "claim_tier": NON_EVIDENCE,
        "kind": kind,
        "date": date,
        "notes": payload_notes,
    }

    base.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)
    return target
