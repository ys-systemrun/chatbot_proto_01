@echo off
setlocal
rem chatbot_invitro AWS teardown. Double-click to run (requires typing 'destroy' to confirm).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\destroy.ps1"
echo.
echo ---- Finished. Press any key to close this window. ----
pause >nul
endlocal
