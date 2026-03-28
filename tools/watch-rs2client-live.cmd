@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0watch-rs2client-live.ps1" %*
exit /b %ERRORLEVEL%
