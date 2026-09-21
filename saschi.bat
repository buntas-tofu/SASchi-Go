@echo off
setlocal

rem ---------------------------------------------------------------------------
rem  SASchi-Go launcher (Windows)
rem
rem  Boots a Python 3.12 environment and runs the pipeline interface.
rem    saschi.bat                          interactive console (needs rich)
rem    saschi.bat analyze  path\to\x.sas    parse, recognize, route, report
rem    saschi.bat translate path\to\x.sas   emit translated code and report
rem    saschi.bat check                    environment readiness
rem    saschi.bat verify                   run the fixture gate suite
rem
rem  Drag a .sas file onto this file to translate it. Add -o out.py to write
rem  the translated code to a file instead of the console.
rem ---------------------------------------------------------------------------

rem Resolve the repository root as this file's directory.
set "ROOT=%~dp0"

rem Prefer a local venv, then python on PATH, then the py launcher at 3.12.
set "PYEXE=python"
set "PYARGS="
if exist "%ROOT%.venv\Scripts\python.exe" (
    set "PYEXE=%ROOT%.venv\Scripts\python.exe"
    goto :have_python
)
where python >nul 2>nul
if not errorlevel 1 goto :have_python
where py >nul 2>nul
if not errorlevel 1 (
    set "PYEXE=py"
    set "PYARGS=-3.12"
    goto :have_python
)
echo [saschi] no Python interpreter found on PATH.
echo [saschi] install Python 3.12 plus the gate dependencies, then retry.
pause
exit /b 1

:have_python
rem Run from the repository root so imports and .sas paths resolve.
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%;%PYTHONPATH%"

%PYEXE% %PYARGS% -m saschi %*

set "STATUS=%ERRORLEVEL%"
if not "%STATUS%"=="0" (
    echo.
    echo [saschi] the command finished with a non-zero status ^(%STATUS%^).
    pause
)
exit /b %STATUS%
