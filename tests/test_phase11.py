from risk.liquidity import dynamic_slippage,is_liquid
from exchange_rules import limit_prices
from validation.robustness import is_stable

def test_limit_prices():
    assert limit_prices(10,'600000')==(11.0,9.0)

def test_liquidity():
    rows=[{'amount':200_000_000} for _ in range(20)]
    assert is_liquid(rows)
    assert dynamic_slippage(rows)>=0.0005

def test_stability():
    assert is_stable([{'return_pct':10},{'return_pct':12},{'return_pct':8}])
