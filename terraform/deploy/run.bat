@echo off
rem Shared runner (ADR-0040). Args = deploy subcommand (+ extra options).
rem Called by each terraform\*.bat. Builds the image if missing, then runs deploy in a container.
rem Host prereq: Docker Desktop running. terraform / aws CLI are NOT needed on the host (bundled in the image).
setlocal
set "IMAGE=chatbot-deploy:latest"

rem Resolve repo root (two levels up from terraform\deploy\) as an absolute path (no trailing backslash).
pushd "%~dp0..\.."
set "REPO=%CD%"
popd

rem Build the image every run (context = this file's directory = terraform\deploy).
rem Docker layer cache makes this fast when nothing changed, and it guarantees that
rem edits to the deploy Python code are always picked up (image is not left stale).
echo [deploy] Building image %IMAGE% ...
docker build -t %IMAGE% "%~dp0." || goto :fail

rem Share the Docker socket (DooD) to drive the host daemon. Mount the repo at /work.
rem Cache provider plugins in a named volume. terraform\.env is read from under the mount.
rem Note: this is a Linux container, so bind /var/run/docker.sock (NOT //./pipe/docker_engine,
rem       which is for Windows containers). Docker Desktop exposes /var/run/docker.sock to Linux containers.
docker run --rm -it ^
  -v "%REPO%:/work" ^
  -v /var/run/docker.sock:/var/run/docker.sock ^
  -v chatbot-tf-plugins:/root/.terraform.d/plugin-cache ^
  -w /work/terraform ^
  %IMAGE% %*
goto :eof

:fail
echo [deploy] Image build failed. Make sure Docker Desktop is running.
exit /b 1
