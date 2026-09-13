import tempfile, os
from data_quality import audit_bars, require_pit_asof
from corporate.corporate_actions import adjust_execution_price
from risk.risk_budget import inverse_vol_weights, concentration_hhi
from regime_validation import classify_return_regime, summarize_by_regime
from alpha_experiment import compare_variants
from paper_trading import append_event, load_events
from release_gate import evaluate_release

def test_data_quality_and_pit():
    bars=[{'date':'2024-01-01','open':1,'high':2,'low':1,'close':1.5}]
    assert audit_bars(bars)['ok']
    assert not require_pit_asof([{'published_at':'2024-01-03'}],'2024-01-02')['ok']

def test_corporate_action_adjustment(): assert adjust_execution_price(100,{'split_ratio':2,'cash_dividend':3})==47

def test_risk_budget_caps_and_hhi():
    w=inverse_vol_weights({'a':.1,'b':.2,'c':.3},.6)
    assert abs(sum(w.values())-1)<1e-9 and max(w.values())<=.6+1e-9 and concentration_hhi(w)>0

def test_regime_validation():
    r=[.02,-.03,0]; s=summarize_by_regime(r,classify_return_regime(r)); assert set(s)=={'bull','bear','range'}

def test_alpha_experiment(): assert compare_variants({'a':[1,2],'b':[0]})[0]['variant']=='a'

def test_paper_ledger():
    with tempfile.TemporaryDirectory() as d:
        p=os.path.join(d,'x.json'); append_event(p,{'date':'2024-01-01','action':'buy'}); assert len(load_events(p))==1

def test_release_gate():
    assert evaluate_release(30,True,True)['approved']; assert not evaluate_release(24,True,True)['approved']

def test_release_gate_rejects_failed_pit():
    assert not evaluate_release(30,True,False)['approved']
