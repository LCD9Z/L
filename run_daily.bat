@echo off
rem TDX daily recommender entry for Windows Task Scheduler (all-ASCII on purpose)
rem Register (once, in cmd as admin or normal user):
rem   schtasks /create /tn TDXDaily /tr "C:\Users\T430\Desktop\1.0\run_daily.bat" /sc weekly /d MON,TUE,WED,THU,FRI /st 15:30
rem Unregister:
rem   schtasks /delete /tn TDXDaily /f
cd /d C:\Users\T430\Desktop\1.0
"C:\Users\T430\.workbuddy\binaries\python\envs\default\Scripts\python.exe" -m tdx_native.run_daily >> reports\daily\run.log 2>&1
