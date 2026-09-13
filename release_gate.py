# -*- coding: utf-8 -*-
"""Conservative release gates; no profitability claim is inferred.

本模块是「研究完整性门禁」的裁决层，被两条真实运行路径使用：

* ``real_alpha_pipeline.run_real_alpha_pipeline`` —— 端到端 Alpha 管线
* ``run_tdx_rolling_eval`` —— 多窗口滚动稳健性检验

设计要点：统计结论（``ALPHA_SUPPORTED`` / ``ALPHA_NOT_ESTABLISHED``）与**可发布结论**
是两件事。证据不完整时，可发布结论必须是 ``INCONCLUSIVE``，
但原始统计结论要原样保留——「统计上不显著」与「证据不足无法判定」
是完全不同的处境，混为一谈会丢失信息。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

from survivorship_guard import SurvivorshipAudit, audit_survivorship, guard_alpha_claim

#: 门禁要求的证据项（与 SurvivorshipAudit 字段一一对应）
EVIDENCE_KEYS = (
    "pit_universe",
    "lifecycle",
    "delisted_history",
    "st_history",
    "suspension_history",
    "corporate_actions",
)


def evaluate_release(test_passed, secret_scan_ok, pit_ok, min_tests=25):
    reasons=[]
    if test_passed<min_tests: reasons.append('insufficient_test_coverage')
    if not secret_scan_ok: reasons.append('secret_scan_failed')
    if not pit_ok: reasons.append('point_in_time_validation_failed')
    return {'approved':not reasons,'reasons':reasons,'test_passed':test_passed}


def evaluate_alpha_release(test_passed, secret_scan_ok, pit_ok, survivorship_audit: SurvivorshipAudit, min_tests=25):
    """Gate an Alpha claim; incomplete survivorship evidence is inconclusive, not a failure."""
    base = evaluate_release(test_passed, secret_scan_ok, pit_ok, min_tests)
    decision = guard_alpha_claim(survivorship_audit)
    reasons = list(base['reasons'])
    if not decision['allowed']:
        reasons.append('SURVIVORSHIP DATA INCOMPLETE')
    return {
        **base,
        'approved': not reasons,
        'reasons': reasons,
        'alpha_status': 'ALPHA_EVIDENCE_ELIGIBLE' if not reasons else 'INCONCLUSIVE',
        'survivorship_audit': survivorship_audit.to_dict(),
    }


# ---------------------------------------------------------------------------
# 构造审计对象
# ---------------------------------------------------------------------------

def build_survivorship_audit(
    evidence: Mapping[str, Any] | None = None,
    *,
    pit_universe_verified: bool = False,
) -> SurvivorshipAudit:
    """从「已具备哪些证据」构造审计对象。

    严格遵循项目原则：**缺失证据不推断为有效**。未在 ``evidence`` 中显式声明为 True 的
    项一律视为 False；``pit_universe`` 可由调用方用 ``pit_universe_verified`` 声明
    「本流程已自行校验过 PIT 股票池」。
    """
    ev: Mapping[str, Any] = evidence or {}

    def flag(key: str, default: bool = False) -> bool:
        value = ev.get(key, default)
        return bool(value)

    return audit_survivorship(
        pit_universe=flag("pit_universe", pit_universe_verified),
        lifecycle=flag("lifecycle"),
        delisted_history=flag("delisted_history"),
        st_history=flag("st_history"),
        suspension_history=flag("suspension_history"),
        corporate_actions=flag("corporate_actions"),
        missing_delisted_codes=int(ev.get("missing_delisted_codes") or 0),
    )


def missing_evidence(audit: SurvivorshipAudit) -> list[str]:
    """列出尚缺的证据项，便于把「为什么被阻断」讲清楚。"""
    pairs = (
        ("pit_universe", audit.pit_universe_ok),
        ("lifecycle", audit.lifecycle_ok),
        ("delisted_history", audit.delisted_history_ok),
        ("st_history", audit.st_history_ok),
        ("suspension_history", audit.suspension_history_ok),
        ("corporate_actions", audit.corporate_actions_ok),
    )
    return [name for name, ok in pairs if not ok]


def load_survivorship_evidence(path: str | Path | None) -> Dict[str, Any] | None:
    """读取证据清单 JSON；``None`` 表示未提供（等价于「无任何证据」）。

    JSON 采用扁平结构，键名见 :data:`EVIDENCE_KEYS`，可另附任意说明字段
    （如 ``source`` / ``note`` / ``as_of``）用于溯源，这些字段会被原样保留。
    """
    if path is None:
        return None
    p = Path(path)
    if not p.exists():
        raise ValueError(f"survivorship_evidence_file_missing: {p}")
    import json

    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("survivorship_evidence_must_be_json_object")
    return data


# ---------------------------------------------------------------------------
# 把统计结论交予门禁裁决
# ---------------------------------------------------------------------------

def gate_alpha_claim(
    statistical_verdict: str,
    survivorship_audit: SurvivorshipAudit,
) -> Dict[str, Any]:
    """根据研究完整性证据，决定统计结论是否**可以发布**。

    返回字段：

    ``verdict``
        可发布的结论。门禁未通过时为 ``INCONCLUSIVE``；通过时等于原始统计结论。
    ``statistical_verdict``
        原始统计结论，**永不改写**。用于区分「统计上不显著」与「证据不足无法判定」。
    ``alpha_status``
        ``RELEASABLE`` / ``INCONCLUSIVE``。
    ``gate``
        底层门禁裁决原文（含 ``allowed`` / ``status`` / ``reasons``）。
    ``reason`` / ``missing_evidence``
        仅在被阻断时出现，说明阻断原因与尚缺证据项。
    """
    decision = guard_alpha_claim(survivorship_audit)
    out: Dict[str, Any] = {
        "statistical_verdict": statistical_verdict,
        "verdict": statistical_verdict,
        "alpha_status": "RELEASABLE" if decision["allowed"] else "INCONCLUSIVE",
        "gate": decision,
    }
    if not decision["allowed"]:
        reasons = decision.get("reasons") or ["alpha_claim_blocked"]
        out["verdict"] = "INCONCLUSIVE"
        out["reason"] = reasons[0]
        out["reasons"] = list(reasons)
        out["missing_evidence"] = missing_evidence(survivorship_audit)
    return out
