@echo off
rem Keep this console open on double-click: relaunch once under "cmd /k" so the window
rem stays open after the run (even on error). Guarded to avoid an infinite loop.
if not defined _CHATBOT_KEEPOPEN (
  set "_CHATBOT_KEEPOPEN=1"
  cmd /k ""%~f0" %*"
  exit /b
)
setlocal
rem chatbot_invitro - apply the database construction (network + RDS + seed task defs). ADR-0040.
rem Prereq: Docker Desktop running; terraform\.env filled (AWS creds + all TF_VAR_*).
call "%~dp0deploy\run.bat" apply-database
echo.
echo ---- Finished. This window stays open. Type 'exit' to close it. ----
endlocal
