@echo off
rem Keep this console open on double-click: relaunch once under "cmd /k" so the window
rem stays open after the run (even on error). Guarded to avoid an infinite loop.
if not defined _CHATBOT_KEEPOPEN (
  set "_CHATBOT_KEEPOPEN=1"
  cmd /k ""%~f0" %*"
  exit /b
)
setlocal
rem chatbot_invitro - export all data to SQL files, then tear down app and database. ADR-0103.
rem   [1/3] export : both databases -> terraform\backup\ (knowledge.sql / conversation.sql / manifest.json)
rem   [2/3] destroy-app      (same as destroy-app.bat)
rem   [3/3] destroy-database (same as destroy-database.bat)
rem Requires typing 'destroy-all' once to confirm (no --yes). Nothing is destroyed unless the
rem export succeeded and its SHA-256 matched. The previous files in terraform\backup\ are
rem overwritten by a successful export, so do not run this (or export-data.bat) before restoring.
rem
rem Prereq: Docker Desktop running; terraform\.env filled; both database and app applied.
rem If the app construction is already gone, run destroy-database.bat (no export) or
rem apply-app.bat first and then run this again.
rem
rem Resume after a failure in step 2 or 3 (reuses terraform\backup\, does not export again):
rem   destroy-all.bat --resume-from destroy-app
rem   destroy-all.bat --resume-from destroy-database
rem
rem Restore later: apply-all.bat, then
rem   import-data.bat --knowledge-sql backup\knowledge.sql --conversation-sql backup\conversation.sql
call "%~dp0deploy\run.bat" destroy-all %*
echo.
echo ---- Finished. This window stays open. Type 'exit' to close it. ----
endlocal
