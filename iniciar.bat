@echo off
cd /d "%~dp0"
set PY=py -3
%PY% --version >nul 2>&1 || set PY=python
%PY% -c "import pymupdf" >nul 2>&1 || %PY% setup.py
if not exist "_herramientas\tectonic\tectonic.exe" %PY% setup.py
%PY% servidor.py
pause
