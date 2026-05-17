@echo off
:: QuantStrike Server - Double-click to start
:: Launches backend + frontend + Cloudflare tunnel
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File start-server.ps1
pause
