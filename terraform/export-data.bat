@echo off
rem Keep this console open on double-click: relaunch once under "cmd /k" so the window
rem stays open after the run (even on error). Guarded to avoid an infinite loop.
if not defined _CHATBOT_KEEPOPEN (
  set "_CHATBOT_KEEPOPEN=1"
  cmd /k ""%~f0" %*"
  exit /b
)
setlocal
rem chatbot_invitro - export all data to SQL files (non-destructive). ADR-0103.
rem Saves both databases to terraform\backup\ (knowledge.sql / conversation.sql / manifest.json).
rem The app service is stopped during the export and restored afterwards (success or failure).
rem A successful export overwrites the previous files in terraform\backup\.
rem conversation.sql contains chat logs: keep it local and do not share it.
rem
rem Prereq: Docker Desktop running; terraform\.env filled; both database and app applied.
rem
rem Usage (double-click = asks y/N), or from a prompt:
rem   export-data.bat
rem   export-data.bat --yes
call "%~dp0deploy\run.bat" export-data %*
echo.
echo ---- Finished. This window stays open. Type 'exit' to close it. ----
endlocal
