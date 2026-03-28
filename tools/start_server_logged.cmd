@echo off
setlocal

set "ROOT=C:\Users\Demon\Documents\New project\OpenNXT"
set "LOG=%ROOT%\tmp-run-server.log"

if exist "%LOG%" del /f /q "%LOG%" >nul 2>nul

start "opennxt-server" /b cmd /c ""%ROOT%\build\install\OpenNXT\bin\OpenNXT.bat" run-server > "%LOG%" 2>&1"

endlocal
