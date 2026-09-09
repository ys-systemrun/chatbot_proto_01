@echo off
rem Keep this console open on double-click: relaunch once under "cmd /k" so the window
rem stays open after the run (even on error). Guarded to avoid an infinite loop.
if not defined _CHATBOT_KEEPOPEN (
  set "_CHATBOT_KEEPOPEN=1"
  cmd /k ""%~f0" %*"
  exit /b
)
setlocal
rem chatbot_invitro - ad-hoc SQL execution (QUERY_MODE=true). ADR-0083 / ADR-0040.
rem Runs the SQL written in terraform\query.sql against the RDS database via a one-shot
rem db_hiroba_qa_init run-task, then prints the result (SELECT rows / affected row count)
rem fetched from CloudWatch Logs.
rem
rem Runs with the master role: query.sql may contain DESTRUCTIVE SQL (DROP/DELETE/TRUNCATE).
rem Before it runs, the target database name must be typed to confirm (no --yes bypass).
rem Only the result set of the LAST statement is shown on screen.
rem
rem Prereq:
rem   - Docker Desktop running; terraform\.env filled (AWS creds + all TF_VAR_*).
rem   - Both database and app constructions already applied.
rem   - Operator AWS credentials have logs:GetLogEvents on /ecs/db-hiroba-qa-init.
rem   - Write the SQL to run in terraform\query.sql (see query.sql.example).
rem
rem Usage (double-click = chatbot), or from a prompt:
rem   query.bat                          (target=chatbot)
rem   query.bat --target conversation
rem   query.bat --target both
rem   query.bat --sql-file other.sql
call "%~dp0deploy\run.bat" query %*
echo.
echo ---- Finished. This window stays open. Type 'exit' to close it. ----
endlocal
