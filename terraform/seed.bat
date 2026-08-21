@echo off
rem Keep this console open on double-click: relaunch once under "cmd /k" so the window
rem stays open after the run (even on error). Guarded to avoid an infinite loop.
if not defined _CHATBOT_KEEPOPEN (
  set "_CHATBOT_KEEPOPEN=1"
  cmd /k ""%~f0" %*"
  exit /b
)
setlocal
rem chatbot_invitro - run the db_hiroba_qa_init seed task and wait for exitCode=0. ADR-0040.
rem Prereq: both database and app constructions applied. Can also be used to re-seed.
call "%~dp0deploy\run.bat" seed
echo.
echo ---- Finished. This window stays open. Type 'exit' to close it. ----
endlocal
