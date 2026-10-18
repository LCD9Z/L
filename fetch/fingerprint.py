# -*- coding: utf-8 -*-
"""数据集指纹：一次 md5 + 行数 + 字节数，让产物自证「重跑 = 同一数据集」。

## 为什么必须有这一层

归档产物此前**没有任何数据集指纹**（无 md5 / 无行数 / 无版本），
所以「重跑 = 同一数据集」这件事无法从产物自证，只能靠人记得
「数据大概没变」。实测已经发生过一次静默漂移：
`D:/tdx_dataset_v3/disclosure_dates.jsonl` 归档 176,841 条 → 重跑时
176,830 行，其中 7 条从「真实披露日」退回「法定截止日」
（见 `DSR_IC_FAMILY_VERDICT.md` §五）。因子统计量在归档精度下未变，
但**没有指纹的话，读者无从判断两次跑的到底是不是同一份数据**。

这与 `GITHUB_ASHARE_QUANT_SURVEY.md` §8.3-① 从 `microalpha` 抓到的
「收据绑生成器版本」是同一族问题：**可复现性需要指纹，
否则会退化成「看起来可复现」**。

## 设计约束

* **一次 md5**：流式分块读，不把整文件读进内存（`fundamentals.jsonl` 120 MB，
  本机 7.8 GB，但核心管道按「8 GB 机器可跑」设计）。
* **缺失即缺失**：可选文件缺失时记 `{"missing": True}`，不补造空指纹；
  必需文件缺失时抛 `FileNotFoundError` —— 诚实失败，不返回空表冒充
  「该文件为空」。
* **无时钟 / 无主机 / 无随机项**：同一文件两次调用结果逐位相同。
  指纹描述的是**文件内容**，不是「什么时候跑的」。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Optional, Union

__all__ = ["CHUNK_SIZE", "fingerprint_datasets", "fingerprint_file"]

#: 流式读取分块大小（1 MiB）。太小则 IO 次数多，太大则内存峰值高。
CHUNK_SIZE = 1024 * 1024


def fingerprint_file(path: Union[str, Path], *, required: bool = True,
                     name: Optional[str] = None) -> Dict[str, Any]:
    """返回单个文件的指纹 ``{path, bytes, lines, md5}``。

    参数
    ----
    path:
        文件路径。
    required:
        ``True``（默认）时文件缺失抛 :class:`FileNotFoundError`；
        ``False`` 时返回 ``{"path": ..., "missing": True}``
        —— 供**可选**输入（如披露日表缺失时 PIT 自动退口径）自证
        「本次没有该文件的指纹」，而不是伪造一个空文件的指纹。
    name:
        覆盖 ``path`` 字段的显示名（如 ``"fundamentals"``）。

    ``lines`` 口径与 ``wc -l`` 一致：换行符计数，末行无换行时 +1。
    """
    p = Path(path)
    label = name if name is not None else str(p)
    if not p.is_file():
        if required:
            raise FileNotFoundError(f"指纹目标不存在：{p}")
        return {"path": label, "missing": True}
    md5 = hashlib.md5()
    size = 0
    lines = 0
    with p.open("rb") as fh:
        while True:
            chunk = fh.read(CHUNK_SIZE)
            if not chunk:
                break
            md5.update(chunk)
            size += len(chunk)
            lines += chunk.count(b"\n")
    # 末行无换行符时补 1（与 wc -l 的差别只在这一点，须显式处理）
    with p.open("rb") as fh:
        fh.seek(max(0, size - 1))
        if size and fh.read(1) != b"\n":
            lines += 1
    return {"path": label, "bytes": size, "lines": lines, "md5": md5.hexdigest()}


def fingerprint_datasets(files: Dict[str, Union[str, Path]], *,
                         required: Union[bool, Dict[str, bool]] = True
                         ) -> Dict[str, Dict[str, Any]]:
    """批量指纹：``{"fundamentals": {...}, "disclosure_dates": {...}}``。

    ``required`` 可传 dict 按名指定（如披露日表可选、财务表必需）。
    键的顺序即传入顺序 —— 产物 JSON 的键序由此确定，保证可复现比对。
    """
    if isinstance(required, dict):
        req_of = {k: bool(required.get(k, True)) for k in files}
    else:
        req_of = {k: bool(required) for k in files}
    return {name: fingerprint_file(path, required=req_of[name], name=name)
            for name, path in files.items()}
