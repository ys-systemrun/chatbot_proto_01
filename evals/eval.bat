@echo off
setlocal
rem chatbot_invitro - evaluation runner (ADR-0099). Runs "python -m runner" in a container.
rem Settings: evals\.env (copy from evals\.env.example; EVAL_BASE_URL = admin_ui URL).
rem LLM judge uses the AWS credentials in terraform\.env (same as deploy).
rem Prereq: Docker Desktop running; access to the admin_ui ALB (office network).
rem
rem Usage (from a prompt, any directory):
rem   evals\eval.bat pull-feedback                 Save new human evaluations to evals\feedback\
rem   evals\eval.bat build-golden                  Create evals\golden\v1.csv (first time only)
rem   evals\eval.bat run                           Ask golden set v1 in both modes and score answers
rem   evals\eval.bat run --mode agentic --limit 5  Try a few questions in one mode
rem   evals\eval.bat compare RUN_A RUN_B           Compare two runs (directory names under evals\runs\)
set "IMAGE=chatbot-evals:latest"
pushd "%~dp0.."
set "REPO=%CD%"
popd
docker build -q -t %IMAGE% "%~dp0." >nul || goto :fail
docker run --rm -it -v "%REPO%:/work" -w /work/evals %IMAGE% python -m runner %*
goto :eof

:fail
echo [eval] Image build failed. Make sure Docker Desktop is running.
exit /b 1
