@echo off
setlocal
rem chatbot_invitro - run DVC inside the deploy container (ADR-0097).
rem AWS credentials are taken from terraform\.env. Runs at the repository root.
rem Prereq: Docker Desktop running; apply-datastore done once (S3 bucket for the DVC remote).
rem
rem Usage (from a prompt, any directory):
rem   terraform\dvc.bat status
rem   terraform\dvc.bat add db_init/data/hiroba_qa
rem   terraform\dvc.bat push
rem   terraform\dvc.bat pull
rem   terraform\dvc.bat checkout
rem   terraform\dvc.bat diff kb-2026.10.05-1 HEAD
rem Paths are relative to the repository root and use forward slashes.
call "%~dp0deploy\run.bat" dvc %*
endlocal
