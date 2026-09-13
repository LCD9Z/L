"""tushare_provider 测试。

关键约定：**本文件不依赖可选依赖 pandas**。
原版测试直接构造 pandas.DataFrame，导致该文件被 pytest.ini 用
`--ignore` 排除，模块实际处于零自动化覆盖状态。

现改为：
  · 用一个最小 DataFrame 替身驱动纯逻辑（指纹、落盘、哈希、降级分支）
  · 若环境装有 pandas，再用 `pytest.importorskip` 追加跑一遍真实 DataFrame
这样无论 pandas 是否安装，模块逻辑都始终被覆盖。
"""
import builtins
import hashlib
from pathlib import Path

import pytest

from tushare.tushare_provider import TuShareProvider, TuShareProviderError


class FakeDataFrame:
    """pandas.DataFrame 的最小替身，仅实现 tushare_provider 用到的接口。

    它是「接口替身」而非「字节级复制」：CSV 的具体字节与 pandas 不完全相同，
    但模块本身不依赖这一点（见文件末尾的真实 pandas 测试）。
    """

    def __init__(self, columns, rows):
        self.columns = list(columns)
        self.rows = [list(r) for r in rows]

    def __len__(self):
        return len(self.rows)

    def to_csv(self, path_or_buf=None, index=False):
        assert index is False, "本替身仅支持 index=False（与调用方一致）"
        lines = [",".join(self.columns)]
        lines.extend(",".join("" if v is None else str(v) for v in r) for r in self.rows)
        text = "\n".join(lines) + "\n"
        if path_or_buf is None:
            return text
        Path(path_or_buf).write_text(text, encoding="utf-8")
        return None


def _df():
    return FakeDataFrame(["trade_date", "close"], [["20240102", 10.0]])


# --- 凭据 ---------------------------------------------------------------

def test_missing_token_rejected(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    with pytest.raises(TuShareProviderError):
        TuShareProvider()


def test_blank_token_rejected(monkeypatch):
    """只有空白的 token 同样应被拒绝（strip 后为空）。"""
    monkeypatch.setenv("TUSHARE_TOKEN", "   ")
    with pytest.raises(TuShareProviderError):
        TuShareProvider()


def test_explicit_token_wins_over_environment(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "from-env")
    assert TuShareProvider("from-arg").token == "from-arg"


# --- 指纹 ---------------------------------------------------------------

def test_dataframe_fingerprint_is_deterministic():
    assert TuShareProvider.fingerprint_dataframe(_df()) == TuShareProvider.fingerprint_dataframe(_df())


def test_fingerprint_changes_with_content():
    """内容不同则指纹必须不同，否则下游无法用它做数据比对。"""
    other = FakeDataFrame(["trade_date", "close"], [["20240102", 11.0]])
    assert TuShareProvider.fingerprint_dataframe(_df()) != TuShareProvider.fingerprint_dataframe(other)


def test_fingerprint_is_sha256_hex():
    assert len(TuShareProvider.fingerprint_dataframe(_df())) == 64


# --- 落盘与元数据 -------------------------------------------------------

def test_dataset_metadata_and_hash(tmp_path):
    obj = TuShareProvider.__new__(TuShareProvider)
    r = obj.save_dataset(_df(), tmp_path / "x.csv", {"source": "tushare", "point_in_time": True})

    assert r["rows"] == 1 and len(r["sha256"]) == 64
    assert r["source"] == "tushare" and r["point_in_time"] is True
    assert Path(r["path"]).exists()
    # 元数据里的 sha256 必须与实际落盘文件一致（不得与文件脱节）
    assert hashlib.sha256(Path(r["path"]).read_bytes()).hexdigest() == r["sha256"]


def test_save_dataset_creates_parent_directories(tmp_path):
    obj = TuShareProvider.__new__(TuShareProvider)
    target = tmp_path / "a" / "b" / "x.csv"
    r = obj.save_dataset(_df(), target, {})
    assert Path(r["path"]).exists()
    assert (tmp_path / "a" / "b" / "x.csv.metadata.json").exists()


def test_save_dataset_metadata_is_written_as_readable_json(tmp_path):
    import json

    obj = TuShareProvider.__new__(TuShareProvider)
    r = obj.save_dataset(_df(), tmp_path / "x.csv", {"note": "中文元数据"})
    meta = json.loads((tmp_path / "x.csv.metadata.json").read_text(encoding="utf-8"))
    assert meta["note"] == "中文元数据"
    assert meta["path"] == r["path"]


# --- 降级分支 -----------------------------------------------------------

def _provider_with_client(client):
    obj = TuShareProvider.__new__(TuShareProvider)
    obj.token = "x"
    obj._pro = client
    return obj


def test_client_raises_when_tushare_not_installed(monkeypatch):
    """tushare 未安装时必须给出明确错误，而非静默返回空数据。"""
    obj = _provider_with_client(None)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "tushare":
            raise ImportError("no tushare")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(TuShareProviderError):
        obj._client()


def test_probe_reports_failure_instead_of_raising():
    """probe 应把异常转成 ok=False 的结果，而不是向上抛。"""

    class Boom:
        def stock_basic(self, **kwargs):
            raise RuntimeError("network down")

    res = _provider_with_client(Boom()).probe()
    assert res.ok is False
    assert res.rows == 0
    assert "network down" in res.message


def test_probe_success_reports_row_count():
    class Ok:
        def stock_basic(self, **kwargs):
            return FakeDataFrame(["ts_code"], [["600000.SH"], ["000001.SZ"]])

    res = _provider_with_client(Ok()).probe()
    assert res.ok is True and res.rows == 2


def test_daily_passes_arguments_through():
    seen = {}

    class Client:
        def daily(self, **kwargs):
            seen.update(kwargs)
            return "df"

    assert _provider_with_client(Client()).daily("600000.SH", "20240101", "20240131") == "df"
    assert seen == {"ts_code": "600000.SH", "start_date": "20240101", "end_date": "20240131"}


# --- 真实 pandas（可选依赖，装了就一并验证模块在其上可用） ---------------

def test_real_pandas_dataframe_is_supported(tmp_path):
    """装有 pandas 时用真实 DataFrame 端到端跑一遍。

    注意：这里**不比对替身与 pandas 的字节输出**。tushare_provider 把 DataFrame
    当作不透明对象，只依赖 `to_csv(index=False)` 与 `len()`；CSV 的具体字节
    （换行符、浮点格式）随 pandas 版本与平台变化，不属于模块契约。
    因此只断言「相同数据 → 相同指纹」与「元数据与落盘文件自洽」。
    """
    pd = pytest.importorskip("pandas", reason="pandas 为可选依赖，未安装时跳过")

    def real_df():
        return pd.DataFrame({"trade_date": ["20240102"], "close": [10.0]})

    fp = TuShareProvider.fingerprint_dataframe(real_df())
    assert len(fp) == 64
    assert fp == TuShareProvider.fingerprint_dataframe(real_df())

    obj = TuShareProvider.__new__(TuShareProvider)
    r = obj.save_dataset(real_df(), tmp_path / "real.csv", {"source": "tushare"})
    assert r["rows"] == 1 and len(r["sha256"]) == 64
    assert hashlib.sha256(Path(r["path"]).read_bytes()).hexdigest() == r["sha256"]
