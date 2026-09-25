# -*- coding: utf-8 -*-
r"""研究产物的**增量落盘** —— 长跑脚本必须分段落盘。

## 为什么需要

本机后台进程会**静默死亡**（SOUL.md 明列的工程风险）。2026-09-23 实测：
集中度实验跑到**第 11/12 次回测**时进程无报错退出，因脚本只在结尾写一次 JSON，
**10 次回测（约 2 小时）的结果全部丢失**。同类问题 2026-09-19 也发生过一次。

## 设计：`.partial` / 正式文件 双文件

* 每完成一个**工作单元**（一次回测 / 一个变体 / 一个窗口）→ 写 ``<out>.partial``，
  载荷含 ``"complete": False``；
* 全部完成 → 写正式 ``<out>``，载荷含 ``"complete": True``。

因此：

1. **存在正式 ``<out>`` 即代表跑完** —— 读者无需猜测；
2. ``<out>.partial`` 永远可抢救，**且不会被误当作完整结果**；
3. 写入用 ``os.replace`` **原子替换** —— 不会读到写了一半的文件。

## 用法

::

    from research_artifacts import write_final, write_partial

    for unit in units:
        rows.append(run(unit))
        write_partial(args.out, {"rows": rows, "args": vars(args)})

    write_final(args.out, {"rows": rows, "summary": summary, "args": vars(args)})

``out`` 为空时两个函数都是空操作（脚本支持不落盘）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

__all__ = ["PARTIAL_SUFFIX", "read_partial", "write_final", "write_partial"]

PARTIAL_SUFFIX = ".partial"


def _atomic_write(path: str, payload: Dict[str, Any]) -> None:
    """先写 ``<path>.tmp`` 再 ``os.replace`` —— 避免读到半成品。"""
    p = Path(path)
    tmp = str(p) + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, p)


def write_partial(out: str, payload: Dict[str, Any], *, note: str = "") -> None:
    """把当前已完成的结果写到 ``<out>.partial``。

    ``note`` 可写明进度（如 ``"已完成 5/12 次回测"``），便于抢救时判断完整度。
    """
    if not out:
        return
    body = dict(payload)
    body["complete"] = False
    body["note"] = note or "部分结果（进程可能仍在运行或已静默死亡）"
    try:
        _atomic_write(out + PARTIAL_SUFFIX, body)
    except OSError:
        # 落盘失败不得影响研究本身 —— 但仍要让调用方看到
        print(f"  [warn] 增量落盘失败: {out}{PARTIAL_SUFFIX}")


def write_final(out: str, payload: Dict[str, Any]) -> None:
    """写正式产物（带 ``complete: True``）。**只有跑完才应调用。**"""
    if not out:
        return
    body = dict(payload)
    body["complete"] = True
    _atomic_write(out, body)
    print(f"\n结果已写入: {out}")


def read_partial(out: str) -> Dict[str, Any] | None:
    """读回 ``<out>.partial``（不存在或损坏时返回 ``None``）。"""
    p = Path(out + PARTIAL_SUFFIX)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
