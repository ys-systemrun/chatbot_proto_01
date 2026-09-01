@echo off
rem Keep this console open on double-click: relaunch once under "cmd /k" so the window
rem stays open after the run (even on error). Guarded to avoid an infinite loop.
if not defined _CHATBOT_KEEPOPEN (
  set "_CHATBOT_KEEPOPEN=1"
  cmd /k ""%~f0" %*"
  exit /b
)
setlocal
rem chatbot_invitro - full-data import (TRUNCATE + overwrite). ADR-0066 / ADR-0040.
rem Destructive: wipes target tables and overwrites from SQL dumps. Auto-backup is taken first.
rem Requires typing the target cluster name to confirm before it runs.
rem
rem Prereq:
rem   - Docker Desktop running; terraform\.env filled (AWS creds + all TF_VAR_*).
rem   - Both database and app constructions already applied.
rem   - Export dumps placed in this folder: terraform\chatbot.sql and terraform\conversation.sql
rem     (or pass --chatbot-sql / --conversation-sql with a path).
rem
rem Usage (double-click = both databases), or from a prompt:
rem   import-data.bat                       (target=both)
rem   import-data.bat --target chatbot
rem   import-data.bat --target conversation
call "%~dp0deploy\run.bat" import-data %*
echo.
echo ---- Finished. This window stays open. Type 'exit' to close it. ----
endlocal
