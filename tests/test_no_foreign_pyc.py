# -*- coding: utf-8 -*-
"""防止「跨仓库字节码顶替本仓库源码」——2026-10-18 实测踩到的一次静默失效。

## 发生了什么

`trunk` 的 `__pycache__/` 里混入了 **129 个**从别的路径编译的 `.pyc`：

| 来源 | 个数 | 代码是否与 trunk 源码一致 |
|---|---|---|
| `D:\\hunhe\\1.0\\...` | 106 | **不一致**（DIFF） |
| `C:\\Users\\T430\\Desktop\\1.0\\...` | 若干 | 不一致 |
| 其余外部路径 | 23 | 一致（仅路径标签不同） |

关键在于 **`.pyc` 头部记录的 `mtime`/`size` 与 trunk 的 `.py` 完全匹配**
（复制时保留了时间戳），于是 CPython 的 import 机制**优先加载外部字节码**，
trunk 的源码被跳过。

后果：`python -m pytest` 看起来在测 trunk，实际执行的是
`D:\\hunhe\\1.0` 时代的代码。traceback 会显示 `???`（源码路径不存在），
但测试照样"通过"或"失败"——**只是那个通过/失败不属于这个仓库**。

受影响的高危模块包括 `tdx_native/day_reader.py`（接口契约踩过两次）、
`validation/multiple_testing.py`、`conftest.py`、`track/costs.py`
以及 8 个测试文件。

## 为什么是「静默失效」家族的新形态

它同时满足本项目已知的三种失效形态：

- 「读磁盘能通过 ≠ 文件入库」——这里反过来：**源码在磁盘上对，跑的不是它**；
- 「能力已实现 ≠ 能力在生效」——源码是对的，生效的是别处编译的副本；
- 「测试全绿 ≠ 纪律成立」——验证者（pytest）与被验证者（源码）被拆开了。

## 判据

`__pycache__/*.pyc` 的 `co_filename` 必须位于**本仓库根**之下。
纯 Python 实现（`marshal` + `pathlib`），**不 shell out**
（2026-10-17 教训：缺 `grep.exe` 时 subprocess 会把环境缺失伪装成断言失败）。
"""
import marshal
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _co_filename(pyc: pathlib.Path):
    """读出 .pyc 里记录的源码路径；读不出返回 None。"""
    try:
        return marshal.loads(pyc.read_bytes()[16:]).co_filename
    except Exception:
        return None


def _is_foreign(pyc: pathlib.Path, co_filename) -> bool:
    """判据核心：给定 .pyc 路径与其 co_filename，是否算「外部字节码」。

    读不出 co_filename 一律算外部（损坏的 .pyc 同样是问题）。

    ⚠️ 2026-10-18 修：第一版用裸 `startswith(str(ROOT))`，被自己的反向验证
    抓到缺陷——`D:\\hunhe\\trunk_backup\\x.py` 会匹配 `D:\\hunhe\\trunk` 前缀
    而被误判为「本仓库内」。故改为**先规范化、再要求路径分隔符边界**：
    - 统一小写（Windows 盘符/目录大小写不敏感）；
    - 根路径末尾补 `/`，保证 `trunk_backup` 不会冒充 `trunk` 的子路径。
    """
    if co_filename is None:
        return True
    try:
        root_norm = ROOT.resolve().as_posix().lower().rstrip("/") + "/"
        cf_norm = pathlib.Path(co_filename).as_posix().lower()
        return not cf_norm.startswith(root_norm)
    except (ValueError, OSError):
        return True


def test_no_foreign_pyc_in_repo():
    """所有 .pyc 的 co_filename 必须落在本仓库内。"""
    foreign = []
    for pyc in sorted(ROOT.rglob("__pycache__/*.pyc")):
        if ".git" in pyc.parts:
            continue
        cf = _co_filename(pyc)
        if _is_foreign(pyc, cf):
            foreign.append((pyc, str(cf) if cf is not None else "<无法读取>"))
    assert not foreign, (
        f"发现 {len(foreign)} 个来自仓库外的字节码 —— 它们会顶替本仓库源码被 import"
        "（.pyc 头部的 mtime/size 若与 .py 匹配，CPython 优先用 .pyc）。\n"
        "来源通常是「从别的副本整目录复制文件进来」且保留了时间戳。\n"
        "修复：把这些 .pyc 移出仓库（用 os.replace 改名到同盘目录，勿批量删除），"
        "或直接删除整个 __pycache__ 让解释器重建。\n"
        + "\n".join(f"  {p.relative_to(ROOT)}  <-  {cf}" for p, cf in foreign[:20])
        + (f"\n  ……另 {len(foreign) - 20} 个" if len(foreign) > 20 else "")
    )


def test_foreign_pyc_guard_catches_a_planted_one():
    """反向验证：判据必须能识别外部来源。

    没有这一条，「守卫存在」本身也可能是失效的
    （2026-10-15 教训：改守卫自身必须附反向验证）。

    在**内存中**构造输入而不真的写文件——曾用「写一个假 .pyc 再删」的版本，
    但清理时 `os.replace` 跨磁盘失败（D: → C: Temp）反而让测试报错。
    判据是纯逻辑，用构造输入验证它比在磁盘上折腾更可靠，也无清理副作用。
    """
    # 1) 真实踩到过的三类来源，必须全部判为外部
    real_cases = [
        r"D:\hunhe\1.0\tests\test_layout_doc_in_sync.py",
        r"d:\hunhe\1.0\conftest.py",                        # 小写盘符也要抓
        r"C:\Users\T430\Desktop\1.0\tdx_native\day_reader.py",
        r"D:\hunhe\1.0 - 副本\scripts\run_recompute.py",     # 带空格与中文的路径
    ]
    for cf in real_cases:
        assert _is_foreign(pathlib.Path("tests/__pycache__/x.pyc"), cf), (
            f"判据漏掉了真实来源 {cf}"
        )

    # 2) 本仓库内的必须判为合法（含大小写不同的盘符）
    ok_cases = [
        str(ROOT / "tests" / "test_x.py"),
        str(ROOT).replace("D:", "d:") + r"\tests\test_x.py",
    ]
    for cf in ok_cases:
        assert not _is_foreign(pathlib.Path("tests/__pycache__/x.pyc"), cf), (
            f"判据把本仓库文件误判为外部 {cf} —— 会造成恒红噪声"
        )

    # 3) 读不出 co_filename 必须判为外部
    assert _is_foreign(pathlib.Path("tests/__pycache__/x.pyc"), None)

    # 4) 判据本身要能区别「相似但不同」的根路径
    near_miss = str(ROOT) + "_backup\\tests\\x.py"      # trunk_backup 不是 trunk
    assert _is_foreign(pathlib.Path("tests/__pycache__/x.pyc"), near_miss), (
        f"判据被前缀相似路径糊弄：{near_miss}"
    )


def test_pyc_reading_mechanism_works():
    """确认「读 .pyc 拿 co_filename」这条路本身是通的。

    否则上面全是空转——若 `marshal` 读法错了，主测试会水过。
    """
    import py_compile
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / "probe.py"
        src.write_text("x = 1\n", encoding="utf-8")
        cfile = pathlib.Path(td) / "probe.pyc"
        py_compile.compile(str(src), cfile=str(cfile), doraise=True)
        cf = _co_filename(cfile)
        assert cf is not None, "读不出 co_filename —— _co_filename 实现有误"
        assert "probe.py" in str(cf), f"co_filename 异常: {cf}"
        # 且它是「本仓库外」的（td 在 Temp 下）
        assert _is_foreign(cfile, cf)
