# -*- coding: utf-8 -*-
"""守卫：baostock 抓取脚本必须设置**连接级**超时，且顺序正确。

## 锁住什么

`scripts/fetch_baostock_xsrc.py` 此前**没有任何连接级超时** ——
baostock 偶发挂起（login / 取数）会让抓取**永久阻塞**，
只能靠上层子进程超时兜底（2026-10-14 由信箱巡检登记为主干内部待决项）。

同目录的 `fetch_delisted_full.py` 早有 `urlopen(timeout=25)` +
`socket.setdefaulttimeout(30)`，**只有 baostock 这个漏了**。

## 为什么本守卫要查「顺序」而不只是「有没有」

`socket.setdefaulttimeout()` **只影响其后新建的 socket**，
而 baostock 的服务端连接是在 `bs.login()` 时建立的。

→ 若把 `setdefaulttimeout` 放在 `login()` **之后**，代码「看起来改了」，
但**完全不生效** —— 典型的「静默无效」。故必须校验行号顺序。

## 为什么用 AST 而不是字符串查找

模块 docstring 里同时提到了 `bs.login()` 与 `socket.setdefaulttimeout()`，
且 docstring 中前者在前。**字符串 `find()` 会被文档文本误导**，
从而把「正确代码」判成「顺序错误」。→ 用 AST 只取**真实调用**的行号。
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "fetch_baostock_xsrc.py"


def _src() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _call_lines(src: str) -> dict:
    """返回 {限定调用名: 最小行号}（只算真实 ast.Call，不含注释/字符串）。"""
    found: dict[str, int] = {}
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute):
            continue
        base = getattr(fn.value, "id", None)
        name = f"{base}.{fn.attr}" if base else fn.attr
        prev = found.get(name)
        found[name] = node.lineno if prev is None else min(prev, node.lineno)
    return found


def test_script_exists():
    assert SCRIPT.is_file(), "fetch_baostock_xsrc.py 缺失"


def test_declares_timeout_cli_arg():
    src = _src()
    assert '"--timeout"' in src, "缺少 --timeout 参数（无法调节连接级超时）"


def test_sets_socket_timeout():
    calls = _call_lines(_src())
    assert "socket.setdefaulttimeout" in calls, (
        "未设置连接级 socket 超时 —— baostock 挂起会让抓取永久阻塞，"
        "只能靠子进程超时兜底"
    )


def test_socket_timeout_set_before_login():
    """⚠️ 核心：setdefaulttimeout 必须在 bs.login() **之前**，否则不生效。"""
    calls = _call_lines(_src())
    assert "socket.setdefaulttimeout" in calls, "未找到 socket.setdefaulttimeout(...)"
    assert "bs.login" in calls, "未找到 bs.login()"
    assert calls["socket.setdefaulttimeout"] < calls["bs.login"], (
        "socket.setdefaulttimeout 出现在 bs.login() 之后 —— "
        "该调用只影响其后新建的 socket，而 baostock 连接在 login 时建立，"
        "故实际上**不会生效**"
    )
