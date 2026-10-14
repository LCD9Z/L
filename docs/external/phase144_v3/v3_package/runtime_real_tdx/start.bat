@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "TDX_PATH=D:\new_tdx\vipdoc"
if exist "tdx_path.txt" set /p TDX_PATH=<"tdx_path.txt"
echo ==============================================
echo A-share TDX Quant V3 - 100000 Yuan Paper Portfolio
echo ==============================================
echo TDX_PATH=%TDX_PATH%
echo INITIAL_CASH=100000
if not exist "%TDX_PATH%" goto NO_TDX
where py >nul 2>nul
if not errorlevel 1 goto USE_PY
where python >nul 2>nul
if not errorlevel 1 goto USE_PYTHON
echo [ERROR] Python not found.
pause
exit /b 10
:USE_PY
py -3 run_v3_portfolio.py --tdx-path "%TDX_PATH%" --output output
goto FINISH
:USE_PYTHON
python run_v3_portfolio.py --tdx-path "%TDX_PATH%" --output output
goto FINISH
:NO_TDX
echo [ERROR] TDX folder not found: %TDX_PATH%
:FINISH
echo.
echo Output: output\daily_nav.csv / trades.csv / all_top20_signals.csv / rebalance_log.csv / run_report.json
echo.
pause
