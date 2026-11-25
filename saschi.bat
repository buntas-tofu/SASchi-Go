@echo off
setlocal
REM SASchi-Go launcher. Drops into the rich interface. Pass a .sas file to open it in context.
REM UTF-8 mode is required, not optional: the gates build non-ASCII test vectors
REM and the cp1252 default raises UnicodeEncodeError on them.
set "PYTHONUTF8=1"
cd /d "%~dp0"
set "PYTHON=python"
where python >nul 2>nul || set "PYTHON=py"
"%PYTHON%" -m saschi.tui %*
endlocal
