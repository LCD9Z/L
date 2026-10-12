# -*- coding: utf-8 -*-
"""baostock 客户端**分页静默截断**的守卫。

## 机制（读 `baostock/data/resultset.py` 得出，非推测）

``ResultData.next()`` 在「当前页取完」时的分支：

.. code-block:: text

    if len(self.data) <  BAOSTOCK_PER_PAGE_COUNT: return False   # 不足一页 → 确实结束
    if len(self.data) >  BAOSTOCK_PER_PAGE_COUNT: return False   # 服务端一次给全了 → 结束
    # 恰好 == 2000 → 去取下一页
    receive_data = sock.send_msg(...)
    if receive_data is None or receive_data.strip() == "": return False   # ← 静默停止
    ...
    if cons.BSERR_SUCCESS == self.error_code: ...
    else: return False                                                   # ← 静默停止

**关键**：当某一页**恰好**返回 ``BAOSTOCK_PER_PAGE_COUNT``(=2000) 行时，客户端会去取下一页；
**若该请求失败（空响应或非成功错误码），``next()`` 直接返回 ``False`` 且不抛任何异常**
→ 调用方看到的是「**干净地结束在 2000 行**」。

## 为什么必须守卫

- **不报错**：无异常、无 ``error_code`` 冒泡 —— 属本项目反复警惕的「静默失效」
- **看起来有数据**：2000 行是**合法行数**，下游 ``min_rows`` 阈值未必拦得住
  （如 L1 下限 4000，截断到 4000 就会通过）
- **时变**：服务端有时一次返回全量（如 8,992 > 2000 → 不分页），有时只返回一页
  → **同一版本、同一接口、不同时刻结果不同**（2026-10-12 实测：08:0x = 8,992；11:3x = 2,000；12:39 = 8,992）

## 判据

**总数恰为 2000 的整数倍 ⇒ 可疑**（需复测或人工确认），因为截断只能落在整数倍上。
合法总数恰为整数倍时也会命中 —— 故本判据是**「须复核」而非「必定错」**。
"""

from __future__ import annotations

from typing import Final

#: 与 ``baostock.common.contants.BAOSTOCK_PER_PAGE_COUNT`` 保持一致。
#: ⚠️ 该常量是 baostock 的**私有实现细节**，上游若改动本模块须同步
#: （`tests/test_pit_snapshot_scripts.py` 有对 2000 的守卫）。
BAOSTOCK_PER_PAGE_COUNT: Final[int] = 2000


def suspect_truncation(n: int) -> bool:
    """``n`` 是否为**疑似分页静默截断**的行数。

    >>> suspect_truncation(2000)
    True
    >>> suspect_truncation(4000)
    True
    >>> suspect_truncation(8992)
    False
    >>> suspect_truncation(0)
    False
    """
    return n > 0 and n % BAOSTOCK_PER_PAGE_COUNT == 0


def assert_not_truncated(n: int, what: str) -> None:
    """``n`` 疑似截断即抛错 —— **宁可失败，不可静默写入残缺快照**。

    报错信息给出重试指引：服务端行为时变，**重跑一次往往就能拿到全量**。
    """
    if suspect_truncation(n):
        raise RuntimeError(
            f"{what} 返回 {n} 行，恰为 {BAOSTOCK_PER_PAGE_COUNT} 的整数倍 —— "
            f"疑似 baostock 客户端**分页静默截断**"
            f"（见 pit/baostock_guard.py 的机制说明）。\n"
            f"处理：① 重跑一次（服务端行为时变，实测同一接口 8,992 / 2,000 都出现过）；"
            f"② 若重跑仍相同，请人工确认该接口的真实总数后再落盘。"
        )
