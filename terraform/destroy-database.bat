@echo off
rem Keep this console open on double-click: relaunch once under "cmd /k" so the window
rem stays open after the run (even on error). Guarded to avoid an infinite loop.
if not defined _CHATBOT_KEEPOPEN (
  set "_CHATBOT_KEEPOPEN=1"
  cmd /k ""%~f0" %*"
  exit /b
)
setlocal
rem chatbot_invitro - DATABASE construction teardown (RDS + seeded data). ADR-0040.
rem Deletes the RDS instance and seeded data. Requires typing 'destroy-database' to confirm.
rem Destroy order: run destroy-app.bat first (app -> database).
call "%~dp0deploy\run.bat" destroy-database
echo.
echo ---- Finished. This window stays open. Type 'exit' to close it. ----
endlocal
