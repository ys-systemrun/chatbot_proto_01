@echo off
rem Keep this console open on double-click: relaunch once under "cmd /k" so the window
rem stays open after the run (even on error). Guarded to avoid an infinite loop.
if not defined _CHATBOT_KEEPOPEN (
  set "_CHATBOT_KEEPOPEN=1"
  cmd /k ""%~f0" %*"
  exit /b
)
setlocal
rem chatbot_invitro - Phase 0 (state bucket only). ADR-0040: runs in a Python container.
rem Prereq: Docker Desktop running; fill terraform\.env with STATE_BUCKET / AWS_REGION and AWS creds.
call "%~dp0deploy\run.bat" bootstrap
echo.
echo ---- Finished. This window stays open. Type 'exit' to close it. ----
endlocal
