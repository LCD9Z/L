# -*- coding: utf-8 -*-
"""研究完整性门禁的裁决逻辑，以及它是否**真的**接入了发布路径。

本文件有两类测试：

1. **行为测试** —— 门禁在各种证据组合下如何裁决。
2. **接线测试** —— 门禁是否真的被生产代码调用。
   起因：此前 `release_gate` / `survivorship_guard` 只被测试引用，
   而 README 声称「已接到发布流程」。这类「看起来接通了」正是本项目
   一贯反对的失效模式，因此显式守卫。
"""
import inspect
import json
from pathlib import Path

import pytest

import real_alpha_pipeline
import release_gate
import run_tdx_rolling_eval
import survivorship_guard
from release_gate import (
    build_survivorship_audit,
    gate_alpha_claim,
    load_survivorship_evidence,
    missing_evidence,
)

ALL_EVIDENCE = {
    "pit_universe": True,
    "lifecycle": True,
    "delisted_history": True,
    "st_history": True,
    "suspension_history": True,
    "corporate_actions": True,
}


# --- 构造审计对象 ---------------------------------------------------------

def test_no_evidence_means_not_ok():
    """缺失证据不推断为有效。"""
    audit = build_survivorship_audit(None)
    assert audit.ok is False
    assert audit.status == "INCONCLUSIVE"


def test_partial_evidence_still_blocked():
    audit = build_survivorship_audit({"delisted_history": True})
    assert audit.ok is False
    assert audit.delisted_history_ok is True
    assert audit.corporate_actions_ok is False


def test_pit_universe_verified_flag_is_honoured():
    """调用方若自行校验了 PIT 股票池，可如实声明（这不是推断，是证据）。"""
    audit = build_survivorship_audit(None, pit_universe_verified=True)
    assert audit.pit_universe_ok is True
    assert audit.ok is False  # 其余证据仍缺失


def test_explicit_evidence_overrides_verified_flag():
    audit = build_survivorship_audit({"pit_universe": False}, pit_universe_verified=True)
    assert audit.pit_universe_ok is False


def test_full_evidence_is_ok():
    assert build_survivorship_audit(ALL_EVIDENCE).ok is True


def test_missing_evidence_lists_only_absent_items():
    audit = build_survivorship_audit({"st_history": True, "lifecycle": True})
    missing = missing_evidence(audit)
    assert "st_history" not in missing
    assert "lifecycle" not in missing
    assert set(missing) == {"pit_universe", "delisted_history",
                            "suspension_history", "corporate_actions"}


# --- 门禁裁决 -------------------------------------------------------------

def test_incomplete_evidence_downgrades_verdict():
    gated = gate_alpha_claim("ALPHA_SUPPORTED", build_survivorship_audit(None))
    assert gated["verdict"] == "INCONCLUSIVE"
    assert gated["alpha_status"] == "INCONCLUSIVE"
    assert gated["reason"] == "SURVIVORSHIP DATA INCOMPLETE"


def test_statistical_verdict_is_never_lost():
    """「统计上不显著」与「证据不足」是两回事，原始结论必须保留。"""
    gated = gate_alpha_claim("ALPHA_NOT_ESTABLISHED", build_survivorship_audit(None))
    assert gated["statistical_verdict"] == "ALPHA_NOT_ESTABLISHED"
    assert gated["verdict"] == "INCONCLUSIVE"


def test_complete_evidence_releases_verdict_unchanged():
    gated = gate_alpha_claim("ALPHA_SUPPORTED", build_survivorship_audit(ALL_EVIDENCE))
    assert gated["verdict"] == "ALPHA_SUPPORTED"
    assert gated["alpha_status"] == "RELEASABLE"
    assert "reason" not in gated
    assert "missing_evidence" not in gated


def test_gate_reports_missing_items_when_blocked():
    gated = gate_alpha_claim("ALPHA_NOT_ESTABLISHED",
                             build_survivorship_audit({"pit_universe": True}))
    assert "corporate_actions" in gated["missing_evidence"]
    assert "pit_universe" not in gated["missing_evidence"]


def test_gate_is_deterministic():
    a = gate_alpha_claim("ALPHA_SUPPORTED", build_survivorship_audit(None))
    b = gate_alpha_claim("ALPHA_SUPPORTED", build_survivorship_audit(None))
    assert a == b


def test_missing_delisted_codes_is_recorded():
    audit = build_survivorship_audit({**ALL_EVIDENCE, "missing_delisted_codes": 15})
    assert audit.missing_delisted_codes == 15
    # 数量为 0 才代表退市历史完整
    assert build_survivorship_audit(ALL_EVIDENCE).missing_delisted_codes == 0


# --- 证据清单文件 ---------------------------------------------------------

def test_load_evidence_returns_none_without_path():
    assert load_survivorship_evidence(None) is None


def test_load_evidence_reads_json(tmp_path):
    p = tmp_path / "ev.json"
    p.write_text(json.dumps({**ALL_EVIDENCE, "source": "vendor-x", "as_of": "2026-09-13"}),
                 encoding="utf-8")
    ev = load_survivorship_evidence(p)
    assert ev is not None
    assert ev["delisted_history"] is True
    assert ev["source"] == "vendor-x"
    # 额外溯源字段不影响门禁判定
    assert build_survivorship_audit(ev).ok is True


def test_load_evidence_rejects_missing_file(tmp_path):
    with pytest.raises(ValueError, match="missing"):
        load_survivorship_evidence(tmp_path / "nope.json")


def test_load_evidence_rejects_non_object(tmp_path):
    p = tmp_path / "ev.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="object"):
        load_survivorship_evidence(p)


# --- 接线守卫（防止「文档说接通了、代码没接」） ---------------------------

def test_pipeline_imports_the_gate():
    assert real_alpha_pipeline.gate_alpha_claim is release_gate.gate_alpha_claim
    assert real_alpha_pipeline.build_survivorship_audit is release_gate.build_survivorship_audit


def test_pipeline_actually_invokes_the_gate():
    """仅仅 import 不算接通——必须被调用。"""
    src = inspect.getsource(real_alpha_pipeline.run_real_alpha_pipeline)
    assert "gate_alpha_claim(" in src
    assert "build_survivorship_audit(" in src


def test_pipeline_accepts_survivorship_evidence():
    params = inspect.signature(real_alpha_pipeline.run_real_alpha_pipeline).parameters
    assert "survivorship_evidence" in params


def test_rolling_eval_invokes_the_gate():
    src = inspect.getsource(run_tdx_rolling_eval.main)
    assert "gate_alpha_claim(" in src
    assert "build_survivorship_audit(" in src


def test_rolling_eval_exposes_evidence_cli_flag():
    src = inspect.getsource(run_tdx_rolling_eval.main)
    assert "--survivorship-evidence" in src


def test_release_gate_builds_on_survivorship_guard():
    assert release_gate.guard_alpha_claim is survivorship_guard.guard_alpha_claim
    assert release_gate.audit_survivorship is survivorship_guard.audit_survivorship


def test_evidence_keys_match_audit_builder():
    """EVIDENCE_KEYS 必须与 `audit_survivorship` 的参数名一致，否则会静默漂移。

    对照基准是**构造函数的参数名**（`pit_universe` 等），而非 dataclass 字段
    （`pit_universe_ok` 等）——前者才是「证据项」的语义来源。
    """
    params = inspect.signature(survivorship_guard.audit_survivorship).parameters
    accepted = {k for k, v in params.items()
                if v.kind in (v.KEYWORD_ONLY, v.POSITIONAL_OR_KEYWORD)}
    assert set(release_gate.EVIDENCE_KEYS) <= accepted


def test_every_evidence_key_is_readable_from_audit():
    """每个证据项都能从审计对象上读回，确保 `missing_evidence` 覆盖完整。"""
    audit = build_survivorship_audit(None)
    assert set(missing_evidence(audit)) == set(release_gate.EVIDENCE_KEYS)
    assert missing_evidence(build_survivorship_audit(ALL_EVIDENCE)) == []


# --- 与既有测试的兼容性 ---------------------------------------------------

def test_evaluate_alpha_release_still_works():
    """v4.9 移植过来的原有接口不得回归。"""
    audit = build_survivorship_audit(ALL_EVIDENCE)
    out = release_gate.evaluate_alpha_release(30, True, True, audit)
    assert out["approved"] is True
    assert out["alpha_status"] == "ALPHA_EVIDENCE_ELIGIBLE"

    bad = release_gate.evaluate_alpha_release(30, True, True, build_survivorship_audit(None))
    assert bad["approved"] is False
    assert "SURVIVORSHIP DATA INCOMPLETE" in bad["reasons"]
    assert bad["alpha_status"] == "INCONCLUSIVE"


def test_project_files_are_present():
    """守卫本文件所依赖的模块确实存在（防止重构时静默移动文件）。"""
    names = {"release_gate.py", "survivorship_guard.py", "real_alpha_pipeline.py",
             "run_tdx_rolling_eval.py"}
    found = {p.name for p in Path(release_gate.__file__).parent.glob("*.py")}
    assert names <= found
