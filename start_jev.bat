@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" app\server.py --env-file .env %*
    goto :eof
)
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" app\server.py --env-file .env %*
    goto :eof
)
if exist "env\Scripts\python.exe" (
    "env\Scripts\python.exe" app\server.py --env-file .env %*
    goto :eof
)
where python >nul 2>nul
if not errorlevel 1 (
    python app\server.py --env-file .env %*
    goto :eof
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 app\server.py --env-file .env %*
    goto :eof
)
echo Python was not found in the project environments, PATH, or Python launcher.
pause
exit /b 1
