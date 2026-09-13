# Phase 27 Web-Sourced Real-Data Execution Report

## Executed data source
Public GitHub raw CSV published in the SysTradeBench repository for A-share symbol 300750 (CATL), 2024-2025 OHLCV dataset. The repository states its A-share daily data cover 2024-2025 and include 300750 among five A-share instruments.

## Actual web-sourced slice executed
- Symbol: 300750
- Source slice: 2024-11-14 through 2025-03-11
- Rows executed: 77
- Fields: date, open, high, low, close, volume
- Data audit: 77 valid rows, 0 structural/OHLC errors

## Defect found during end-to-end execution
The portfolio pipeline required `amount` >= 100m average. OHLCV-only public data was loaded with amount=0, which caused all securities to fail the liquidity filter and generated zero trades even when volume data were present.

## Repair
`liquidity.py` now:
1. uses actual `amount` whenever present;
2. when amount is missing, estimates notional from `close * volume * 100` for A-share feeds where volume is supplied in lots;
3. keeps the existing liquidity thresholds and slippage schedule.

## Verification
- Full project test suite after repair: 44 passed
- Web-sourced slice before repair through portfolio backtest: 0 trades, 0.0% return (false inactivity due to missing amount)
- Same slice after repair through portfolio backtest: 2 trades, -1.237% return, max drawdown 1.254%, daily Sharpe -1.885
- Independent walk-forward execution on the same web-sourced slice: 2 closed trades, -4.186% total return, win rate 50%

## Interpretation
This is a genuine web-sourced execution and it did not produce a favorable result on the tested slice. The sample is far too short and too narrow for an Alpha verdict; therefore the correct Alpha state remains INCONCLUSIVE. The important result is that the first actual web-data execution exposed and repaired a pipeline defect that would otherwise have silently converted valid OHLCV-only datasets into zero-trade backtests.
