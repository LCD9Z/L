# -*- coding: utf-8 -*-
"""组合级风险引擎：统一决定是否允许新开仓与仓位倍率。"""
from dataclasses import dataclass

@dataclass
class RiskLimits:
    max_drawdown_pct: float = 12.0
    soft_drawdown_pct: float = 6.0
    max_consecutive_losses: int = 5
    max_single_position_pct: float = 0.20
    max_total_exposure_pct: float = 0.90

def evaluate_portfolio(drawdown_pct=0, consecutive_losses=0, regime='RANGE', limits=None):
    limits=limits or RiskLimits(); regime=str(regime).upper()
    reasons=[]; multiplier=1.0
    if drawdown_pct >= limits.max_drawdown_pct:
        return {'allow_new_positions':False,'multiplier':0.0,'reasons':['max_drawdown_breached']}
    if drawdown_pct >= limits.soft_drawdown_pct: multiplier=min(multiplier,0.5); reasons.append('soft_drawdown')
    if consecutive_losses >= limits.max_consecutive_losses: multiplier=min(multiplier,0.5); reasons.append('loss_streak')
    if regime in ('WEAK','RISK_OFF'): multiplier=min(multiplier,0.5); reasons.append('weak_regime')
    if regime in ('EXTREME','HALT'): return {'allow_new_positions':False,'multiplier':0.0,'reasons':['extreme_regime']}
    return {'allow_new_positions':True,'multiplier':multiplier,'reasons':reasons or ['normal']}
