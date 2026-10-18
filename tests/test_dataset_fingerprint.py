# -*- coding: utf-8 -*-
"""数据集指纹守卫（DATA_CHANNEL_PREREG 组件 A，判据 F 组）。

## 锁住什么

归档产物必须能自证「重跑 = 同一数据集」。此前产物无 md5 / 无行数，
「数据大概没变」只能靠人记 —— 而 `disclosure_dates.jsonl` 已经发生过
一次静默漂移（176,841 → 176,830 行，7 条从真实披露日退回法定截止日，
见 `DSR_IC_FAMILY_VERDICT.md` §五）。

本文件锁住：md5/行数/字节数的正确性、内容变更可检出、缺失不补造、
确定性，以及「接入只增一个键」。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fetch.fingerprint import CHUNK_SIZE, fingerprint_datasets, fingerprint_file

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "run_fundamental_factor_study.py"
ARCHIVED_OUTPUT = ROOT / "reports" / "v3_fundamental_factor_study.json"


def _write(p: Path, text: str) -> Path:
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


# ---------------------------------------------------------------------------
# F-1 正确性
# ---------------------------------------------------------------------------

def test_f1_matches_hashlib_and_size(tmp_path):
    """md5 / bytes / lines 与独立实现逐位一致（F-1）。"""
    content = ("a,b\n" * 5000) + "tail-without-newline"
    p = _write(tmp_path / "f.jsonl", content)
    fp = fingerprint_file(p)
    assert fp["md5"] == hashlib.md5(p.read_bytes()).hexdigest()
    assert fp["bytes"] == len(content.encode("utf-8"))
    # 5000 个换行 + 末行无换行补 1 = 5001
    assert fp["lines"] == 5001


def test_f1_lines_matches_wc_l_convention(tmp_path):
    """两种行尾形态：有/无末行换行，行数都与 wc -l 口径一致（F-1）。"""
    with_nl = _write(tmp_path / "with_nl.txt", "x\ny\nz\n")
    without_nl = _write(tmp_path / "without_nl.txt", "x\ny\nz")
    assert fingerprint_file(with_nl)["lines"] == 3
    assert fingerprint_file(without_nl)["lines"] == 3  # 末行补 1


def test_f1_chunk_boundary_does_not_change_result(tmp_path):
    """分块大小只影响 IO 次数，不影响结果（F-1/F-4）：构造跨块内容。"""
    line = "0123456789abcdef" * 64  # 1024 B，正好半个块
    content = (line + "\n") * (CHUNK_SIZE // 1024 + 3)  # 跨过 1 MiB 边界
    p = _write(tmp_path / "big.txt", content)
    fp = fingerprint_file(p)
    assert fp["md5"] == hashlib.md5(p.read_bytes()).hexdigest()
    assert fp["lines"] == content.count("\n")


# ---------------------------------------------------------------------------
# F-2 内容变更可检出（阳性对照）
# ---------------------------------------------------------------------------

def test_f2_byte_change_changes_md5(tmp_path):
    """改一个字节 ⇒ md5 变（F-2）。行数不变（同行长替换）。"""
    p = _write(tmp_path / "f.txt", "a\nb\nc\n")
    before = fingerprint_file(p)
    _write(p, "a\nX\nc\n")
    after = fingerprint_file(p)
    assert after["md5"] != before["md5"]
    assert after["lines"] == before["lines"] == 3


def test_f2_line_added_changes_lines_and_md5(tmp_path):
    """加一行 ⇒ 行数 +1 且 md5 变（F-2）。"""
    p = _write(tmp_path / "f.txt", "a\nb\n")
    before = fingerprint_file(p)
    _write(p, "a\nb\nc\n")
    after = fingerprint_file(p)
    assert after["lines"] == before["lines"] + 1
    assert after["md5"] != before["md5"]


# ---------------------------------------------------------------------------
# F-3 缺失即缺失
# ---------------------------------------------------------------------------

def test_f3_optional_missing_records_missing_flag(tmp_path):
    """可选文件缺失 ⇒ {"missing": True}，不得出现伪造的 md5/lines（F-3）。"""
    fp = fingerprint_file(tmp_path / "nope.jsonl", required=False)
    assert fp.get("missing") is True
    assert "md5" not in fp and "lines" not in fp


def test_f3_required_missing_raises(tmp_path):
    """必需文件缺失 ⇒ FileNotFoundError，不返回空指纹（F-3）。"""
    with pytest.raises(FileNotFoundError, match="指纹目标不存在"):
        fingerprint_file(tmp_path / "nope.jsonl")


# ---------------------------------------------------------------------------
# F-4 确定性
# ---------------------------------------------------------------------------

def test_f4_deterministic_and_no_clock_fields(tmp_path):
    """同文件两次调用逐位相同；字段集固定（无时钟/主机/随机项）（F-4）。"""
    p = _write(tmp_path / "f.txt", "a\nb\n")
    a, b = fingerprint_file(p), fingerprint_file(p)
    assert a == b
    assert set(a) == {"path", "bytes", "lines", "md5"}


def test_fingerprint_datasets_mixed_required(tmp_path):
    """批量接口：按名指定 required；键序 = 传入序（产物可比对）。"""
    need = _write(tmp_path / "need.jsonl", "x\n")
    got = fingerprint_datasets(
        {"fundamentals": need, "disclosure_dates": tmp_path / "opt.jsonl"},
        required={"fundamentals": True, "disclosure_dates": False})
    assert list(got) == ["fundamentals", "disclosure_dates"]
    assert got["fundamentals"]["md5"] == hashlib.md5(b"x\n").hexdigest()
    assert got["disclosure_dates"] == {"path": "disclosure_dates", "missing": True}


# ---------------------------------------------------------------------------
# F-5 只增键
# ---------------------------------------------------------------------------

def _payload_keys_from_source() -> list:
    """从脚本源码用 AST 提取 `payload = {...}` 的顶层键。

    不用正则：一行里可能有第二个键（如 `"args": vars(args), "elapsed_sec": ...`），
    行首锚定会漏；而块内还有嵌套 dict 的字面量键，全文匹配会多。
    AST 只认**赋值目标为 payload 的那个 dict 的字面量顶层键**。
    """
    import ast
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "payload" for t in node.targets):
            value = node.value
            assert isinstance(value, ast.Dict), "payload 不是 dict 字面量"
            return [k.value for k in value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    raise AssertionError("脚本中未找到 payload 赋值")


#: 已**刻意移除**的归档键（不是丢失）。`elapsed_sec` 于 2026-10-18 由 RECEIPT
#: 立项删除：墙钟写进产物使「干净目录重跑字节级相同」永远不成立（A7 判据 T-11），
#: 实测两次运行唯一差异就是它。耗时仍由 stdout 打印 `用时 Ns`，不进产物。
#: 登记为缺陷 #19（HANDOVER）。此处**白名单化**而非放宽断言：删任何一个别的键仍红。
RETIRED_KEYS = {"elapsed_sec"}


def test_f5_payload_keys_are_archived_plus_fingerprint():
    """接入后 payload 顶层键 = 归档产物的键 + 且仅 + dataset_fingerprint（F-5）。

    归档产物 `reports/v3_fundamental_factor_study.json` 是接入前的真实输出
    （18 键）。本测试防「顺手改口径」：除了新增指纹键，一个键都不许动。
    `RETIRED_KEYS` 是**显式登记**的例外（每个都要有理由与被引用的缺陷号）。
    """
    if not ARCHIVED_OUTPUT.exists():  # pragma: no cover - 归档产物在仓库内
        pytest.skip("归档产物缺失（应随仓库分发）")
    archived = set(json.loads(ARCHIVED_OUTPUT.read_text(encoding="utf-8")))
    current = set(_payload_keys_from_source())
    assert current - archived == {"dataset_fingerprint"}, (
        f"payload 新增了非指纹键：{sorted(current - archived)}")
    assert archived - current == RETIRED_KEYS, (
        f"payload 丢了未登记的归档键：{sorted((archived - current) - RETIRED_KEYS)}")


def test_f5_retired_keys_stay_retired():
    """`elapsed_sec` 不许被「顺手加回来」——加回来就破坏 A7 的 T-11。"""
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"elapsed_sec"' not in text, (
        "墙钟回到产物会让「干净目录重跑字节级相同」失效（缺陷 #19）")


def test_f5_fingerprint_wired_once():
    """指纹接入点唯一且带 required 区分（F-5）：必需财务表、可选披露表。"""
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.count('"dataset_fingerprint": ds_fp,') == 1
    assert "fingerprint_datasets(" in text
    assert '"fundamentals": True' in text
    assert '"disclosure_dates": False' in text
