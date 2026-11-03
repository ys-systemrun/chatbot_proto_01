@echo off
rem Keep this console open on double-click: relaunch once under "cmd /k" so the window
rem stays open after the run (even on error). Guarded to avoid an infinite loop.
if not defined _CHATBOT_KEEPOPEN (
  set "_CHATBOT_KEEPOPEN=1"
  cmd /k ""%~f0" %*"
  exit /b
)
setlocal
rem chatbot_invitro - restore the databases from the CSV snapshots (DESTRUCTIVE). ADR-0109.
rem Reads knowledge from db_init\data\knowledge\ and conversation from snapshots\conversation\
rem (run "terraform\dvc.bat pull" first), uploads them to S3, then wipes and reloads the target tables.
rem Embeddings are filled from db_init\data\embedding_cache\.
rem Stops if the schema version differs or if the target database changed since the last import/export;
rem --force overrides those checks. A rollback SQL of the old data is saved to S3 first.
rem The db_init task log (imported rows, checks, rollback location) is printed when the task ends.
rem
rem Prereq: Docker Desktop running; terraform\.env filled; both database and app applied.
rem
rem Usage (asks for the cluster name), or from a prompt:
rem   kb-import.bat
rem   kb-import.bat --target knowledge
rem   kb-import.bat --force
call "%~dp0deploy\run.bat" kb-import %*
echo.
echo ---- Finished. This window stays open. Type 'exit' to close it. ----
endlocal
