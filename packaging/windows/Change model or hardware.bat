@echo off
rem Choose the model size (4B or 9B) and graphics card or CPU again.
title VietPoet - change model or hardware
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher\start.ps1" -Reconfigure %*
if errorlevel 1 pause
