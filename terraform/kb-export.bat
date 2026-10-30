@echo off
rem Keep this console open on double-click: relaunch once under "cmd /k" so the window
rem stays open after the run (even on error). Guarded to avoid an infinite loop.
if not defined _CHATBOT_KEEPOPEN (
  set "_CHATBOT_KEEPOPEN=1"
  cmd /k ""%~f0" %*"
  exit /b
)
setlocal
rem chatbot_invitro - export both databases as CSV snapshots and record them with DVC (non-destructive). ADR-0109.
rem knowledge    -> db_init\data\knowledge\   (also the seed source)
rem conversation -> snapshots\conversation\    (restore only; contains chat logs, never commit the CSV itself)
rem One CSV per table (PostgreSQL COPY format, embeddings excluded) plus manifest.json, then "dvc add".
rem The app service is stopped during the export and restored afterwards (success or failure).
rem After it finishes: commit the .dvc files and run "terraform\dvc.bat push".
rem
rem Prereq: Docker Desktop running; terraform\.env filled; both database and app applied.
rem
rem Usage (double-click = asks y/N), or from a prompt:
rem   kb-export.bat
rem   kb-export.bat --yes
call "%~dp0deploy\run.bat" kb-export %*
echo.
echo ---- Finished. This window stays open. Type 'exit' to close it. ----
endlocal
