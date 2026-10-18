# -*- coding: utf-8 -*-
"""A7 收据守卫（RECEIPT_PREREG 判据 T 组）。

## 锁住什么

- T-1 确定性：同输入两次 build ⇒ 摘要逐位相同；
- T-2 路径无关：同内容放两个不同绝对路径 ⇒ 摘要相同（绝对路径不进摘要）；
- T-3 参数序无关、值敏感；
- T-4/T-12 生成器源码变 1 字节 ⇒ `GeneratorChangedError`（**不是** Integrity）；
- T-5/T-6 产物/输入被改 1 字节 ⇒ `ReceiptIntegrityError` 且报出文件；
- T-7 路径逃出 root ⇒ `ReceiptPathError`（拒绝，不静默截断）；
- T-8 时间戳/主机/notes 不入摘要；
- T-9 md 表里的哈希由产物算出，手改一位即可被发现；
- T-10 零第三方依赖；
- T-11 干净目录端到端：两份收据**字节级相同**。

## 一个容易写错的点

T-4 与 T-5 必须**报不同异常**：代码改了是合法情形（重出即可），
内容改了但收据没重出才是问题。合并成「不一致」会让人分不清该做什么。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "runtime" / "receipt.py"
CLI = ROOT / "scripts" / "gen_receipt.py"

sys.path.insert(0, str(ROOT))

from runtime.receipt import (  # noqa: E402
    GeneratorChangedError, ReceiptError, ReceiptFormatError,
    ReceiptIntegrityError, ReceiptPathError, build_receipt, canonical_bytes,
    file_entry, load_receipt, receipt_digest, relative_path, render_markdown,
    verify_receipt, write_receipt,
)

ARTIFACT_TEXT = '{"result": 1.25, "n": 3}\n'


def _fixture(root: Path) -> dict:
    """造一份最小可用的「生成器 + 输入 + 产物」。"""
    (root / "gen").mkdir(parents=True, exist_ok=True)
    (root / "in").mkdir(parents=True, exist_ok=True)
    (root / "out").mkdir(parents=True, exist_ok=True)
    (root / "gen" / "maker.py").write_text(
        "# fixture generator\nprint('hi')\n", encoding="utf-8", newline="\n")
    (root / "in" / "data.txt").write_text("2024-01-02,1.0\n", encoding="utf-8",
                                          newline="\n")
    (root / "out" / "result.json").write_text(ARTIFACT_TEXT, encoding="utf-8",
                                              newline="\n")
    return {
        "generator": root / "gen" / "maker.py",
        "inputs": [root / "in" / "data.txt"],
        "artifacts": [root / "out" / "result.json"],
    }


def _build(root: Path, **over) -> dict:
    f = _fixture(root)
    kwargs = {
        "generator": f["generator"],
        "params": {"horizon": 20, "control": "log_amount_20"},
        "inputs": f["inputs"],
        "artifacts": f["artifacts"],
        "root": root,
    }
    kwargs.update(over)
    return build_receipt(**kwargs)


# --------------------------------------------------------------------------
# T-1 / T-2 / T-3
# --------------------------------------------------------------------------

def test_t1_deterministic(tmp_path):
    """T-1：同输入两次构造 ⇒ 摘要逐位相同。"""
    a = _build(tmp_path)
    b = _build(tmp_path)
    assert a["receipt_sha256"] == b["receipt_sha256"]
    assert a == b


def test_t2_path_independent(tmp_path):
    """T-2：同内容放两个不同绝对路径 ⇒ 摘要相同。"""
    root_a = tmp_path / "alpha_root"
    root_b = tmp_path / "beta_root_deeper"
    da = _build(root_a)
    db = _build(root_b)
    assert da["receipt_sha256"] == db["receipt_sha256"]
    # 摘要相同，且两份收据的条目路径都只有相对形式
    for entry in da["inputs"] + da["artifacts"]:
        assert not Path(entry["path"]).is_absolute()
        assert str(root_a.name) not in entry["path"]


def test_t3_param_order_and_value(tmp_path):
    """T-3：键序无关；值改变 ⇒ 摘要变。"""
    x = _build(tmp_path, params={"a": 1, "b": 2})
    y = _build(tmp_path, params={"b": 2, "a": 1})
    z = _build(tmp_path, params={"a": 1, "b": 3})
    assert x["receipt_sha256"] == y["receipt_sha256"]
    assert x["receipt_sha256"] != z["receipt_sha256"]


# --------------------------------------------------------------------------
# T-4 / T-12 / T-5 / T-6
# --------------------------------------------------------------------------

def test_t4_generator_change_raises_distinct_error(tmp_path):
    """T-4/T-12：生成器源码改 1 字节 ⇒ GeneratorChangedError（非 Integrity）。"""
    receipt = _build(tmp_path)
    gen = tmp_path / "gen" / "maker.py"
    gen.write_text("# fixture generator\nprint('hi')\n# bumped\n",
                   encoding="utf-8", newline="\n")
    with pytest.raises(GeneratorChangedError) as ei:
        verify_receipt(receipt, root=tmp_path)
    assert not isinstance(ei.value, ReceiptIntegrityError)
    # 重出后摘要必须变（T-12）——注意不能走 _build()，它会重建 fixture
    # 把生成器写回原样（本测试第一版就栽在这里）
    fresh = build_receipt(
        generator=gen,
        params={"horizon": 20, "control": "log_amount_20"},
        inputs=[tmp_path / "in" / "data.txt"],
        artifacts=[tmp_path / "out" / "result.json"],
        root=tmp_path,
    )
    assert fresh["receipt_sha256"] != receipt["receipt_sha256"]
    assert verify_receipt(fresh, root=tmp_path)["ok"] is True


def test_t5_artifact_tamper_reports_file(tmp_path):
    """T-5：产物改 1 字节 ⇒ IntegrityError，且报出具体文件。"""
    receipt = _build(tmp_path)
    (tmp_path / "out" / "result.json").write_text(
        '{"result": 1.26, "n": 3}\n', encoding="utf-8", newline="\n")
    with pytest.raises(ReceiptIntegrityError) as ei:
        verify_receipt(receipt, root=tmp_path)
    assert "out/result.json" in str(ei.value)


def test_t6_input_tamper_reports_file(tmp_path):
    """T-6：输入改 1 字节 ⇒ IntegrityError，且报出具体文件。"""
    receipt = _build(tmp_path)
    (tmp_path / "in" / "data.txt").write_text("2024-01-02,2.0\n", encoding="utf-8",
                                              newline="\n")
    with pytest.raises(ReceiptIntegrityError) as ei:
        verify_receipt(receipt, root=tmp_path)
    assert "in/data.txt" in str(ei.value)


def test_t6b_params_tamper_detected(tmp_path):
    """参数被改而收据未重出 ⇒ 摘要自洽性检查抓到（不依赖文件）。"""
    receipt = _build(tmp_path)
    tampered = json.loads(json.dumps(receipt))
    tampered["params"]["horizon"] = 5
    with pytest.raises(ReceiptIntegrityError) as ei:
        verify_receipt(tampered, root=tmp_path)
    assert "摘要与内容不符" in str(ei.value)


# --------------------------------------------------------------------------
# T-7 路径安全
# --------------------------------------------------------------------------

def test_t7_path_escape_rejected(tmp_path):
    """T-7：绝对路径在 root 外 / `..` 越界 ⇒ ReceiptPathError。"""
    outside = tmp_path.parent / "outside_receipt_probe.txt"
    outside.write_text("x", encoding="utf-8")
    root = tmp_path / "root"
    _fixture(root)
    with pytest.raises(ReceiptPathError):
        relative_path(outside, root=root)
    with pytest.raises(ReceiptPathError):
        relative_path("../outside_receipt_probe.txt", root=root)
    # 正常相对路径（含 root 内部的 ..）必须放行
    assert relative_path("in/../in/data.txt", root=root) == "in/data.txt"


# --------------------------------------------------------------------------
# T-8 易变量不入摘要
# --------------------------------------------------------------------------

def test_t8_volatile_fields_not_in_digest(tmp_path):
    """T-8：notes 不进摘要；收据不含时间戳/主机字段。"""
    plain = _build(tmp_path)
    noted = _build(tmp_path, notes="2026-10-18 18:30:00 @ T430 生成")
    assert plain["receipt_sha256"] == noted["receipt_sha256"]
    assert "notes" in noted and "notes" not in plain

    blob = json.dumps({k: v for k, v in noted.items() if k != "notes"},
                      ensure_ascii=False)
    for banned in ("generated_at", "timestamp", "mtime", "ctime", "hostname",
                   "user", "argv", "pid"):
        assert banned not in blob, f"易变量进了收据: {banned}"


def test_t8b_canonical_bytes_is_order_stable():
    """规范字节：键序不影响；分隔符写死（历史踩过分隔符差一空格）。"""
    a = canonical_bytes({"b": 1, "a": [2, 3]})
    b = canonical_bytes({"a": [2, 3], "b": 1})
    assert a == b == b'{"a":[2,3],"b":1}'


# --------------------------------------------------------------------------
# T-9 文档哈希可复算
# --------------------------------------------------------------------------

def test_t9_markdown_hashes_are_computable(tmp_path):
    """T-9：md 表内每个 sha256 == 重算值；手改一位即可被发现。"""
    receipt = _build(tmp_path)
    md = render_markdown(receipt)
    listed = dict(re.findall(r"\| `([^`]+)` \| \d+ \| `([0-9a-f]{64})` \|", md))
    assert listed, "md 表里没解析出哈希行"
    for rel, digest in listed.items():
        assert file_entry(rel, root=tmp_path)["sha256"] == digest, rel

    # 手改一位 ⇒ 与重算值不符（守卫的判据就是这条）
    tampered = md.replace(sorted(listed.values())[0],
                          "0" * 64, 1)
    re_listed = dict(re.findall(r"\| `([^`]+)` \| \d+ \| `([0-9a-f]{64})` \|",
                                tampered))
    changed = [k for k, v in re_listed.items() if listed[k] != v]
    assert len(changed) == 1, "手改未能在重算中暴露"


# --------------------------------------------------------------------------
# T-10 零第三方依赖
# --------------------------------------------------------------------------

def test_t10_no_third_party_imports():
    """T-10：模块不得 import numpy/pandas/arch/scipy/statsmodels。"""
    text = MODULE.read_text(encoding="utf-8")
    for banned in ("numpy", "pandas", "arch", "scipy", "statsmodels"):
        assert f"import {banned}" not in text, f"发现第三方依赖 {banned}"


# --------------------------------------------------------------------------
# T-11 干净目录端到端（走 CLI，两套不同绝对路径）
# --------------------------------------------------------------------------

def _run_cli(root: Path, out: Path, md_out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI),
         "--generator", str(root / "gen" / "maker.py"),
         "--param", "horizon=20", "--param", "flag=true",
         "--input", str(root / "in" / "data.txt"),
         "--artifact", str(root / "out" / "result.json"),
         "--root", str(root),
         "--out", str(out), "--md-out", str(md_out), "--verify"],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(ROOT), check=False)


def test_t11_clean_dirs_byte_identical(tmp_path):
    """T-11：两个不同绝对路径各跑一次 CLI ⇒ 两份收据**字节级相同**。"""
    root_a = tmp_path / "clean_a"
    root_b = tmp_path / "clean_b" / "nested"
    _fixture(root_a)
    _fixture(root_b)
    ra = _run_cli(root_a, tmp_path / "ra.json", tmp_path / "ra.md")
    rb = _run_cli(root_b, tmp_path / "rb.json", tmp_path / "rb.md")
    assert ra.returncode == 0, ra.stderr
    assert rb.returncode == 0, rb.stderr
    assert (tmp_path / "ra.json").read_bytes() == (tmp_path / "rb.json").read_bytes()
    assert (tmp_path / "ra.md").read_bytes() == (tmp_path / "rb.md").read_bytes()


def test_t11b_cli_refuses_escape(tmp_path):
    """CLI 侧也要拒绝越界路径（不能只在库里拦）。"""
    root = tmp_path / "root"
    _fixture(root)
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    proc = _run_cli(root, tmp_path / "r.json", tmp_path / "r.md")
    assert proc.returncode == 0
    proc2 = subprocess.run(
        [sys.executable, str(CLI),
         "--generator", str(root / "gen" / "maker.py"),
         "--input", str(outside),
         "--root", str(root),
         "--out", str(tmp_path / "bad.json")],
        capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT), check=False)
    assert proc2.returncode != 0
    assert "ReceiptPathError" in (proc2.stderr + proc2.stdout)


def test_t11c_generator_payload_has_no_wallclock():
    """T-11 前置条件：T-11 的生成器产物里不得有墙钟字段。

    `elapsed_sec` 会让「干净目录重跑字节级相同」永远不成立——
    本立项实测就是先撞上它（两次运行唯一差异 26.8 / 25.6）。
    这是**前置条件**而非风格问题：墙钟进产物 ⇒ T-11 不可能通过。
    """
    text = (ROOT / "scripts" / "run_fundamental_factor_study.py").read_text(
        encoding="utf-8")
    assert '"elapsed_sec"' not in text, (
        "T-11 生成器把墙钟写进了产物；诊断信息应走 stdout，不进产物")


# --------------------------------------------------------------------------
# 落盘 / 读回 / 结构校验
# --------------------------------------------------------------------------

def test_roundtrip_and_format_errors(tmp_path):
    """write→load 往返一致；缺键 / 未知 schema ⇒ ReceiptFormatError。"""
    receipt = _build(tmp_path)
    path = tmp_path / "receipt.json"
    write_receipt(receipt, path)
    assert path.read_bytes().endswith(b"\n")
    assert load_receipt(path) == receipt

    broken = json.loads(json.dumps(receipt))
    broken.pop("artifacts")
    path2 = tmp_path / "broken.json"
    path2.write_text(json.dumps(broken), encoding="utf-8", newline="\n")
    with pytest.raises(ReceiptFormatError):
        load_receipt(path2)

    bad_schema = json.loads(json.dumps(receipt))
    bad_schema["schema"] = 99
    path3 = tmp_path / "schema.json"
    path3.write_text(json.dumps(bad_schema), encoding="utf-8", newline="\n")
    with pytest.raises(ReceiptFormatError):
        load_receipt(path3)


def test_duplicate_file_and_missing_file(tmp_path):
    """重复文件 ⇒ ReceiptError；缺文件 ⇒ FileNotFoundError（不伪造空哈希）。"""
    f = _fixture(tmp_path)
    with pytest.raises(ReceiptError):
        build_receipt(generator=f["generator"], root=tmp_path,
                      inputs=[f["inputs"][0], f["inputs"][0]])
    with pytest.raises(FileNotFoundError):
        file_entry("in/nope.txt", root=tmp_path)


def test_digest_is_self_excluding(tmp_path):
    """摘要不自我指涉：改 receipt_sha256 字段本身不改重算值。"""
    receipt = _build(tmp_path)
    copy = json.loads(json.dumps(receipt))
    copy["receipt_sha256"] = "0" * 64
    assert receipt_digest(copy) == receipt["receipt_sha256"]
