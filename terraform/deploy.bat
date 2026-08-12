@echo off
setlocal
rem chatbot_invitro AWS deploy (full pipeline). Double-click to run.
rem Prerequisites: fill scripts\config.ps1 (auto-created on first run) and
rem                envs\verify\terraform.tfvars, then AWS auth (aws configure / SSO)
rem                and a running Docker Desktop.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\deploy.ps1"
echo.
echo ---- Finished. Press any key to close this window. ----
pause >nul
endlocal
