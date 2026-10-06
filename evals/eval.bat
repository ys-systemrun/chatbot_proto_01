@echo off
setlocal
rem chatbot_invitro - evaluation runner (ADR-0099). Runs "python -m runner" in a python container.
rem Settings: evals\.env (copy from evals\.env.example; EVAL_BASE_URL = admin_ui URL).
rem Prereq: Docker Desktop running; access to the admin_ui ALB (office network).
rem
rem Usage (from a prompt, any directory):
rem   evals\eval.bat pull-feedback      Save new human evaluations to evals\feedback\<datetime>.jsonl
pushd "%~dp0"
set "EVALS=%CD%"
popd
docker run --rm -v "%EVALS%:/evals" -w /evals python:3.11-slim python -m runner %*
endlocal
