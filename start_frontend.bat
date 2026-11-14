@echo off
chcp 65001 >nul
title FindStar Frontend
set "PATH=D:\nodejs;%PATH%"
cd /d "%~dp0frontend"
if not exist node_modules call npm install
echo.
echo Frontend running at http://localhost:5173
echo Keep this window open. Press Ctrl+C to stop.
call npm run dev
pause