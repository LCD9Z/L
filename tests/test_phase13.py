from validation.benchmark import benchmark_metrics
from historical_universe import point_in_time_universe
from validation.strategy_validation import bootstrap_trade_returns, split_periods
from validation.health_monitor import evaluate_health

def test_pit_universe_uses_latest_snapshot_only():
    m={'2024-01-01':['000001'],'2024-02-01':['000002']}
    assert point_in_time_universe(m,'2024-01-15')==['000001']
    assert point_in_time_universe(m,'2024-03-01')==['000002']

def test_bootstrap_is_deterministic_and_reports_probability():
    a=bootstrap_trade_returns([1,-1,2,-.5],iterations=200,seed=7)
    b=bootstrap_trade_returns([1,-1,2,-.5],iterations=200,seed=7)
    assert a==b and 0<=a['probability_positive']<=1

def test_benchmark_metrics_has_excess_fields():
    curve=[{'date':'2024-01-01','equity':100},{'date':'2024-01-02','equity':102},{'date':'2024-01-03','equity':103}]
    bars=[{'date':'2024-01-01','close':100},{'date':'2024-01-02','close':101},{'date':'2024-01-03','close':101}]
    r=benchmark_metrics(curve,bars)
    assert r['common_periods']==2 and r['excess_return_pct'] is not None

def test_health_alerts_detect_losses():
    r=evaluate_health([{'equity':100},{'equity':80}],[{'return_pct':-1,'status':'closed'}]*5,max_drawdown_alert=15,consecutive_loss_alert=5)
    assert not r['healthy'] and 'drawdown_alert' in r['alerts'] and 'consecutive_loss_alert' in r['alerts']

def test_split_periods():
    b=list(range(10)); windows=split_periods(b,4,2)
    assert len(windows)==3 and windows[0]['test']==[4,5]
