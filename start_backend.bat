@echo off
chcp 65001 >nul
title FindStar Backend
cd /d "%~dp0backend"
python -c "import fastapi" 2>nul || pip install -r requirements.txt
echo.
echo Backend running at http://localhost:8000   (API docs: http://localhost:8000/docs)
echo Keep this window open. Press Ctrl+C to stop.
python -m uvicorn app.main:app --reload --port 8000
pause