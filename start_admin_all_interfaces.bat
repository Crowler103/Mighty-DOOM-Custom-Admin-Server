@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    py -3 -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt

if "%ADMIN_PASSWORD%"=="" (
    echo.
    echo ADMIN_PASSWORD is not set. A temporary password will be generated and printed in the console.
    echo For a persistent password, run this first:
    echo set ADMIN_PASSWORD=your-secure-password
    echo.
    python app.py --db "db\local.sqlite3" --game-data "data\game-data.json" --host 0.0.0.0 --port 8090 --user admin
) else (
    python app.py --db "db\local.sqlite3" --game-data "data\game-data.json" --host 0.0.0.0 --port 8090 --user admin --password "%ADMIN_PASSWORD%"
)

pause
