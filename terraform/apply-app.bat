@echo off
rem Keep this console open on double-click: relaunch once under "cmd /k" so the window
rem stays open after the run (even on error). Guarded to avoid an infinite loop.
if not defined _CHATBOT_KEEPOPEN (
  set "_CHATBOT_KEEPOPEN=1"
  cmd /k ""%~f0" %*"
  exit /b
)
setlocal
rem chatbot_invitro - apply the app construction (ECS cluster + services + inspector + budget). ADR-0040.
rem Prereq: database construction applied; Docker Desktop running; terraform\.env filled.
call "%~dp0deploy\run.bat" apply-app
echo.
echo ---- Finished. This window stays open. Type 'exit' to close it. ----
endlocal
