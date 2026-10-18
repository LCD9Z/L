# -*- coding: utf-8 -*-
"""收据（receipt）：把「输入 + 生成器 + 参数 + 全部产物」一起哈希。

回答一个和数据集指纹不同的问题：**「这份产物，是不是由这份代码 + 这批数据 +
这组参数跑出来的」**。`fetch/fingerprint.py` 只回答「数据集有没有变」；
本模块回答「**整条链**有没有变」。

## 三条口径（A7 的硬要求，逐条对应 survey §8.4-A7）

1. **覆盖全链**：摘要覆盖 `{generator, params, inputs[], artifacts[]}`，
   任一环节变一个字节，摘要就变。
2. **排除易变量**：时间戳、主机名、用户名、argv、绝对路径
   **都不进摘要**（默认也不存储）；`notes` 存但不进摘要，
   `verify` 会明示它未被校验。时间戳一旦进摘要，「干净目录重跑字节级相同」
   就永远做不到——A7 的第 ① 条验收直接失效。
3. **版本由源码算出**：`generator.sha256` 是**生成器源码的哈希**，不是手写
   版本号。survey §8.3-① 的反例正是「手写 `version 0.2.0` 与代码不同步」；
   源码哈希不可能不同步。手写版本串只许进 `notes`（展示用）。

## 与既有实践的关系

- `scripts/gen_evidence_index.py` 的 sha256：只覆盖结果文件 ⇒ 本模块**取代不了它**
  （那是给人核对的清单），两者并存。
- 聚合 md5（`md5sum -b … | md5sum`）：口径在命令行习惯里，不可自证
  （历史上因 GNU `-b` 在文件名前多一个 `*` 而 5 种复现法全败）。
  本模块把口径**写进代码**，`canonical_bytes` 是唯一入口。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

#: 收据格式版本（结构变更才动它；与生成器版本无关）
SCHEMA = 1

#: 不进摘要的顶层键
_VOLATILE_KEYS = ("receipt_sha256", "notes")


class ReceiptError(ValueError):
    """收据构造或校验失败。"""


class ReceiptPathError(ReceiptError):
    """路径逃出 root（绝对路径在 root 外、或 `..` 越界）。"""


class ReceiptFormatError(ReceiptError):
    """收据结构不合法（缺键 / 类型不符 / schema 不认识）。"""


class ReceiptIntegrityError(ReceiptError):
    """内容与收据不符（产物或输入被改、参数被改、摘要对不上）。"""


class GeneratorChangedError(ReceiptError):
    """生成器源码已变 ⇒ 旧收据失效，必须重出。

    刻意与 :class:`ReceiptIntegrityError` 分开：前者是「代码改了」（合法情形，
    重出即可），后者是「内容被改了但收据没重出」（是问题）。
    """


# --------------------------------------------------------------------------
# 规范字节
# --------------------------------------------------------------------------

def canonical_bytes(obj: Any) -> bytes:
    """规范化 JSON 字节：键排序、无多余空白、UTF-8。

    这是摘要的**唯一**入口——任何「自己拼字符串再 sha256」的写法都不可接受，
    因为分隔符差一个空格就会得到不同哈希（项目里真发生过）。
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    """字节内容的 sha256（十六进制小写）。"""
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Any) -> str:
    """文件内容的 sha256（流式分块，不整文件进内存）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# 路径归一
# --------------------------------------------------------------------------

def relative_path(path: Any, *, root: Any) -> str:
    """把路径归一成「相对 root、`/` 分隔」的形式；越界即抛错。

    不做静默截断：逃出 root 的路径**一定是调用方写错了**，
    悄悄改成别的名字会让收据指向一个不存在的文件，比报错更坏。
    """
    raw = os.fspath(path)
    root_abs = os.path.abspath(os.fspath(root))
    target = raw if os.path.isabs(raw) else os.path.join(root_abs, raw)
    target = os.path.abspath(target)
    try:
        common = os.path.commonpath([target, root_abs])
    except ValueError as exc:  # 不同盘符（Windows）
        raise ReceiptPathError(
            f"路径与 root 不在同一盘: {raw!r}") from exc
    if os.path.normcase(common) != os.path.normcase(root_abs):
        raise ReceiptPathError(
            f"路径逃出 root: {raw!r}（root={root_abs!r}）")
    return os.path.relpath(target, root_abs).replace(os.sep, "/")


def file_entry(path: Any, *, root: Any) -> Dict[str, Any]:
    """单个文件的收据条目 ``{path, bytes, sha256}``。

    文件不存在 ⇒ :class:`FileNotFoundError`（缺失即缺失，不伪造空哈希）。
    """
    rel = relative_path(path, root=root)
    full = os.path.join(os.path.abspath(os.fspath(root)), rel.replace("/", os.sep))
    if not os.path.isfile(full):
        raise FileNotFoundError(f"收据要覆盖的文件不存在: {rel}")
    return {
        "path": rel,
        "bytes": os.path.getsize(full),
        "sha256": sha256_file(full),
    }


def _entries(paths: Iterable[Any], *, root: Any) -> List[Dict[str, Any]]:
    entries = [file_entry(p, root=root) for p in paths]
    seen = set()
    for e in entries:
        if e["path"] in seen:
            raise ReceiptError(f"重复文件: {e['path']}")
        seen.add(e["path"])
    entries.sort(key=lambda e: e["path"])
    return entries


# --------------------------------------------------------------------------
# 构造 / 摘要
# --------------------------------------------------------------------------

def _payload(receipt: Mapping[str, Any]) -> Dict[str, Any]:
    """取「进摘要的部分」：去掉 `receipt_sha256` 与 `notes`。"""
    return {k: v for k, v in receipt.items() if k not in _VOLATILE_KEYS}


def receipt_digest(receipt: Mapping[str, Any]) -> str:
    """对收据的**可摘要部分**重算 sha256（不含自指字段与 notes）。"""
    return sha256_bytes(canonical_bytes(_payload(receipt)))


def build_receipt(*,
                  generator: Any,
                  params: Optional[Mapping[str, Any]] = None,
                  inputs: Sequence[Any] = (),
                  artifacts: Sequence[Any] = (),
                  root: Any,
                  notes: Optional[str] = None) -> Dict[str, Any]:
    """构造收据。

    ``generator`` 是**生成器源码文件**路径（不是模块名）：
    版本由它的内容算出。``params`` 只放影响产物的参数（不许塞 argv / 路径）。
    """
    gen = file_entry(generator, root=root)
    receipt: Dict[str, Any] = {
        "schema": SCHEMA,
        "generator": {"path": gen["path"], "sha256": gen["sha256"]},
        "params": dict(params or {}),
        "inputs": _entries(inputs, root=root),
        "artifacts": _entries(artifacts, root=root),
    }
    receipt["receipt_sha256"] = receipt_digest(receipt)
    if notes is not None:
        receipt["notes"] = notes
    return receipt


# --------------------------------------------------------------------------
# 落盘 / 读回 / 校验
# --------------------------------------------------------------------------

def write_receipt(receipt: Mapping[str, Any], path: Any) -> None:
    """落盘：UTF-8、无 BOM、`\\n` 换行、键排序 + 缩进（可 diff）。"""
    text = json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False)
    out = Path(os.fspath(path))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8", newline="\n")


def load_receipt(path: Any) -> Dict[str, Any]:
    """读回收据并做**结构**校验（内容校验走 :func:`verify_receipt`）。"""
    raw = Path(os.fspath(path)).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReceiptFormatError(f"收据不是合法 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ReceiptFormatError("收据顶层必须是对象")
    for key, typ in (("schema", int), ("generator", dict), ("params", dict),
                     ("inputs", list), ("artifacts", list),
                     ("receipt_sha256", str)):
        if key not in data:
            raise ReceiptFormatError(f"收据缺字段: {key}")
        if not isinstance(data[key], typ):
            raise ReceiptFormatError(f"字段类型不符: {key} 应为 {typ.__name__}")
    if data["schema"] != SCHEMA:
        raise ReceiptFormatError(
            f"未知收据 schema: {data['schema']}（本实现支持 {SCHEMA}）")
    for field in ("path", "sha256"):
        if field not in data["generator"]:
            raise ReceiptFormatError(f"generator 缺字段: {field}")
    return data


def verify_receipt(receipt: Mapping[str, Any], *, root: Any) -> Dict[str, Any]:
    """校验收据：先验自洽，再验文件，最后验生成器。

    顺序是刻意的：**先查「收据有没有被改」**（摘要与内容不符），
    再查「文件有没有被改」，最后查「代码有没有改」——
    三类问题报三种异常，绝不合并成一句「不一致」。
    """
    if not isinstance(receipt, dict):
        raise ReceiptFormatError("收据顶层必须是对象")
    if receipt.get("receipt_sha256") != receipt_digest(receipt):
        raise ReceiptIntegrityError(
            "收据摘要与内容不符（params/generator/input 列表被改过但未重出）")

    mismatched: List[str] = []
    checked = {"inputs": 0, "artifacts": 0}
    for kind in ("inputs", "artifacts"):
        for entry in receipt.get(kind, []):
            current = file_entry(entry.get("path", ""), root=root)
            checked[kind] += 1
            if current["sha256"] != entry.get("sha256"):
                mismatched.append(f"{kind}: {current['path']}")
            elif current["bytes"] != entry.get("bytes"):
                mismatched.append(f"{kind}: {current['path']}（字节数变）")
    if mismatched:
        raise ReceiptIntegrityError(
            "以下文件与收据不符:\n  " + "\n  ".join(mismatched))

    gen = receipt.get("generator", {})
    current_gen = file_entry(gen.get("path", ""), root=root)
    if current_gen["sha256"] != gen.get("sha256"):
        raise GeneratorChangedError(
            f"生成器源码已变（{gen.get('path')}）：旧收据失效，必须重出")

    return {
        "ok": True,
        "checked_inputs": checked["inputs"],
        "checked_artifacts": checked["artifacts"],
        "notes_verified": False,  # notes 不进摘要，必须明示
    }


# --------------------------------------------------------------------------
# 人读渲染
# --------------------------------------------------------------------------

def render_markdown(receipt: Mapping[str, Any]) -> str:
    """生成人读表格。

    表里的 sha256 **全部来自条目本身**（``file_entry`` 算出），
    不接受调用方传入手写值——A7 第 ③ 条验收就锁在这里。
    """
    gen = receipt.get("generator", {})
    lines = [
        f"# 收据 `{str(receipt.get('receipt_sha256', ''))[:16]}…`",
        "",
        f"- schema：`{receipt.get('schema')}`",
        f"- 生成器：`{gen.get('path')}`",
        f"- 生成器源码 sha256：`{gen.get('sha256')}`",
        f"- 参数：`{json.dumps(receipt.get('params', {}), sort_keys=True, ensure_ascii=False)}`",
        "",
    ]
    for kind, title in (("inputs", "输入"), ("artifacts", "产物")):
        rows = receipt.get(kind, [])
        lines.append(f"## {title}（{len(rows)} 份）")
        lines.append("")
        lines.append("| 文件 | 字节 | sha256 |")
        lines.append("|---|---|---|")
        for entry in rows:
            lines.append(
                f"| `{entry.get('path')}` | {entry.get('bytes')} | `{entry.get('sha256')}` |")
        lines.append("")
    lines.append(f"**receipt_sha256** = `{receipt.get('receipt_sha256')}`")
    return "\n".join(lines) + "\n"
