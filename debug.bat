@echo off
rem 带控制台启动，方便看报错（关窗即退出程序）
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" main.py %*
) else (
  python main.py %*
)
pause
