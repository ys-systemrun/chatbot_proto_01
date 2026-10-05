@echo off
rem Keep this console open on double-click: relaunch once under "cmd /k" so the window
rem stays open after the run (even on error). Guarded to avoid an infinite loop.
if not defined _CHATBOT_KEEPOPEN (
  set "_CHATBOT_KEEPOPEN=1"
  cmd /k ""%~f0" %*"
  exit /b
)
setlocal
rem chatbot_invitro - apply the datastore construction (S3 bucket used as the DVC remote). ADR-0097.
rem Idempotent. This layer is long-lived and is never destroyed by destroy-app / destroy-database.
rem Prereq: Docker Desktop running; terraform\.env filled (AWS creds).
call "%~dp0deploy\run.bat" apply-datastore %*
echo.
echo ---- Finished. This window stays open. Type 'exit' to close it. ----
endlocal
