# -*- coding: utf-8 -*-
"""A6 数据契约字段守卫（EVIDENCE_CHAIN_PREREG 组件 A6，判据 C 组）。

## 锁住什么

1. **向后兼容**（C-1）：既有构造点不传新字段可正常构造，`to_dict` 滤 None 的
   既有语义不变（新字段默认 None ⇒ 不出现在 dict）；
2. **缺字段即失败**（C-2）：`register_source` 对三个契约字段各缺一次抛
   `IncompleteContractError`；空串/纯空格同样抛；重复注册抛 `ContractError`；
3. **注册非空**（C-3）：本轮注册的三个源字段全非空，且 `null_policy` 含
   代码依据关键词（与 `pit_fundamentals` / `disclosure_eastmoney` 的行为对应）；
4. **遗产显式**（C-4）：`LEGACY_SOURCES` 非空；`validate_all_sources()`
   不抛错但出具遗产点名——不静默放过，也不伪造口径。
"""
from __future__ import annotations

import copy

import pytest

from data_contracts import (
    LEGACY_SOURCES,
    SOURCE_REGISTRY,
    ContractError,
    DataProvenance,
    DataSourceContract,
    IncompleteContractError,
    UnknownSourceError,
    contract_for,
    register_source,
    validate_all_sources,
    validate_source_registered,
)


@pytest.fixture(autouse=True)
def _restore_registry():
    """测试级的注册在用例结束后撤掉，不污染全局注册表（单一事实来源）。"""
    before = copy.deepcopy(SOURCE_REGISTRY)
    yield
    SOURCE_REGISTRY.clear()
    SOURCE_REGISTRY.update(before)


def test_c1_existing_construction_still_works():
    """C-1：既有构造点不传新字段可构造；to_dict 不含 None 新键。"""
    p = DataProvenance("tdx", "pytdx")
    d = p.to_dict()
    assert d == {"source": "tdx", "provider": "pytdx"}
    assert p.availability_lag is None
    assert p.null_policy is None
    assert p.source_version is None


def test_c1_new_fields_roundtrip_when_given():
    """C-1 另一半：传了就能往返（可选增强不破坏默认路径）。"""
    p = DataProvenance("s", "p", availability_lag="T+1", null_policy="跳过",
                       source_version="v1")
    d = p.to_dict()
    assert d["availability_lag"] == "T+1"
    assert d["null_policy"] == "跳过"
    assert d["source_version"] == "v1"


@pytest.mark.parametrize("missing", ["availability_lag", "null_policy", "source_version"])
@pytest.mark.parametrize("blank", [None, "", "   "])
def test_c2_incomplete_registration_raises(missing, blank):
    """C-2：三字段各缺一次（None 与空串两种形态）都必须抛。"""
    kwargs = {"availability_lag": "ok", "null_policy": "ok", "source_version": "ok"}
    kwargs[missing] = blank
    with pytest.raises(IncompleteContractError, match=missing):
        register_source("t_src", **kwargs)


def test_c2_duplicate_registration_raises():
    """C-2：重复注册不允许静默覆盖（契约是单一事实来源）。"""
    with pytest.raises(ContractError, match="已注册"):
        register_source(
            "cninfo_disclosure",
            availability_lag="x", null_policy="y", source_version="z")


def test_c3_registered_sources_are_complete():
    """C-3：本轮三个注册源字段全非空。"""
    expected = {"cninfo_disclosure", "eastmoney_appointment", "fundamentals_yjbb"}
    assert expected <= set(SOURCE_REGISTRY), (
        f"应有源缺失: {expected - set(SOURCE_REGISTRY)}")
    for name in expected:
        c = contract_for(name)
        assert c.availability_lag.strip()
        assert c.null_policy.strip()
        assert c.source_version.strip()
        assert c.note.strip(), f"{name} 缺依据注记（note）"


def test_c3_null_policy_matches_code_behavior():
    """C-3：null_policy 的关键词与代码行为对应（不许写无依据的政策）。"""
    cn = contract_for("cninfo_disclosure")
    assert "法定截止日" in cn.null_policy
    em = contract_for("eastmoney_appointment")
    assert "不补造" in em.null_policy
    fy = contract_for("fundamentals_yjbb")
    assert "法定截止日" in fy.null_policy


def test_c3_unknown_source_raises():
    """C-3：未注册源查询抛 UnknownSourceError（不返回 None 让调用方猜）。"""
    with pytest.raises(UnknownSourceError, match="未注册"):
        contract_for("no_such_source")


def test_c3_validate_entry_matches_contract_for():
    """C-3：validate_source_registered 与 contract_for 同语义。"""
    assert validate_source_registered("cninfo_disclosure") is contract_for(
        "cninfo_disclosure")


def test_c4_legacy_sources_are_explicit():
    """C-4：遗产集非空且被 validate_all_sources 点名（不静默）。"""
    assert LEGACY_SOURCES
    report = validate_all_sources()  # 不抛错
    assert report["n_legacy"] == len(LEGACY_SOURCES)
    assert report["legacy_sources"]
    assert report["n_registered"] == len(SOURCE_REGISTRY)
    assert report["incomplete"] == []


def test_c4_registered_sources_are_frozen_dataclass():
    """C-4：契约是不可变 dataclass（注册后不许改字段）。"""
    c = contract_for("cninfo_disclosure")
    assert isinstance(c, DataSourceContract)
    with pytest.raises(Exception):
        c.null_policy = "改一下"  # type: ignore[misc]
