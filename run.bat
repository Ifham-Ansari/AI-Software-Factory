@echo off
rem ============================================================================
rem  AI Software Factory: double-click this file to start it on Windows.
rem
rem  First run: checks your tools, installs dependencies, builds the dashboard.
rem  Every run: starts AI Software Factory and opens the dashboard in your browser.
rem
rem  Tip: drag a project folder onto run.bat to open that folder directly.
rem  Advanced: run.bat [folder] [asf up options], for example  run.bat --port 4801
rem ============================================================================
setlocal EnableExtensions
title AI Software Factory
chcp 65001 >nul
cd /d "%~dp0"
set "REPO=%~dp0"
set "COREPACK_ENABLE_DOWNLOAD_PROMPT=0"

echo.
echo   ==============================================
echo     AI Software Factory
echo     Your AI software team, on your own machine
echo   ==============================================
echo.

rem ---- 1. Node.js 22.18 or newer ---------------------------------------------
where node >nul 2>nul
if errorlevel 1 goto :no_node
for /f "delims=" %%v in ('node --version') do set "NODEV=%%v"
node -e "const [a,b]=process.versions.node.split('.').map(Number);process.exit(a>22||(a===22&&b>=18)?0:1)"
if errorlevel 1 goto :old_node
echo   [ok] Node.js %NODEV%

rem ---- 2. pnpm, or corepack / npx as a fallback --------------------------------
where pnpm >nul 2>nul
if not errorlevel 1 (
  set "PNPM=pnpm"
  goto :have_pnpm
)
where corepack >nul 2>nul
if not errorlevel 1 (
  set "PNPM=corepack pnpm"
  goto :have_pnpm
)
set "PNPM=npx --yes pnpm@10.27.0"
:have_pnpm
echo   [ok] Package manager: %PNPM%

rem ---- 3. Claude Code and Git: needed by the agents, not to open the dashboard --
where claude >nul 2>nul
if errorlevel 1 (
  echo   [i]  Claude Code was not found. That is fine without a Claude subscription:
  echo        add a free API key on the dashboard's "API keys" screen and choose
  echo        "Built-in engine" in Settings. To use Claude Code instead, install it
  echo        and log in once by running: claude  https://docs.claude.com/en/docs/claude-code
) else (
  echo   [ok] Claude Code found
)
where git >nul 2>nul
if errorlevel 1 (
  echo   [!]  Git was not found. Agents need the bash that comes with Git for Windows:
  echo        https://git-scm.com/download/win
) else (
  echo   [ok] Git found
)

rem ---- 4. Install dependencies on the first run, or after they changed ---------
node -e "const fs=require('fs');const m=f=>{try{return fs.statSync(f).mtimeMs}catch{return 0}};const s=m('node_modules/.modules.yaml');process.exit(s&&s>=m('pnpm-lock.yaml')?0:1)"
if not errorlevel 1 goto :deps_ok
echo.
echo   Installing dependencies. This happens once and takes a minute or two...
echo.
call %PNPM% install
if errorlevel 1 goto :install_failed
:deps_ok
echo   [ok] Dependencies installed

rem ---- 5. Build the dashboard when it is missing or its source changed ---------
node -e "const fs=require('fs'),p=require('path');const d='packages/dashboard';let t=0;const w=x=>{for(const e of fs.readdirSync(x,{withFileTypes:true})){const f=p.join(x,e.name);if(e.isDirectory())w(f);else t=Math.max(t,fs.statSync(f).mtimeMs)}};w(d+'/src');w(d+'/public');t=Math.max(t,fs.statSync(d+'/index.html').mtimeMs);let b=0;try{b=fs.statSync(d+'/dist/index.html').mtimeMs}catch{}process.exit(b>=t?0:1)"
if not errorlevel 1 goto :build_ok
echo   Building the dashboard (about 30 seconds)...
set "BUILD_LOG=%TEMP%\asf-dashboard-build.log"
call %PNPM% build > "%BUILD_LOG%" 2>&1
if errorlevel 1 goto :build_failed
:build_ok
echo   [ok] Dashboard ready

rem ---- 6. Choose the starting folder and start ---------------------------------
rem  Default: a projects folder in your user folder. The dashboard's folder picker
rem  opens there, so you can create a folder for each app.
set "START_DIR=%USERPROFILE%\asf-projects"
if not "%~1"=="" if exist "%~1\*" (
  set "START_DIR=%~f1"
  shift
)
set "EXTRA="
:collect
if "%~1"=="" goto :start
set "EXTRA=%EXTRA% %1"
shift
goto :collect
:start
if not exist "%START_DIR%" mkdir "%START_DIR%"
rem  A trailing backslash (a drive root such as D:\) would escape the closing quote.
if "%START_DIR:~-1%"=="\" set "START_DIR=%START_DIR%."

echo.
echo   Starting AI Software Factory in: %START_DIR%
echo   The dashboard opens in your browser in a moment.
echo.
echo   Keep this window open while you work. Press Ctrl+C here to stop
echo   AI Software Factory and every agent.
echo.
node --disable-warning=ExperimentalWarning "%REPO%packages\cli\src\main.ts" up "%START_DIR%"%EXTRA%
if errorlevel 1 goto :run_failed
rem  When AI Software Factory is already running, asf up only opens the dashboard
rem  and returns, so leave the message on screen for a moment.
timeout /t 5 >nul
exit /b 0

rem ---- Errors -----------------------------------------------------------------
:no_node
echo   [x]  Node.js is not installed.
echo        Install Node.js 22.18 or newer (the LTS version is fine) from
echo        https://nodejs.org, then double-click run.bat again.
start "" "https://nodejs.org/en/download"
goto :fail

:old_node
echo   [x]  Node.js %NODEV% is too old. AI Software Factory needs 22.18 or newer.
echo        Install the current LTS version from https://nodejs.org, then
echo        double-click run.bat again.
start "" "https://nodejs.org/en/download"
goto :fail

:install_failed
echo.
echo   [x]  Installing dependencies failed. See the messages above.
echo        Check your internet connection and try again.
goto :fail

:build_failed
echo.
type "%BUILD_LOG%"
echo.
echo   [x]  Building the dashboard failed. See the messages above.
goto :fail

:run_failed
echo.
echo   [x]  AI Software Factory stopped with an error. See the messages above.
echo        If port 4800 is in use, run:  run.bat --port 4801

:fail
echo.
pause
exit /b 1
