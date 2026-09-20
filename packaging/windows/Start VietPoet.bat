@echo off
rem Double-click to start VietPoet (see README.txt). Closing this window stops it.
title VietPoet
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher\start.ps1" %*
if errorlevel 1 pause
