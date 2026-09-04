@echo off
rem Keep this console open on double-click: relaunch once under "cmd /k" so the window
rem stays open after the run (even on error). Guarded to avoid an infinite loop.
if not defined _CHATBOT_KEEPOPEN (
  set "_CHATBOT_KEEPOPEN=1"
  cmd /k ""%~f0" %*"
  exit /b
)
setlocal
rem chatbot_invitro - migration-only run (MIGRATE_ONLY=true). ADR-0075 / ADR-0040.
rem Applies pending yoyo migrations to chatbot and conversation RDS databases, plus role
rem creation / grants / export-reader role, but SKIPS chatbot seed insertion (embedding calc).
rem Non-destructive and idempotent: safe to run repeatedly. No confirmation prompt (unattended).
rem Use this when you only need to reflect schema changes; keep using import-data for data.
rem Prereq: both database and app constructions already applied.
call "%~dp0deploy\run.bat" migrate
echo.
echo ---- Finished. This window stays open. Type 'exit' to close it. ----
endlocal
