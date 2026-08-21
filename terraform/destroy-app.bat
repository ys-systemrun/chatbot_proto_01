@echo off
rem Keep this console open on double-click: relaunch once under "cmd /k" so the window
rem stays open after the run (even on error). Guarded to avoid an infinite loop.
if not defined _CHATBOT_KEEPOPEN (
  set "_CHATBOT_KEEPOPEN=1"
  cmd /k ""%~f0" %*"
  exit /b
)
setlocal
rem chatbot_invitro - tear down the APP construction only (RDS stays). ADR-0040.
rem Requires typing 'destroy-app' to confirm. Restart later with apply-app.bat only (no re-seed).
call "%~dp0deploy\run.bat" destroy-app
echo.
echo ---- Finished. This window stays open. Type 'exit' to close it. ----
endlocal
